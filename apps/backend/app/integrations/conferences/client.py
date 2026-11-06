"""Bounded GitHub transport. Archive members are read in memory, never extracted."""

from __future__ import annotations
import asyncio
import io
import gzip
from contextlib import contextmanager
import os
import re
import tarfile
from pathlib import PurePosixPath
import httpx

MAX_DOWNLOAD = 50 * 1024 * 1024
MAX_YAML = 2 * 1024 * 1024
MAX_YAML_TOTAL = 20 * 1024 * 1024
MAX_TAR = 150 * 1024 * 1024


class _BoundedArchiveReader:
    """Bound every decompressed byte, including PAX/GNU metadata hidden by tarfile."""

    def __init__(self, source, limit: int):
        self.source = source
        self.remaining = limit

    def read(self, size: int = -1) -> bytes:
        requested = self.remaining + 1 if size < 0 else min(size, self.remaining + 1)
        data = self.source.read(requested)
        self.remaining -= len(data)
        if self.remaining < 0:
            raise ValueError("Conference archive exceeds expanded size limit")
        return data


@contextmanager
def _bounded_tar(archive: bytes):
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as decompressed:
        with tarfile.open(
            fileobj=_BoundedArchiveReader(decompressed, MAX_TAR), mode="r|"
        ) as tar:
            yield tar


def conference_files(archive: bytes) -> dict[str, bytes]:
    files = {}
    total = expanded = members = 0
    with _bounded_tar(archive) as tar:
        for member in tar:
            members += 1
            expanded += max(member.size, 0) + 512
            if members > 10000 or expanded > MAX_TAR:
                raise ValueError(
                    "Conference archive exceeds expanded size/member limit"
                )
            parts = PurePosixPath(member.name).parts
            if member.name.startswith("/") or ".." in parts or "\\" in member.name:
                raise ValueError("Unsafe archive path")
            relative = "/".join(parts[1:])
            selected = relative == "conference/types.yml" or (
                len(parts) == 4
                and parts[1] == "conference"
                and relative.endswith(".yml")
            )
            if not selected:
                continue
            if (
                not member.isfile()
                or member.issparse()
                or member.size < 0
                or member.size > MAX_YAML
                or relative in files
            ):
                raise ValueError("Invalid conference archive member")
            total += member.size
            if total > MAX_YAML_TOTAL:
                raise ValueError("Conference YAML exceeds size limit")
            stream = tar.extractfile(member)
            assert stream is not None
            files[relative] = stream.read(MAX_YAML + 1)
    return files


class ConferenceGitHubClient:
    def __init__(self, transport=None):
        self.transport = transport

    @staticmethod
    def headers():
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ShenZhi-conference-sync",
        }
        token = os.getenv("CONFERENCE_GITHUB_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def latest(self) -> tuple[str, str]:
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            response = await client.get(
                "https://api.github.com/repos/ccfddl/ccf-deadlines/commits/main",
                headers=self.headers(),
            )
            response.raise_for_status()
            body = response.json()
        sha = body["sha"]
        if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha):
            raise ValueError("Invalid upstream revision")
        return sha, body["commit"]["committer"]["date"][:10]

    async def download(self, sha: str) -> dict[str, bytes]:
        if not re.fullmatch("[0-9a-f]{40}", sha):
            raise ValueError("Invalid upstream revision")
        async with httpx.AsyncClient(timeout=60, transport=self.transport) as client:
            async with client.stream(
                "GET", f"https://codeload.github.com/ccfddl/ccf-deadlines/tar.gz/{sha}"
            ) as response:
                response.raise_for_status()
                if int(response.headers.get("content-length", "0")) > MAX_DOWNLOAD:
                    raise ValueError("Conference download exceeds size limit")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_DOWNLOAD:
                        raise ValueError("Conference download exceeds size limit")
        return await asyncio.to_thread(conference_files, bytes(data))

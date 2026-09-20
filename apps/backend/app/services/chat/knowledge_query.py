"""Small deterministic cleanup for Chat's Knowledge retrieval query only."""

from __future__ import annotations

import re


_QUESTION_PREFIXES = (
    "请用一句话解释",
    "用一句话解释",
    "请简单介绍一下",
    "请简单介绍",
    "帮我介绍一下",
    "帮我介绍",
    "请介绍一下",
    "介绍一下",
    "请简单解释",
    "简单解释",
    "什么是",
    "何为",
)
_QUESTION_SUFFIX = re.compile(r"[。！？!?；;：:]+$")


def normalize_knowledge_query(raw: str) -> str:
    """Remove a few known question wrappers while preserving the user's text.

    The caller still applies ``KnowledgeSearchRequest``'s 500-character limit.
    Returning the original input when cleanup would erase the subject keeps the
    helper safe for blank or malformed questions.
    """
    if not isinstance(raw, str) or not raw.strip():
        return raw

    candidate = raw.strip()
    for prefix in _QUESTION_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):].strip()
            break
    candidate = _QUESTION_SUFFIX.sub("", candidate).strip()
    return candidate or raw


__all__ = ["normalize_knowledge_query"]

"""Render A1 Topic covers from ShenZhi paper figures."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
from tempfile import NamedTemporaryFile, gettempdir
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat


W, H = 1440, 400
LANE_ANGLE = -16
LANE_GAP = 20
FIGURE_GAP = 2
LANE_GUTTER = "#d9e2d9"
# One continuous Figure on each clipped outer lane, three in each inner lane.
LANE_WEIGHTS = ((1,), (1.17, 1.03, .80), (.86, 1.18, .96), (1,))
LANE_COUNT = len(LANE_WEIGHTS)
REQUIRED_FIGURES = sum(map(len, LANE_WEIGHTS))
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "apps/web/public/topic-covers"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_url(url, mime, maximum):
    with build_opener(NoRedirect()).open(Request(url, headers={"Accept": mime}), timeout=40) as response:
        if not response.headers.get_content_type().startswith(mime.split("*")[0]):
            raise ValueError("Unexpected content type")
        data = response.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("Response exceeds the byte limit")
    return data


@dataclass
class Figure:
    source: dict
    image: Image.Image
    signature: int

    @property
    def ratio(self):
        return self.image.width / self.image.height


def safe_image_path(value):
    if not isinstance(value, str) or not value.startswith("/images/"):
        return None
    parts = value[8:].split("/")
    if len(parts) > 16 or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", p) for p in parts):
        return None
    if not re.search(r"\.(png|jpe?g|webp)$", parts[-1], re.I):
        return None
    return "/api/paper-images/" + "/".join(parts)


def trim_white(image):
    diff = ImageChops.difference(image, Image.new("RGB", image.size, "white")).convert("L")
    bounds = diff.point(lambda v: 255 if v > 22 else 0).getbbox()
    if not bounds:
        raise ValueError("blank image")
    left, top, right, bottom = bounds
    pad = max(2, round(min(image.size) * .012))
    return image.crop((max(0, left-pad), max(0, top-pad),
                       min(image.width, right+pad), min(image.height, bottom+pad)))


def resembles_pdf_page(image, original_size):
    # A full portrait page has many horizontal text lines in both halves.
    if image.width / image.height > .92:
        return False
    width, height = original_size
    page_ratio = any(abs(width / height - ratio) < .012 for ratio in (8.5 / 11, 1 / math.sqrt(2)))
    if page_ratio and width >= 1000 and image.width < width * .94:
        return True
    preview = image.convert("L").resize((180, 240))
    occupied = []
    for y in range(22, 222):
        left = sum(preview.getpixel((x, y)) < 192 for x in range(12, 86))
        right = sum(preview.getpixel((x, y)) < 192 for x in range(94, 168))
        occupied.append(left >= 9 and right >= 9)
    bands = sum(active and not previous for previous, active in zip([False] + occupied, occupied))
    return bands >= 18 and sum(occupied) >= 58


def decode_figure(payload):
    with Image.open(BytesIO(payload)) as original:
        if original.format not in {"JPEG", "PNG", "WEBP"} or original.width * original.height > 25_000_000:
            return None, "unsupported_image"
        oriented = ImageOps.exif_transpose(original).convert("RGBA")
    rgb = Image.new("RGB", oriented.size, "white")
    rgb.paste(oriented, mask=oriented.getchannel("A"))
    image = trim_white(rgb)
    if min(image.size) < 85:
        return None, "too_small"
    if resembles_pdf_page(image, rgb.size):
        return None, "likely_pdf_page"
    image.thumbnail((850, 650), Image.Resampling.LANCZOS)
    return image, None


def load_figure(origin, paper, cache):
    path = safe_image_path(paper.get("imageId"))
    if not path:
        return None, "unsupported_image_id"
    key = sha256((origin + path).encode()).hexdigest()
    local = cache / key
    try:
        if local.exists():
            payload = local.read_bytes()
        else:
            payload = read_url(origin + path, "image/*", 12_000_000)
            write_atomically(local, payload)
        image, reason = decode_figure(payload)
        if image is None:
            return None, reason
        fingerprint = image.convert("L").resize((9, 8)).tobytes()
        signature = sum((fingerprint[y*9+x] > fingerprint[y*9+x+1]) << (y*8+x)
                        for y in range(8) for x in range(8))
        source = {
            "paper_id": paper["id"], "title": paper.get("title"), "doi": paper.get("doi"),
            "image_id": paper["imageId"], "image_path": path, "cache_key": key,
            "sha256": sha256(payload).hexdigest(), "trimmed_size": list(image.size),
        }
        return Figure(source, image, signature), None
    except HTTPError as error:
        return None, f"image_http_{error.code}"
    except (OSError, ValueError) as error:
        return None, f"unusable_{type(error).__name__}"


def collect(origin, topic_id, cache, goal, max_pages, excluded):
    figures, seen_papers, seen_images = [], set(), set()
    skipped = Counter()
    offset = scanned = 0
    total = None
    with ThreadPoolExecutor(max_workers=6) as downloads:
        for _ in range(max_pages):
            query = urlencode({"limit": 100, "offset": offset})
            url = f"{origin}/api/v1/knowledge/topics/{quote(topic_id, safe='')}/papers?{query}"
            try:
                page = json.loads(read_url(url, "application/json", 8_000_000))["data"]
                papers = page["results"]
                total = page["total"]
                if not isinstance(papers, list) or type(total) is not int:
                    raise ValueError("Invalid paper page")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"Could not read topic papers at offset {offset}: {exc}") from exc
            scanned += len(papers)
            eligible = []
            for paper in papers:
                paper_id, image_id = paper.get("id"), paper.get("imageId")
                if not isinstance(paper_id, str) or not safe_image_path(image_id):
                    skipped["no_image"] += 1
                elif image_id in excluded:
                    skipped["reviewed_non_figure"] += 1
                elif paper_id in seen_papers or image_id in seen_images:
                    skipped["duplicate_source"] += 1
                else:
                    seen_papers.add(paper_id)
                    seen_images.add(image_id)
                    eligible.append(paper)
            for start in range(0, len(eligible), 6):
                # Retain API order while limiting downloads once enough candidates are available.
                for figure, reason in downloads.map(lambda p: load_figure(origin, p, cache), eligible[start:start+6]):
                    if figure is None:
                        skipped[reason] += 1
                    elif any((figure.signature ^ previous.signature).bit_count() <= 4 for previous in figures):
                        skipped["duplicate_figure"] += 1
                    else:
                        figures.append(figure)
                if len(figures) >= goal:
                    break
            print(f"{topic_id}: scanned {scanned}/{total}, accepted {len(figures)}", flush=True)
            offset += len(papers)
            if len(figures) >= goal or not papers or offset >= total:
                break
    return figures[:goal], skipped


def split_pixels(total, weights):
    """Allocate integer widths or heights whose sum exactly equals total."""
    scale = total / sum(weights)
    edges = [0]
    cumulative = 0
    for weight in weights[:-1]:
        cumulative += weight
        edges.append(round(cumulative * scale))
    edges.append(total)
    return [right - left for left, right in zip(edges, edges[1:])]


def retained(ratio, width, height):
    target = width / height
    return min(ratio / target, target / ratio)


def visual_profile(image):
    # The preview sizes bracket the scale at which marks appear on a card.
    small = ImageOps.contain(image, (160, 105), Image.Resampling.LANCZOS)
    gray = small.convert("L")
    fine = ImageStat.Stat(ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(1)))).mean[0] / 255
    broad = gray.filter(ImageFilter.GaussianBlur(3))
    shapes = ImageStat.Stat(broad).stddev[0] / 255
    chroma = [max(r, g, b) - min(r, g, b) for r, g, b in zip(*(band.tobytes() for band in small.split()))]
    color = sum(min(value, 95) for value in chroma) / (95 * len(chroma))
    light = gray.histogram()
    ink = sum(light[:238]) / (small.width * small.height)
    # Reward broad shapes and patches of color; penalize fine edges and blankness.
    preference = 1.25 * min(color, .45) + .55 * min(shapes, .26) - 4 * fine - .55 * max(0, .18 - ink)
    return {"preference": preference, "color": color, "fine_detail": fine, "ink": ink}


def rounded(image, radius):
    # Supersampling keeps the only rounded edge, the outer silhouette, smooth.
    mask = Image.new("L", (image.width * 3, image.height * 3))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width-1, mask.height-1), radius*3, fill=255)
    result = image.convert("RGBA")
    result.putalpha(mask.resize(image.size, Image.Resampling.LANCZOS))
    return result


def write_atomically(output, data):
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_bytes(data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def visible_lane_span(corners, top, bottom):
    """Project the part of the output viewport inside a lane onto its x axis."""
    points = [x for x, y in corners if top <= y <= bottom]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        for boundary in (top, bottom):
            if min(y1, y2) < boundary < max(y1, y2):
                points.append(x1 + (x2-x1) * (boundary-y1) / (y2-y1))
    # Extend past the last visible sample for the bicubic transform.
    return math.floor(min(points))-2, math.ceil(max(points))+2


def diagonal_strips(figures):
    angle = math.radians(LANE_ANGLE)
    c, s = math.cos(angle), math.sin(angle)
    # Output-to-lane transform. Rotation happens once for the entire assembly,
    # so the Figure joins and the lane gaps stay parallel after clipping.
    offset_x = math.ceil((W*c + H*abs(s)) / 2) + 4
    offset_y = math.ceil((H*c + W*abs(s)) / 2) + 4
    tx = offset_x - c*W/2 - s*H/2
    ty = offset_y + s*W/2 - c*H/2
    corners = [(c*x+s*y+tx, -s*x+c*y+ty) for x, y in ((0, 0), (W, 0), (W, H), (0, H))]
    height = math.ceil((2*offset_y - (LANE_COUNT-1)*LANE_GAP) / LANE_COUNT)
    lanes = Image.new("RGB", (2*offset_x, LANE_COUNT*height+(LANE_COUNT-1)*LANE_GAP), LANE_GUTTER)
    tone_curve = [round(47 + .78*value) for value in range(256)] * 3
    profiles = [visual_profile(figure.image) for figure in figures]
    remaining = set(range(len(figures)))
    papers = Counter()
    tiles = []
    # Stagger the Figure joins across lanes so they don't read as columns.
    for lane, lane_weights in enumerate(LANE_WEIGHTS):
        y = lane * (height + LANE_GAP)
        x, end = visible_lane_span(corners, y, y+height)
        widths = split_pixels(end-x-(len(lane_weights)-1)*FIGURE_GAP, lane_weights)
        for width in widths:
            def cost(index):
                figure, profile = figures[index], profiles[index]
                keep = retained(figure.ratio, width, height)
                return (.8 * math.log(keep)**2 - 1.6 * profile["preference"]
                        + .30 * papers[figure.source["paper_id"]], index)

            index = min(remaining, key=cost)
            remaining.remove(index)
            figure = figures[index]
            papers[figure.source["paper_id"]] += 1
            tile = ImageOps.fit(figure.image, (width, height), Image.Resampling.LANCZOS)
            tile = ImageEnhance.Color(tile).enhance(.82)
            # Lift shadows and cap white against the same neutral point for
            # every Figure, then apply the light sage tint.
            tile = tile.point(tone_curve)
            tint = Image.new("RGB", tile.size, "#e5eadb")
            lanes.paste(Image.blend(tile, tint, .18), (x, y))
            tiles.append({"paper_id": figure.source["paper_id"], "image_id": figure.source["image_id"],
                          "lane": lane+1, "box_in_lane_canvas": [x, y, width, height],
                          "retained_fraction_before_viewport": round(retained(figure.ratio, width, height), 3)})
            x += width + FIGURE_GAP
    cover = lanes.transform((W, H), Image.Transform.AFFINE, (c, s, tx, -s, c, ty),
                            Image.Resampling.BICUBIC, fillcolor=LANE_GUTTER)
    return rounded(cover, 22), {
        "angle_degrees": LANE_ANGLE, "lane_count": LANE_COUNT, "lane_gap_px": LANE_GAP,
        "figure_gap_px": FIGURE_GAP, "tint_opacity": .18, "count": len(tiles), "tiles": tiles,
    }


def cover_filename(topic_id):
    match = re.fullmatch(r"openalex:topic:(T[0-9]+)", topic_id)
    if not match:
        raise ValueError(f"Invalid OpenAlex Topic ID: {topic_id!r}")
    return f"{match[1]}.webp"


def catalog_topics(origin):
    data = json.loads(read_url(f"{origin}/api/v1/knowledge/topics", "application/json", 8_000_000))["data"]
    topic_ids = [item["id"] for item in data["items"]]
    names = {cover_filename(topic_id) for topic_id in topic_ids}
    if not topic_ids or len(topic_ids) != len(names) or len(topic_ids) != data["total"]:
        raise ValueError("Topic catalog is empty, incomplete, or contains duplicate IDs")
    return topic_ids


def generate_topic(args, origin, topic_id, excluded):
    output = args.output_dir / cover_filename(topic_id)
    if args.skip_existing and output.is_file():
        try:
            with Image.open(output) as existing:
                if existing.format == "WEBP" and existing.size == (W, H):
                    existing.load()
                    return "existing"
        except OSError:
            pass
    figures, skipped = collect(origin, topic_id, args.cache, args.candidates, args.max_pages, excluded)
    if len(figures) < REQUIRED_FIGURES:
        raise ValueError(f"Found only {len(figures)} of {REQUIRED_FIGURES} required figures (skipped: {dict(skipped)})")
    cover, layout = diagonal_strips(figures)
    data = BytesIO()
    cover.save(data, "WEBP", quality=91, method=5)
    write_atomically(output, data.getvalue())
    sources = "\n".join(f"  lane {tile['lane']}: {tile['paper_id']} {tile['image_id']}" for tile in layout["tiles"])
    print(f"{topic_id} -> {output}\n{sources}", flush=True)
    return "generated"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--topic", help="OpenAlex Topic ID, e.g. openalex:topic:T10028")
    scope.add_argument("--all", action="store_true", help="Generate covers for the current Topic catalog")
    parser.add_argument("--origin", default="http://localhost:3000")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--cache", type=Path, default=Path(gettempdir()) / "shenzhi-topic-cover-cache")
    parser.add_argument("--candidates", type=int, default=32, choices=range(REQUIRED_FIGURES, 41), metavar="8–40")
    parser.add_argument("--max-pages", type=int, default=12)
    parser.add_argument("--jobs", type=int, default=4, choices=range(1, 9), metavar="1–8")
    parser.add_argument("--skip-existing", action="store_true", help="Keep existing valid covers")
    args = parser.parse_args()

    origin = args.origin.rstrip("/")
    try:
        parsed = urlsplit(origin)
        valid_origin = (parsed.scheme in {"http", "https"} and parsed.hostname
                        and parsed.username is None and not (parsed.path or parsed.query or parsed.fragment))
    except ValueError:
        valid_origin = False
    if not valid_origin or args.max_pages < 1:
        parser.error("Provide an HTTP(S) origin without credentials or a path, and at least one page")

    try:
        topic_ids = catalog_topics(origin) if args.all else [args.topic]
        if not args.all:
            cover_filename(args.topic)
        excluded = json.loads(Path(__file__).with_name("excluded-images.json").read_text(encoding="utf-8"))
        args.cache.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f"{exc}\n")

    print(f"Catalog selection: {len(topic_ids)} Topics", flush=True)
    counts = Counter()
    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        pending = {workers.submit(generate_topic, args, origin, topic_id, excluded): topic_id for topic_id in topic_ids}
        for future in as_completed(pending):
            try:
                counts[future.result()] += 1
            except (OSError, ValueError) as exc:
                counts["failed"] += 1
                print(f"FAILED {pending[future]}: {exc}", flush=True)
    print(f"Total {len(topic_ids)}, generated {counts['generated']}, existing {counts['existing']}, failed {counts['failed']}")
    if counts["failed"]:
        parser.exit(1)


if __name__ == "__main__":
    main()

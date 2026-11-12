"""Render A1 Topic covers from ShenZhi paper figures."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import re
from tempfile import gettempdir
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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def read_url(url, mime, maximum):
    with build_opener(NoRedirect()).open(Request(url, headers={"Accept": mime}), timeout=15) as response:
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
            local.write_bytes(payload)
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
            # executor.map retains API order, regardless of download completion order.
            for figure, reason in downloads.map(lambda p: load_figure(origin, p, cache), eligible):
                if figure is None:
                    skipped[reason] += 1
                elif any((figure.signature ^ previous.signature).bit_count() <= 4 for previous in figures):
                    skipped["duplicate_figure"] += 1
                else:
                    figures.append(figure)
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


def save_cover(image, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "WEBP", quality=91, method=5)


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", required=True, help="OpenAlex Topic ID, e.g. openalex:topic:T10028")
    parser.add_argument("--origin", default="http://localhost:3000")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path(gettempdir()) / "shenzhi-topic-cover-cache")
    parser.add_argument("--candidates", type=int, default=32, choices=range(8, 41), metavar="8–40")
    parser.add_argument("--max-pages", type=int, default=12)
    args = parser.parse_args()

    match = re.fullmatch(r"openalex:topic:(T[0-9]+)", args.topic)
    if not match:
        parser.error("--topic must be an OpenAlex Topic ID such as openalex:topic:T10028")
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
        excluded = json.loads(Path(__file__).with_name("excluded-images.json").read_text(encoding="utf-8"))
        args.cache.mkdir(parents=True, exist_ok=True)
        figures, skipped = collect(origin, args.topic, args.cache, args.candidates, args.max_pages, excluded)
        required = sum(map(len, LANE_WEIGHTS))
        if len(figures) < required:
            raise ValueError(f"Found only {len(figures)} of {required} required figures (skipped: {dict(skipped)})")
        cover, layout = diagonal_strips(figures)
        output = args.output_dir / f"{match[1]}.webp"
        save_cover(cover, output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(f"{args.topic} -> {output}")
    for tile in layout["tiles"]:
        print(f"  lane {tile['lane']}: {tile['paper_id']} {tile['image_id']}")


if __name__ == "__main__":
    main()

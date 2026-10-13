#!/usr/bin/env python3
"""Generate the site's flat, transparent artwork (module icons, pillar illustrations, hero, ports band) with OpenAI's image API.

    OPENAI_API_KEY=... python3 scripts/gen_artwork.py --style-ref path/to/reference.png
    OPENAI_API_KEY=... python3 scripts/gen_artwork.py --only single,space   # regenerate a few

Style: flat, minimal, hand-drawn marker illustration (thick rounded near-black
outlines, warm off-white fills, one flat sage-green accent), no 3D, no
gradients, no text — the "luria-minimal-cover" look, but isolated on a
transparent background so the artwork sits straight on the page.

With --style-ref the reference picture is sent to the images/edits endpoint as
a STYLE ONLY example; without it, images/generations is used. Either way the
key is read from the environment only; never put it in the repo. Each icon is
requested at 1024x1024 with a transparent background; if the model returns an
opaque canvas, the flat background colour is keyed out. The result is trimmed
to its opaque bounds and downscaled to --size (default 360 px).
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "assets" / "modules"

STYLE = (
    "Flat minimalist scientific editorial illustration in a hand-drawn marker style: thick, rounded, slightly "
    "irregular near-black (#141512) outlines; flat warm off-white (#FAF9F3) fills; exactly one flat accent colour, "
    "muted sage green (#858F69), used for a few fills; no other colours. Confident spare marker strokes, not "
    "polished stock-vector art. Absolutely no 3D, shading, gradients, glow, glass, shadows, paper texture, "
    "grain or decorative scenery. No text in any language, no letters, numbers, labels, logos or watermarks. "
    "The drawing is centered, filling about 65% of the canvas with generous empty margin, isolated on a "
    "fully transparent background (no background shape, no card, no circle behind it). Part of a matching "
    "icon family for a bioinformatics software website."
)

MODULES = {
    "align":   "a short DNA double helix drawn as two twisted ribbons with a few transverse rungs",
    "pp":      "a funnel with loose dots entering at the top and a neat single row of dots leaving at the bottom",
    "single":  "a loose cluster of round cells of different sizes, like a UMAP scatter: a few off-white, a few sage green, two touching",
    "space":   "a rounded organic tissue-slice outline tiled inside with a handful of hexagonal spots, some filled sage green",
    "bulk":    "a simple bar chart: four rounded bars of different heights on a baseline, the tallest filled sage green",
    "fm":      "a small network graph of six round nodes joined by short lines forming a rough brain-like outline; two nodes filled sage green",
    "mol":     "a ball-and-stick molecule: five round atoms connected by short rods, one central atom larger and sage green",
    "epi":     "a chromatin fiber: one smooth wavy strand wrapped around three round nucleosome beads, the beads off-white",
    "micro":   "a petri dish seen from above: a circle outline with a few rod-shaped and round microbes inside, some sage green",
    "metabol": "a conical laboratory flask with liquid drawn as a flat sage-green area and two small round bubbles above it",
}

# key -> (output path relative to src/, requested size, output edge/width in px, subject)
ASSETS = {
    **{k: (f"assets/modules/{k}.png", "1024x1024", 360, v) for k, v in MODULES.items()},
    "pillar-api": (
        "assets/art/pillar-api.png", "1024x1024", 420,
        "one rounded square container (off-white fill) holding a small grid of dots, with three different small "
        "shapes outside it on the left — a tiny cell cluster, a tiny tissue blob, a tiny bar chart — each joined to "
        "the container by a short plain line; the container is the single shared data object",
    ),
    "pillar-port": (
        "assets/art/pillar-port.png", "1024x1024", 420,
        "a closed loop of DNA (off-white fill, black outline) on the left and an identical loop filled sage green on "
        "the right, with one single curved arrow from left to right: the same method rebuilt in a new form",
    ),
    "pillar-verify": (
        "assets/art/pillar-verify.png", "1024x1024", 420,
        "two short bar charts side by side with exactly the same bar heights, the left one off-white and the right "
        "one sage green, and a single large rounded check mark drawn above them",
    ),
    "pillar-agent": (
        "assets/art/pillar-agent.png", "1024x1024", 420,
        "a simple rounded robot head (off-white, two round dot eyes) beside a short vertical list of three rounded "
        "bars, the first two bars filled sage green as completed steps and the last one off-white",
    ),
    "hero": (
        "assets/art/hero.png", "1536x1024", 1200,
        "a horizontal composition about unifying data: on the left three stacked small samples — a loose cell "
        "cluster of circles, a rounded tissue blob with a few hexagonal spots, and a short DNA strand — each "
        "connected by a short plain line to one central large rounded square container (off-white) that holds "
        "a grid of dots; from the container one single arrow leads right to a small bar chart and a small "
        "scatter plot. A few sage-green fills for accent. Generous empty margins all round",
    ),
    "hero-tree": (
        "assets/art/hero-tree.png", "1024x1536", 960,
        "a tall, intricate tree as a scientific editorial illustration: the trunk is a DNA double helix rising from "
        "roots drawn as small square grids of dots; many branches spread upward and outward, and each branch ends "
        "in a different object of biological data — a loose cluster of round cells, a rounded tissue slice tiled "
        "with hexagons, a small bar chart, a ball-and-stick molecule, a petri dish with a few microbes, a chromatin "
        "strand with round beads, a conical flask, a small network of connected nodes, a tiny scatter plot; a few "
        "simple leaves filled sage green along the branches; the tree fills most of the height of a portrait canvas "
        "with generous empty margins on every side; richly detailed but with the same calm flat marker style",
    ),
    # Hero cover candidates: landscape 3:2, Chinese ink-wash + loose oil/watercolour washes,
    # very few elements, lots of empty paper on the left for the title. Theme: biology
    # infrastructure for the AI era — the OmicVerse open-source community.
    "cover-1": (
        "assets/art/cover-1.png", "1536x1024", 1536,
        "COVER: one large, loose ink-brush circle (an enso) in the right half of the canvas; inside it, soft "
        "diluted washes suggest a single early embryo or cell with a few orange-ochre cell dots; a handful of "
        "small ink dots drift out of the circle toward the lower left; at the bottom right two small sketched "
        "human figures and one small sketched robot, drawn in a few grey pencil strokes, look up at the circle",
    ),
    "cover-2": (
        "assets/art/cover-2.png", "1536x1024", 1536,
        "COVER: distant ink-wash mountains fading into mist on the right half, their faint ridgelines drawn as "
        "two intertwined strands like a DNA helix; a thin stream of small sage-green and ochre dots flows down "
        "from the mountains into the foreground like a river of data; a tiny arched bridge with two small "
        "human figures and a small robot crossing it; the left half is almost empty cream paper",
    ),
    "cover-3": (
        "assets/art/cover-3.png", "1536x1024", 1536,
        "COVER: a single old pine tree painted in loose ink strokes rising from the bottom right, its needle "
        "clusters replaced by soft clusters of round cells in diluted sage green and a few ochre dots; a pale "
        "wash of a sun behind it; a few cells drift off the branches into the open space on the left; one "
        "small sketched figure and a small robot sit under the tree",
    ),
    "cover-4": (
        "assets/art/cover-4.png", "1536x1024", 1536,
        "COVER: a broad, soft horizontal ink wash like a calm sea on the lower right, with a loose brush-drawn "
        "DNA helix rising from it like a plant stem and opening at the top into a few soft green and ochre "
        "blooms painted as cell clusters; two small sketched human figures and a small robot stand on the "
        "shore at the bottom right; large empty cream paper on the left and top",
    ),
    "ports": (
        "assets/art/ports.png", "1536x1024", 900,
        "a horizontal composition: on the left a closed loop of DNA with black outline and off-white fill; a single "
        "curved arrow leads right to an identical loop filled sage green; beneath the arrow, two short bar charts "
        "with identical bar heights sit side by side with a small equals sign made of two short parallel bars "
        "between them; a small rounded check mark above the right loop. Generous empty margins",
    ),
}


def _multipart(fields: dict, files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----omicverse{uuid.uuid4().hex}"
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for field, path in files:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{path.name}\"\r\n"
                  f"Content-Type: {ctype}\r\n\r\n".encode())
        out.write(path.read_bytes())
        out.write(b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), boundary


def _post(url: str, key: str, data: bytes, content_type: str) -> dict:
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Bearer {key}", "Content-Type": content_type})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(6 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e
    raise RuntimeError("unreachable")


COVER_STYLE = (
    "Painted in the manner of a contemporary Chinese ink-wash painting (shuimo) blended with loose oil and "
    "watercolour washes: soft gradients of diluted black ink and muted sage green with a touch of ochre-orange, "
    "visible brush texture and granulation, wet-into-wet bleeds, confident sparse strokes, large areas of empty "
    "warm cream paper (liubai). Very few elements, calm, spacious, poetic; the eye rests. Landscape format: the "
    "subject sits in the right half and lower part of the canvas, while the left third stays almost empty cream "
    "paper (#FBFAF6) for a title. Absolutely no text, letters, numbers, logos, titles, seals or watermarks. No "
    "photo-realism, no 3D render, no digital gloss, no heavy outlines, no busy detail, no frame."
)


def request_image(model: str, prompt: str, quality: str, key: str, style_ref: Path | None, size: str = "1024x1024", background: str = "transparent") -> bytes:
    if style_ref:
        fields = {"model": model, "prompt": prompt, "n": "1", "size": size,
                  "background": background, "output_format": "png", "quality": quality}
        body, boundary = _multipart(fields, [("image[]", style_ref)])
        data = _post("https://api.openai.com/v1/images/edits", key, body, f"multipart/form-data; boundary={boundary}")
    else:
        body = json.dumps({"model": model, "prompt": prompt, "n": 1, "size": size,
                           "background": background, "output_format": "png", "quality": quality}).encode()
        data = _post("https://api.openai.com/v1/images/generations", key, body, "application/json")
    return base64.b64decode(data["data"][0]["b64_json"])


def key_out_background(im: Image.Image) -> Image.Image:
    """If the model ignored `background: transparent`, make the flat background colour transparent."""
    alpha = im.getchannel("A")
    if alpha.getextrema()[0] < 250:  # already has transparency
        return im
    px = im.load()
    w, h = im.size
    corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    out = Image.new("RGBA", im.size)
    opx = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            d = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2]))
            a = 0 if d < 18 else (255 if d > 60 else int(255 * (d - 18) / 42))
            opx[x, y] = (r, g, b, a)
    return out


def postprocess(png: bytes, edge: int, square: bool) -> Image.Image:
    im = key_out_background(Image.open(io.BytesIO(png)).convert("RGBA"))
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    if square:
        side = max(w, h)
        pad = int(side * 0.06)
        canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
        canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
        return canvas.resize((edge, edge), Image.LANCZOS)
    pad = int(w * 0.03)
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, (pad, pad), im)
    scale = edge / canvas.width
    return canvas.resize((edge, max(1, round(canvas.height * scale))), Image.LANCZOS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-image-2.5-sunburst")
    ap.add_argument("--quality", default="medium")
    ap.add_argument("--size", type=int, default=360, help="output edge length in px")
    ap.add_argument("--only", default=None, help="comma-separated module keys")
    ap.add_argument("--style-ref", type=Path, default=None, help="reference picture sent as STYLE ONLY example")
    ap.add_argument("--raw-dir", type=Path, default=None, help="also keep the untouched 1024px PNGs here")
    args = ap.parse_args()

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2
    keys = [k.strip() for k in args.only.split(",")] if args.only else list(ASSETS)
    if args.raw_dir:
        args.raw_dir.mkdir(parents=True, exist_ok=True)
    for k in keys:
        rel, size, edge, subject = ASSETS[k]
        is_cover = subject.startswith("COVER:")
        t0 = time.time()
        if is_cover:
            prompt = f"Draw {subject[6:].strip()}. " + COVER_STYLE
            png = request_image(args.model, prompt, args.quality, key, None, size, background="opaque")
            if args.raw_dir:
                (args.raw_dir / f"{k}.png").write_bytes(png)
            im = Image.open(io.BytesIO(png)).convert("RGB")
            im = im.resize((edge, round(im.height * edge / im.width)), Image.LANCZOS)
        else:
            prompt = (("Use the attached image for STYLE ONLY (line weight, flat fills, palette, restraint); do not copy "
                       "any of its objects. ") if args.style_ref else "") + f"Draw {subject}. " + STYLE
            png = request_image(args.model, prompt, args.quality, key, args.style_ref, size)
            if args.raw_dir:
                (args.raw_dir / f"{k}.png").write_bytes(png)
            im = postprocess(png, edge, square=(size == "1024x1024"))
        out = ROOT / "src" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if im.mode == "RGB":
            im.save(out, format="JPEG", quality=88, optimize=True, progressive=True) if out.suffix == ".jpg" else im.save(out, optimize=True)
            print(f"[art] {k:<14} {im.width}x{im.height} {out.stat().st_size // 1024:>4} KB  opaque  {time.time() - t0:.0f}s", file=sys.stderr)
            continue
        im.save(out, optimize=True)
        transparent = sum(1 for a in im.getchannel("A").getdata() if a == 0) / (im.width * im.height)
        print(f"[art] {k:<14} {im.width}x{im.height} {out.stat().st_size // 1024:>4} KB  transparent={transparent:.0%}  {time.time() - t0:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generate the transparent module icons in src/assets/modules/ with OpenAI's image API.

    OPENAI_API_KEY=... python3 scripts/gen_module_icons.py --style-ref path/to/reference.png
    OPENAI_API_KEY=... python3 scripts/gen_module_icons.py --only single,space   # regenerate a few

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
    "One compact object centered, filling about 65% of the canvas with generous empty margin, isolated on a "
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


def request_image(model: str, prompt: str, quality: str, key: str, style_ref: Path | None) -> bytes:
    if style_ref:
        fields = {"model": model, "prompt": prompt, "n": "1", "size": "1024x1024",
                  "background": "transparent", "output_format": "png", "quality": quality}
        body, boundary = _multipart(fields, [("image[]", style_ref)])
        data = _post("https://api.openai.com/v1/images/edits", key, body, f"multipart/form-data; boundary={boundary}")
    else:
        body = json.dumps({"model": model, "prompt": prompt, "n": 1, "size": "1024x1024",
                           "background": "transparent", "output_format": "png", "quality": quality}).encode()
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


def postprocess(png: bytes, size: int) -> Image.Image:
    im = key_out_background(Image.open(io.BytesIO(png)).convert("RGBA"))
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    side = max(w, h)
    pad = int(side * 0.06)
    canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
    return canvas.resize((size, size), Image.LANCZOS)


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
    keys = [k.strip() for k in args.only.split(",")] if args.only else list(MODULES)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.raw_dir:
        args.raw_dir.mkdir(parents=True, exist_ok=True)
    for k in keys:
        subject = MODULES[k]
        prompt = (("Use the attached image for STYLE ONLY (line weight, flat fills, palette, restraint); do not copy "
                   "any of its objects. ") if args.style_ref else "") + f"Draw {subject}. " + STYLE
        t0 = time.time()
        png = request_image(args.model, prompt, args.quality, key, args.style_ref)
        if args.raw_dir:
            (args.raw_dir / f"{k}.png").write_bytes(png)
        im = postprocess(png, args.size)
        out = OUT / f"{k}.png"
        im.save(out, optimize=True)
        transparent = sum(1 for a in im.getchannel("A").getdata() if a == 0) / (im.width * im.height)
        print(f"[icons] {k:<8} {out.stat().st_size // 1024:>4} KB  transparent={transparent:.0%}  {time.time() - t0:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

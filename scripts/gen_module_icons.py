#!/usr/bin/env python3
"""Generate the transparent module icons in src/assets/modules/ with OpenAI's image API.

    OPENAI_API_KEY=... python3 scripts/gen_module_icons.py --model gpt-image-2.5-sunburst
    OPENAI_API_KEY=... python3 scripts/gen_module_icons.py --only single,space   # regenerate a few

The key is read from the environment only; never put it in the repo.
Each icon is requested as a 1024x1024 PNG with a transparent background,
trimmed to its opaque bounds and downscaled to --size (default 360 px).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "assets" / "modules"

STYLE = (
    "A single flat vector icon in a modern minimal style with subtle depth: smooth two-tone gradients, "
    "soft rounded geometry, no outlines, no text, no labels, no background shapes, no frame, no shadow on the "
    "ground. Centered, filling about 70% of the canvas, generous empty margin. Isolated on a fully transparent "
    "background. Palette: {color} as the main hue with a lighter tint of the same hue, plus small cream "
    "(#fbfaf6) highlights. Consistent with a matching icon family for a bioinformatics software website."
)

MODULES = {
    "align":   ("#2f8f45", "a stylised DNA double helix with a few nucleotide bars, slightly tilted"),
    "pp":      ("#1f7a36", "a funnel filtering scattered dots into a clean ordered stream below it"),
    "single":  ("#345aa8", "a cluster of round cells of different sizes, like a UMAP scatter, with a few connecting arcs"),
    "space":   ("#8848a4", "a tissue slice seen from above, a rounded organic shape tiled with small hexagonal spots in two shades"),
    "bulk":    ("#d9712b", "a bar chart of four rounded bars rising left to right with a small trend arrow"),
    "fm":      ("#347ec4", "a neural network node graph: a few connected glowing nodes forming a small brain-like shape"),
    "mol":     ("#2d7a4b", "a 3D molecule: five spheres connected by short rods, ball-and-stick model"),
    "epi":     ("#34418f", "a chromatin fiber: a smooth wavy strand wrapped around three round nucleosome beads"),
    "micro":   ("#d73986", "a petri dish seen from above with a few rod-shaped and round microbes inside"),
    "metabol": ("#7f48a6", "a conical laboratory flask with liquid and two rising bubbles, next to a tiny hexagon"),
}


def request_image(model: str, prompt: str, size: str, quality: str, key: str) -> bytes:
    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "background": "transparent",
        "output_format": "png",
        "quality": quality,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode())
            return base64.b64decode(data["data"][0]["b64_json"])
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(6 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg}") from e
    raise RuntimeError("unreachable")


def postprocess(png: bytes, size: int) -> Image.Image:
    im = Image.open(__import__("io").BytesIO(png)).convert("RGBA")
    alpha = im.getchannel("A")
    bbox = alpha.point(lambda a: 255 if a > 8 else 0).getbbox()
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
        color, subject = MODULES[k]
        prompt = f"{subject}. " + STYLE.format(color=color)
        t0 = time.time()
        png = request_image(args.model, prompt, "1024x1024", args.quality, key)
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

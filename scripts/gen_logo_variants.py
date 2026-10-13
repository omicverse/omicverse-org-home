#!/usr/bin/env python3
"""Simplified variants of the existing OmicVerse logo (sent to images/edits as the reference).

    OPENAI_API_KEY=... python3 scripts/gen_logo_variants.py --ref current-logo.png --out src/assets/art
"""
import argparse, os, sys, time, io
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_artwork import request_image, key_out_background  # noqa: E402

BASE = ("Redesign the attached logo as a SIMPLER version of itself. Keep its identity: a vertical DNA double helix "
        "with a leaf at the top, in the same fresh green family (two flat greens at most, #4f9a2f and #7cc242). "
        "Flat vector shapes, no gradients, no shading, no outlines, no text, no background shape. The mark must "
        "stay readable at 28 pixels: bold simple shapes, generous counters, nothing thinner than the helix strand. "
        "Isolated on a fully transparent background, centered, filling about 75% of the canvas. ")
VARIANTS = {
    "logo-v1": "Remove the orbit arcs and all scattered dots. Keep only the helix with four rungs and one leaf at the top.",
    "logo-v2": "Remove the orbit arcs and all dots. Keep the helix (three rungs) and ONE leaf at the top, and make the two strands two slightly different greens.",
    "logo-v3": "Reduce to a single solid green glyph: a compact helix of two strands with two rungs, the top of one strand ending in one leaf. No dots, no arcs.",
    "logo-v4": "Keep one thin orbit arc behind the helix as a simple single curve, remove all dots and the lower leaves; one leaf at the top; two greens.",
}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("src/assets/art"))
    ap.add_argument("--model", default="gpt-image-2.5-sunburst")
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    key = os.environ["OPENAI_API_KEY"]
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ([n.strip() for n in args.only.split(",")] if args.only else VARIANTS):
        t0 = time.time()
        png = request_image(args.model, BASE + VARIANTS[name], "high", key, args.ref, "1024x1024")
        im = key_out_background(Image.open(io.BytesIO(png)).convert("RGBA"))
        bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if bbox:
            im = im.crop(bbox)
        side = max(im.size); pad = int(side * 0.08)
        canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
        canvas.paste(im, ((canvas.width - im.width) // 2, (canvas.height - im.height) // 2), im)
        canvas = canvas.resize((512, 512), Image.LANCZOS)
        out = args.out / f"{name}.png"; canvas.save(out, optimize=True)
        print(f"[logo] {name} {out.stat().st_size // 1024} KB {time.time() - t0:.0f}s", file=sys.stderr)

if __name__ == "__main__":
    main()

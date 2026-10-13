#!/usr/bin/env python3
"""Cut the brand mark into the sizes the site uses.

    python3 scripts/make_brand.py src/assets/art/logo-1.png

Writes src/assets/brand/mark.png (256 px, header/footer), favicon-32.png,
favicon-180.png (apple touch, on cream) and mark.svg (the 256 px raster
wrapped in SVG). The source should be a square transparent PNG.
"""
import base64
import io
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "assets" / "brand"


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    im = im.crop(bbox) if bbox else im
    side = max(im.size)
    pad = int(side * 0.08)
    canvas = Image.new("RGBA", (side + 2 * pad, side + 2 * pad), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - im.width) // 2, (canvas.height - im.height) // 2), im)
    return canvas


def main(src: str) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    im = trim(Image.open(src).convert("RGBA"))
    mark = im.resize((256, 256), Image.LANCZOS)
    mark.save(OUT / "mark.png", optimize=True)
    im.resize((32, 32), Image.LANCZOS).save(OUT / "favicon-32.png", optimize=True)
    touch = Image.new("RGBA", (180, 180), (251, 250, 246, 255))
    inner = im.resize((150, 150), Image.LANCZOS)
    touch.paste(inner, (15, 15), inner)
    touch.convert("RGB").save(OUT / "favicon-180.png", optimize=True)
    # mark.svg is the true vector (scripts/logo: vtracer of the brand PNG, rotated -20°); it is not overwritten here.
    for p in sorted(OUT.iterdir()):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

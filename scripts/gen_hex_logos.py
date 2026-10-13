#!/usr/bin/env python3
"""Generate flat hand-drawn hex stickers for every port repo.

    OPENAI_API_KEY=... python3 scripts/gen_hex_logos.py --style-ref ref.png --out /tmp/hex-logos --only py-limma,rust-NMF
    OPENAI_API_KEY=... python3 scripts/gen_hex_logos.py --style-ref ref.png --out /tmp/hex-logos            # all 70

For each repo a pictogram that depicts what the package does is generated with
OpenAI's image API (same flat style as the homepage artwork: thick near-black
outlines, warm off-white fills, one sage-green accent, transparent background).
The hexagon frame and the package name are then composed locally with Pillow so
all stickers share identical geometry and typography.

Outputs per repo in <out>/<repo>/: logo.png (512 px) and logo.svg (the same
raster wrapped in an SVG so existing <img src="logo/logo.svg"> links keep
working), plus <out>/contact-sheet.png.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_artwork import STYLE, key_out_background, request_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Medium.ttf"
INK = (20, 21, 18, 255)
PAPER = (250, 249, 243, 255)
SAGE = (133, 143, 105, 255)

SUBJECTS = {
    "py-Augur":        "a three-step podium with one round cell standing on the top step",
    "py-CellCall":     "two round cells facing each other with a dashed curved signal between them",
    "py-CopyKAT":      "an X-shaped chromosome with one arm segment filled sage green",
    "py-DEqMS":        "a short chain of round peptide beads next to a tiny bar chart",
    "py-DoubletFinder": "two overlapping round cells with a small magnifying glass over them",
    "py-MARVEL":       "a gene drawn as four exon boxes on a line, with an arc skipping the second box",
    "py-MSstats":      "a mass spectrum: several vertical spikes of different heights on a baseline",
    "py-Monocle3":     "a smooth trajectory line that forks into two branches, with small dots along it",
    "py-OlinkAnalyze": "a microplate grid of round wells, a few wells filled sage green",
    "py-SCEVAN":       "two groups of round cells separated by a dashed line, one group filled sage green",
    "py-SCORPIUS":     "a single smooth curved line passing through scattered dots",
    "py-SPATA2":       "a tissue-slice outline with one contour line and a few dots inside",
    "py-SPLIT":        "a circle splitting into an off-white half and a sage-green half with a small gap between",
    "py-Scissors":     "a pair of scissors cutting through a small cluster of dots",
    "py-SigXTalk":     "two curved lines crossing each other with a round node at the crossing point",
    "py-Slingshot":    "a Y-shaped slingshot with a curve of dots running up through both arms",
    "py-SpaceTrooper": "a grid of round spots with a magnifying glass over one spot",
    "py-Statial":      "two round cells with a double-headed arrow between them inside a tissue outline",
    "py-TSCAN":        "a chain of round nodes connected by lines with one side branch (a spanning tree)",
    "py-TranspaceR":   "a grid of spots with a rising wavy curve drawn over it",
    "py-URD":          "an upward branching tree with a thick root and small round tips",
    "py-alakazam":     "a Y-shaped antibody with two round tips",
    "py-cca":          "two overlapping ellipses with a small arrow pulling them together",
    "py-cellAdmix":    "a large round cell with a smaller cell overlapping its edge and a dashed line between them",
    "py-coloc":        "two overlapping tall peaks rising from the same point on a baseline",
    "py-condiments":   "two branching curves side by side with a double-headed arrow between them",
    "py-dada2":        "a row of five small boxes with one box replaced by a sage-green corrected box",
    "py-dcHiC":        "a square map with a diagonal of dark blocks like a checkerboard of two compartments",
    "py-decontx":      "a round cell with loose dots around it and an arrow sweeping the dots away",
    "py-destiny":      "a curved sweep of dots going from dense on the left to sparse on the right",
    "py-dowser":       "a small bifurcating phylogenetic tree with four leaves",
    "py-dynbenchmark": "a branching curve beside a vertical bar scale with a tick",
    "py-dyneval":      "two overlaid trajectory curves with a check mark",
    "py-dynwrap":      "a branching trajectory curve inside a rounded rectangle",
    "py-edgeR":        "a histogram of bars with a smooth skewed curve over it",
    "py-fastcar":      "a teardrop droplet containing one round cell, with small loose dots outside the droplet",
    "py-funkyheatmap": "a small grid where cells are circles of different sizes, some sage green",
    "py-gliph":        "three Y-shaped receptors grouped together by a curly bracket",
    "py-hdWGCNA":      "a network with one large hub node connected to many small nodes",
    "py-hoodscanr":    "a central round cell with a dashed circular ring around it and neighbor cells inside the ring",
    "py-immunarch":    "a column of horizontal bars of different lengths next to a Y-shaped receptor",
    "py-imputeLCMD":   "a matrix grid with a few empty cells and an arrow filling one of them",
    "py-inferCNV":     "a horizontal band divided into segments, some filled sage green and some off-white",
    "py-ldsc":         "scattered dots with a straight rising regression line through them",
    "py-limma":        "a straight fitted line passing through scattered dots",
    "py-lipidr":       "a lipid: a round head with two wavy tails",
    "py-matrixeqtl":   "a small diamond connected by a line to a short bar inside a grid",
    "py-mclustR":      "two overlapping bell curves, one filled sage green",
    "py-mfuzz":        "several overlapping wavy time-series curves rising and falling together",
    "py-miloR":        "a network of nodes with a circle drawn around a small neighborhood of them",
    "py-monocle2":     "a Y-shaped branching tree of dots",
    "py-nichede":      "a central cell surrounded by a ring of different smaller cells",
    "py-proDA":        "a bar chart where two bars are dashed outlines (missing values)",
    "py-sccdc":        "a round cell with a few stray dots inside and a small wavy flag above it",
    "py-scDblFinder":  "two fused round cells with a small flag planted on top",
    "py-scdrs":        "a tall peak above a small cluster of round cells",
    "py-scmetabolism": "a round cell with a ring of three curved arrows inside it",
    "py-scoper":       "small Y-shaped receptors grouped into two circles",
    "py-shazam":       "a Y-shaped receptor with small tick marks along its arms",
    "py-soupx":        "a bowl holding small dots like soup, with one round cell floating above it",
    "py-spanorm":      "a wavy surface on the left becoming a flat line on the right, over a grid of spots",
    "py-spotsweeper":  "a grid of round spots with a broom sweeping two spots out",
    "py-susie":        "one tall peak among small peaks with a bracket under the tall one",
    "py-tigger":       "a gene segment line with one box marked by a small star",
    "py-tradeSeq":     "two smooth expression curves along the same trajectory line",
    "py-twas":         "a gene box, an arrow to a bar, and an arrow to a diamond in a row",
    "py-twosamplemr":  "a diamond, an arrow to a circle, and an arrow to a square in a row",
    "rust-NMF":        "a large rectangle, an equals sign, and two smaller rectangles side by side",
    "rust-bandnorm":   "a square map with stripes parallel to its diagonal",
    "rust-scHiCluster": "a triangular contact map with a few clustered dots inside",
}


def ensure_font(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "IBMPlexMono-Medium.ttf"
    if not path.exists():
        urllib.request.urlretrieve(FONT_URL, path)
    return path


def hexagon(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """Pointy-top regular hexagon (the R sticker orientation)."""
    return [(cx + r * math.cos(math.radians(60 * i - 90)), cy + r * math.sin(math.radians(60 * i - 90))) for i in range(6)]


def compose(pictogram: Image.Image, name: str, font_path: Path, size: int = 1024) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = size / 2, size / 2, size * 0.455
    pts = hexagon(cx, cy, r)
    d.polygon(pts, fill=PAPER)
    stroke = int(size * 0.022)
    d.line(pts + [pts[0]], fill=INK, width=stroke, joint="curve")
    # pictogram: centred in the wide middle band of the hexagon
    box_w, box_h = size * 0.58, size * 0.42
    pic = pictogram.copy()
    pic.thumbnail((int(box_w), int(box_h)), Image.LANCZOS)
    px, py = int(cx - pic.width / 2), int(size * 0.21 + (box_h - pic.height) / 2)
    im.paste(pic, (px, py), pic)
    # thin sage rule + name, kept inside the tapering lower part of the hexagon
    rule_y = int(size * 0.675)
    d.line([(cx - size * 0.14, rule_y), (cx + size * 0.14, rule_y)], fill=SAGE, width=int(size * 0.011))
    label = name
    fsize = int(size * 0.066)
    while fsize > 18:
        font = ImageFont.truetype(str(font_path), fsize)
        bbox = d.textbbox((0, 0), label, font=font)
        if bbox[2] - bbox[0] <= size * 0.50:
            break
        fsize -= 2
    tw = bbox[2] - bbox[0]
    d.text((cx - tw / 2 - bbox[0], size * 0.70), label, font=font, fill=INK)
    return im


def to_svg(png: Image.Image) -> str:
    buf = io.BytesIO()
    png.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {png.width} {png.height}" width="{png.width}" height="{png.height}">'
            f'<image width="{png.width}" height="{png.height}" xlink:href="data:image/png;base64,{b64}"/></svg>')


def quantize(im: Image.Image, colors: int = 96) -> Image.Image:
    """Palette-quantize while keeping the alpha channel intact (small, flat PNGs)."""
    rgb = im.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGBA")
    rgb.putalpha(im.getchannel("A"))
    return rgb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--style-ref", type=Path, default=None)
    ap.add_argument("--model", default="gpt-image-2.5-sunburst")
    ap.add_argument("--quality", default="medium")
    ap.add_argument("--only", default=None)
    ap.add_argument("--reuse", action="store_true", help="skip repos whose pictogram.png already exists in --out")
    args = ap.parse_args()

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set", file=sys.stderr)
        return 2
    font = ensure_font(args.out / "_font")
    names = [n.strip() for n in args.only.split(",")] if args.only else list(SUBJECTS)
    done = []
    for name in names:
        subject = SUBJECTS[name]
        rdir = args.out / name
        rdir.mkdir(parents=True, exist_ok=True)
        raw = rdir / "pictogram.png"
        t0 = time.time()
        if not (args.reuse and raw.exists()):
            prompt = (("Use the attached image for STYLE ONLY (line weight, flat fills, palette, restraint); do not copy "
                       "any of its objects. ") if args.style_ref else "") + f"Draw {subject}. " + STYLE
            png = request_image(args.model, prompt, args.quality, key, args.style_ref, "1024x1024")
            raw.write_bytes(png)
        pic = key_out_background(Image.open(raw).convert("RGBA"))
        bbox = pic.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if bbox:
            pic = pic.crop(bbox)
        sticker = compose(pic, name, font)
        small = quantize(sticker.resize((512, 512), Image.LANCZOS))
        small.save(rdir / "logo.png", optimize=True)
        (rdir / "logo.svg").write_text(to_svg(small))
        done.append(name)
        print(f"[hex] {name:<18} png={(rdir / 'logo.png').stat().st_size // 1024:>3} KB svg={(rdir / 'logo.svg').stat().st_size // 1024:>3} KB  {time.time() - t0:.0f}s", file=sys.stderr)

    # contact sheet of everything present in --out
    stickers = sorted(p for p in args.out.glob("*/logo.png"))
    if stickers:
        cols = 10
        rows = math.ceil(len(stickers) / cols)
        cell = 180
        sheet = Image.new("RGBA", (cols * cell + 20, rows * cell + 20), (251, 250, 246, 255))
        for i, p in enumerate(stickers):
            t = Image.open(p).convert("RGBA").resize((cell - 10, cell - 10), Image.LANCZOS)
            sheet.paste(t, (10 + (i % cols) * cell, 10 + (i // cols) * cell), t)
        sheet.save(args.out / "contact-sheet.png")
    json.dump(done, open(args.out / "_done.json", "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

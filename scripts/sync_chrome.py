#!/usr/bin/env python3
"""Keep the site header / footer / asset cache-busters identical on every page.

    python3 scripts/sync_chrome.py          # rewrite src/**/*.html in place
    python3 scripts/sync_chrome.py --check  # exit 1 if any page is out of date

`build_blog.py` imports `header_html` / `footer_html` from here so generated
blog pages get the same chrome.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# Bump when styles.css / script.js / ports.js change in a way cached clients must pick up.
ASSET_VERSION = "2026-10-13a"

NAV = [
    ("packages", "Packages", "packages.html"),
    ("ports", "Ports", "ports.html"),
    ("learn", "Learn", "https://omicverse.readthedocs.io/"),
    ("blog", "Blog", "blog.html"),
    ("people", "People", "people.html"),
    ("about", "About", "about.html"),
    ("join", "Join", "join.html"),
]

FOOTER_COLUMNS = [
    ("Project", [
        ("Packages", "packages.html"),
        ("R-port catalog", "ports.html"),
        ("Documentation", "https://omicverse.readthedocs.io/"),
        ("Blog", "blog.html"),
    ]),
    ("Community", [
        ("People", "people.html"),
        ("Events", "events.html"),
        ("Join", "join.html"),
        ("Discussions ↗", "https://github.com/omicverse/omicverse/discussions"),
    ]),
    ("Resources", [
        ("About & citation", "about.html"),
        ("Porting protocol ↗", "https://github.com/omicverse/omicverse-rebuildr"),
        ("Tutorials ↗", "https://github.com/omicverse/omicverse-tutorials"),
        ("GitHub ↗", "https://github.com/omicverse"),
    ]),
]


def _href(href: str, prefix: str) -> str:
    return href if href.startswith("http") else prefix + href


def header_html(current: str | None, prefix: str = "") -> str:
    links = []
    for key, label, href in NAV:
        cur = ' aria-current="page"' if key == current else ""
        ext = ' target="_blank" rel="noopener"' if href.startswith("http") and key != "learn" else ""
        links.append(f'      <a{cur} href="{_href(href, prefix)}"{ext}>{label}</a>')
    links.append('      <a class="nav-cta" href="https://github.com/omicverse" target="_blank" rel="noopener"><svg class="nav-gh" viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>GitHub</a>')
    return f'''  <header class="site-header">
    <a class="brand" href="{prefix}index.html" aria-label="OmicVerse home">
      <img class="brand-logo" src="{prefix}assets/omicos-logo.png" alt="" />
      <span>OmicVerse</span>
    </a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-links">Menu</button>
    <nav class="nav-links" id="nav-links" aria-label="Primary navigation">
{chr(10).join(links)}
    </nav>
  </header>'''


def footer_html(prefix: str = "") -> str:
    cols = []
    for title, items in FOOTER_COLUMNS:
        ext = ' target="_blank" rel="noopener"'
        lis = "".join(
            f'<li><a href="{_href(h, prefix)}"{ext if h.startswith("http") else ""}>{t}</a></li>'
            for t, h in items
        )
        cols.append(f'      <div class="footer-col"><span class="footer-col-title">{title}</span><ul>{lis}</ul></div>')
    return f'''  <footer class="footer">
    <div class="footer-inner page-width wide">
      <div class="footer-brand-col">
        <span class="footer-brand"><img src="{prefix}assets/omicos-logo.png" alt="" /> OmicVerse</span>
        <p>Open-source multi-omics in Python, with Rust and Torch underneath. Trusted R methods, rebuilt and verified.</p>
        <p class="footer-install"><code>pip install omicverse</code></p>
      </div>
{chr(10).join(cols)}
    </div>
    <div class="footer-bottom page-width wide">
      <span>© OmicVerse contributors · Apache-2.0</span>
      <span>Built with <a href="https://github.com/omicverse/omicverse-org-home" target="_blank" rel="noopener">omicverse-org-home</a></span>
    </div>
  </footer>'''


HEADER_RE = re.compile(r"  <header class=\"site-header\">.*?</header>", re.S)
FOOTER_RE = re.compile(r"  <footer class=\"footer[^\"]*\">.*?</footer>", re.S)
ASSET_RE = re.compile(r'((?:href|src)="(?:\.\./)?(?:styles\.css|script\.js|ports\.js))(?:\?v=[^"]*)?"')


def current_key(path: Path) -> str | None:
    if path.parent.name == "blog" or path.stem == "blog":
        return "blog"
    return {"index": None, "packages": "packages", "ports": "ports", "people": "people",
            "about": "about", "join": "join", "events": None}.get(path.stem)


def render(path: Path, text: str) -> str:
    prefix = "../" if path.parent != SRC else ""
    text = HEADER_RE.sub(lambda m: header_html(current_key(path), prefix), text, count=1)
    text = FOOTER_RE.sub(lambda m: footer_html(prefix), text, count=1)
    text = ASSET_RE.sub(lambda m: f'{m.group(1)}?v={ASSET_VERSION}"', text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    pages = sorted(p for p in SRC.rglob("*.html") if "nav-links" in p.read_text())
    stale = []
    for p in pages:
        old = p.read_text()
        new = render(p, old)
        if new != old:
            stale.append(p)
            if not args.check:
                p.write_text(new)
    if args.check:
        for p in stale:
            print(f"out of date: {p.relative_to(ROOT)}")
        return 1 if stale else 0
    print(f"[chrome] {len(stale)} of {len(pages)} pages rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())

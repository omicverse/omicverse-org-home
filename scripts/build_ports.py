#!/usr/bin/env python3
"""Build the R-port catalog (src/assets/ports.json) from the omicverse GitHub org.

For every `py-*` / `rust-*` repository the script looks for a machine-readable
`port.yaml` at the repo root (see docs/PORT_MANIFEST.md).  When a repo has one,
it is the single source of truth.  When it does not, the script *infers* a
best-effort record from what the rebuildr protocol already leaves behind:

  * README.md          -> "What's included" Python <-> R mapping table(s)
  * AUDIT.md           -> r_function_audit coverage table (exported R functions)
  * data/manifest.yaml -> pre-registered parity gate (algorithm class, outputs)
  * pyproject.toml     -> PyPI name, import name, version, license
  * repo description   -> upstream name / source / citation

Inferred records are flagged `"source": "inferred"` so the website can show a
"metadata auto-extracted - add port.yaml to curate" hint.

Usage
-----
    # token from $GITHUB_TOKEN, or `gh auth token` when gh is installed
    python scripts/build_ports.py --out src/assets/ports.json

    # dev loop: cache every API response so re-runs are instant
    python scripts/build_ports.py --cache /tmp/ports-cache --out src/assets/ports.json

    # write a draft port.yaml per repo (to seed PRs into the port repos)
    python scripts/build_ports.py --cache /tmp/ports-cache --scaffold /tmp/port-yaml-drafts

    # restrict to a few repos while debugging the heuristics
    python scripts/build_ports.py --cache /tmp/ports-cache --only py-limma,py-edgeR --out /tmp/p.json
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
ORG = "omicverse"
PORT_RE = re.compile(r"^(py|rust)-", re.I)
PORT_FILE_CANDIDATES = ("port.yaml", "port.yml", ".omicverse/port.yaml")
SCHEMA_VERSION = "omicverse-ports/v1"

DOMAINS = {
    "single-cell": "Single-cell",
    "spatial": "Spatial",
    "trajectory": "Trajectory",
    "bulk": "Bulk",
    "proteomics": "Proteomics",
    "metabolomics": "Metabolomics",
    "genetics": "Genetics",
    "immune": "Immune repertoire",
    "microbiome": "Microbiome",
    "hic": "Hi-C / 3D genome",
    "stats": "Statistics",
    "visualization": "Visualization",
    "other": "Other",
}

STATUS_VALUES = ("ported", "partial", "planned", "skipped")
PARITY_VALUES = ("exact", "approx", "behavioural", "none")


# --------------------------------------------------------------------------- #
# GitHub client (tiny, cached)                                                #
# --------------------------------------------------------------------------- #

class GitHub:
    def __init__(self, token: str | None, cache_dir: Path | None, verbose: bool = False):
        self.token = token
        self.cache_dir = cache_dir
        self.verbose = verbose
        self.calls = 0
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path | None:
        if not self.cache_dir:
            return None
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")

    def get(self, path: str, params: dict | None = None, allow_404: bool = False):
        url = path if path.startswith("http") else f"{API}/{path.lstrip('/')}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        cp = self._cache_path(url)
        if cp and cp.exists():
            data = json.loads(cp.read_text())
            return None if data == {"__404__": True} else data
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "omicverse-org-home/build_ports",
            **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
        })
        self.calls += 1
        if self.verbose:
            print(f"  GET {url}", file=sys.stderr)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404 and allow_404:
                if cp:
                    cp.write_text(json.dumps({"__404__": True}))
                return None
            body = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"GitHub {e.code} for {url}: {body}") from e
        if cp:
            cp.write_text(json.dumps(data))
        return data

    def paginate(self, path: str, params: dict | None = None) -> list:
        out: list = []
        page = 1
        while True:
            chunk = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < 100:
                break
            page += 1
        return out

    def file_text(self, repo: str, path: str, ref: str | None = None) -> str | None:
        params = {"ref": ref} if ref else None
        data = self.get(f"repos/{ORG}/{repo}/contents/{path}", params, allow_404=True)
        if not data or data.get("encoding") != "base64":
            return None
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None

    def tree(self, repo: str, ref: str) -> list[str]:
        data = self.get(f"repos/{ORG}/{repo}/git/trees/{ref}", {"recursive": "1"}, allow_404=True)
        if not data:
            return []
        return [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]


def resolve_token() -> str | None:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    try:
        tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
        return tok or None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Markdown helpers                                                            #
# --------------------------------------------------------------------------- #

CODE_SPAN = re.compile(r"`([^`]+)`")
MD_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
SEP_CELL = re.compile(r"^:?-{2,}:?$")
EMPTY_CELLS = {"", "-", "—", "–", "n/a", "na", "none", "null", "—"}


def split_row(line: str) -> list[str]:
    line = line.strip()
    line = line.replace("\\|", "\x00")
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.replace("\x00", "|").strip() for c in line.split("|")]


def parse_md_tables(md: str) -> list[dict]:
    """Return every GFM table as {"header": [...], "rows": [[...], ...], "section": str}."""
    tables: list[dict] = []
    cur: list[str] = []
    section = ""
    in_code = False

    def flush():
        nonlocal cur
        if len(cur) >= 2:
            rows = [split_row(r) for r in cur]
            sep = rows[1]
            if all(SEP_CELL.match(c) for c in sep if c) and any(sep):
                tables.append({"header": rows[0], "rows": rows[2:], "section": section})
        cur = []

    for raw in md.splitlines() + [""]:
        s = raw.strip()
        if s.startswith("```"):
            in_code = not in_code
            flush()
            continue
        if in_code:
            continue
        if s.startswith("#"):
            flush()
            section = s.lstrip("#").strip()
            continue
        if s.startswith("|") and s.count("|") >= 2:
            cur.append(s)
        else:
            flush()
    return tables


def strip_md(text: str) -> str:
    text = MD_LINK.sub(r"\1", text)
    text = re.sub(r"[*_]{1,2}([^*_]+)[*_]{1,2}", r"\1", text)
    return text.strip()


def clean_ident(code: str) -> str:
    """`CreateNichConObject()` -> CreateNichConObject ; `obj$new(mat)` -> obj$new"""
    c = code.strip()
    c = re.sub(r"\((?:[^()]|\([^()]*\))*\)$", "", c).strip()  # trailing call parens
    return c


R_WORD = re.compile(r"(^|[^A-Za-z0-9_])R([^A-Za-z0-9_]|$)")


def classify_header(cell: str, hints: dict) -> str | None:
    """Return 'py' | 'r' | 'status' | 'note' | None for a header cell."""
    raw = strip_md(cell)
    low = raw.lower()
    py_hit = (
        "python" in low or "pyth" in low or "py-" in low
        or re.search(r"(^|[^a-z0-9])py([^a-z0-9]|$)", low) is not None
        or any(h and h.lower() in low for h in (hints.get("import_name"), hints.get("pypi")))
    )
    r_hit = (
        R_WORD.search(raw) is not None
        or any(h and re.search(rf"(^|[^A-Za-z0-9]){re.escape(h)}([^A-Za-z0-9]|$)", raw, re.I)
               for h in (hints.get("upstream"),))
    )
    if py_hit and not re.search(r"\bvs\.?\b|_vs_|⇄|<->|↔", low):
        return "py"
    if r_hit and not py_hit:
        return "r"
    if re.search(r"status|match|tier|parity|coverage", low):
        return "status"
    if re.search(r"note|purpose|description|desc|stage|what|role|test", low):
        return "note"
    return None


def classify_status(text: str, default: str = "ported") -> tuple[str, str | None]:
    """Infer (status, parity) from a status/notes cell."""
    low = text.lower()
    status = default
    parity = None
    if "❌" in text or "missing" in low or "not ported" in low or "not implemented" in low:
        status = "planned"
    if "⛔" in text or "skipped" in low or "out of scope" in low or "deliberately" in low:
        status = "skipped"
    if "🔸" in text or "⚠" in text or "partial" in low or "wip" in low or "in progress" in low:
        status = "partial"
    if re.search(r"planned|todo|roadmap|coming|not yet|⏳|🚧|v0\.\d+ *$", low) or "⏳" in text or "🚧" in text:
        status = "planned"
    if re.search(r"bit[- ]?exact|bit[- ]?equivalent|identical|exact", low):
        parity = "exact"
    elif re.search(r"atol|rtol|approx|≈|1e-\d|tolerance|pearson|spearman|jaccard", low):
        parity = "approx"
    elif re.search(r"behaviou?r|semantic|same api", low):
        parity = "behavioural"
    return status, parity


def split_pieces(cell: str) -> list[dict]:
    """Split a mapping cell into pieces; each piece = {name, aliases}.

    `lm_fit` / `lmFit`, `ebayes`  ->  [{lm_fit, [lmFit]}, {ebayes, []}]
    plain text (no code spans)    ->  [{text, []}]
    """
    text = cell.strip()
    plain = strip_md(text).lower().strip("✅❌🔸⏳🚧⛔ ").strip()
    if plain in EMPTY_CELLS or plain in {"(custom)", "custom", "python-only", "new", "(new)", "n/a"}:
        return []
    has_code = bool(CODE_SPAN.search(text))
    # split on commas that sit *outside* code spans and parentheses
    pieces, buf, in_code, paren = [], "", False, 0
    for ch in text:
        if ch == "`":
            in_code = not in_code
        elif not in_code and ch in "([":
            paren += 1
        elif not in_code and ch in ")]":
            paren = max(0, paren - 1)
        if ch == "," and not in_code and paren == 0:
            pieces.append(buf)
            buf = ""
        else:
            buf += ch
    pieces.append(buf)
    out = []
    for p in pieces:
        ids = [clean_ident(i) for i in CODE_SPAN.findall(p)]
        ids = [i for i in ids if i]
        if ids:
            out.append({"name": ids[0], "aliases": ids[1:], "raw": strip_md(p)})
        elif not has_code:
            t = strip_md(p).strip()
            if t and t.lower() not in EMPTY_CELLS:
                out.append({"name": t, "aliases": [], "raw": t})
    return out


def norm_key(name: str | None) -> str:
    if not name:
        return ""
    n = name.split("::")[-1]
    n = re.sub(r"^[a-z_][a-z0-9_]*\.", "", n) if "." in n and not n[0].isupper() else n  # drop module prefix
    return re.sub(r"[^a-z0-9]", "", n.lower())


def extract_function_rows(md: str, hints: dict) -> tuple[list[dict], list[str]]:
    """Scan README tables for Python<->R mappings. Returns (functions, sections_used)."""
    functions: list[dict] = []
    sections: list[str] = []
    for table in parse_md_tables(md):
        kinds = [classify_header(h, hints) for h in table["header"]]
        if "r" in kinds and "py" not in kinds:
            for i, h in enumerate(table["header"]):
                if kinds[i] is None and re.fullmatch(r"(function|functions|python api|python function|method|step|api)", strip_md(h).strip().lower()):
                    kinds[i] = "py"
                    break
        if "py" not in kinds or "r" not in kinds or kinds.count("py") > 1:
            continue
        py_i = kinds.index("py")
        r_i = kinds.index("r")
        status_i = kinds.index("status") if "status" in kinds else None
        note_i = kinds.index("note") if "note" in kinds else None
        sections.append(table["section"] or "(untitled table)")
        for row in table["rows"]:
            if max(py_i, r_i) >= len(row):
                continue
            r_pieces = split_pieces(row[r_i])
            py_pieces = split_pieces(row[py_i])
            status_text = row[status_i] if status_i is not None and status_i < len(row) else ""
            note_text = strip_md(row[note_i]) if note_i is not None and note_i < len(row) else ""
            default_status = "ported" if py_pieces else "planned"
            status, parity = classify_status(status_text + " " + row[py_i] + " " + row[r_i], default_status)
            if not r_pieces and not py_pieces:
                continue
            if not CODE_SPAN.search(row[r_i]) and not CODE_SPAN.search(row[py_i]):
                continue  # prose comparison row, not a function mapping
            note_text = re.sub(r"^[\s✅❌🔸⏳🚧⛔]+|[\s✅❌🔸⏳🚧⛔]+$", "", note_text)
            pairs: list[tuple[dict | None, dict | None]] = []
            if r_pieces and py_pieces and len(r_pieces) == len(py_pieces):
                pairs = list(zip(r_pieces, py_pieces))
            elif r_pieces and len(py_pieces) == 1:
                pairs = [(r, py_pieces[0]) for r in r_pieces]
            elif py_pieces and len(r_pieces) == 1:
                merged = {"name": " / ".join(p["name"] for p in py_pieces),
                          "aliases": [a for p in py_pieces for a in p["aliases"]], "raw": row[py_i]}
                pairs = [(r_pieces[0], merged)]
            elif not py_pieces:
                pairs = [(r, None) for r in r_pieces]
            elif not r_pieces:
                pairs = [(None, p) for p in py_pieces]
            else:
                pairs = [({"name": " / ".join(p["name"] for p in r_pieces), "aliases": [], "raw": row[r_i]},
                          {"name": " / ".join(p["name"] for p in py_pieces), "aliases": [], "raw": row[py_i]})]
            for r, p in pairs:
                functions.append({
                    "r": r["name"] if r else None,
                    "py": p["name"] if p else None,
                    "aliases": (p["aliases"] if p else []) + (r["aliases"] if r and not p else []),
                    "status": status if p else ("planned" if status == "ported" else status),
                    "parity": parity,
                    "note": note_text or re.sub(r"^[\s✅❌🔸⏳🚧⛔]+|[\s✅❌🔸⏳🚧⛔]+$", "", strip_md(status_text)) or None,
                    "test": None,
                    "_from": "readme",
                })
    return functions, sections


def parse_audit(md: str) -> dict:
    """Parse AUDIT.md from engine/r_function_audit.py."""
    out = {"exports": [], "summary": {}}
    for table in parse_md_tables(md):
        hdr = [strip_md(h).lower() for h in table["header"]]
        if hdr[:3] == ["r function", "python equivalent", "status"]:
            for row in table["rows"]:
                if len(row) < 3:
                    continue
                r = CODE_SPAN.findall(row[0])
                py = CODE_SPAN.findall(row[1])
                py_name = clean_ident(py[0]) if py and py[0].strip() not in EMPTY_CELLS else None
                out["exports"].append({
                    "r": clean_ident(r[0]) if r else strip_md(row[0]),
                    "py": py_name,
                    "status": "ported" if "✅" in row[2] or "ported" in row[2].lower() else "planned",
                })
        elif hdr[:1] == ["category"] and "ported" in hdr:
            for row in table["rows"]:
                if len(row) >= 3 and row[0].lower().startswith("exported"):
                    try:
                        out["summary"] = {"exported_ported": int(row[1]), "exported_total": int(row[2])}
                    except ValueError:
                        pass
    return out


def parse_report(md: str) -> dict:
    """Pull parity evidence out of RECONSTRUCTION_REPORT.md §1 (Identity table)."""
    out: dict = {}
    NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?(?:e-?\d+)?)(?![\w.])")
    def num(x):
        """First number in a cell: '`0.9978`', 'Spearman **0.8385**, Jaccard **0.667** ✅', 'Pearson ≥ 0.99'."""
        x = x.replace("**", "").replace("`", "")
        m = re.search(r"[≥>]=?\s*" + NUM.pattern, x)
        m = NUM.search(x, m.start()) if m else NUM.search(x)
        try:
            return float(m.group(1)) if m else None
        except ValueError:
            return None
    for table in parse_md_tables(md):
        hdr = [strip_md(h).lower() for h in table["header"]]
        if hdr[:2] != ["field", "value"]:
            continue
        for row in table["rows"]:
            if len(row) < 2:
                continue
            k = strip_md(row[0]).lower()
            v = strip_md(row[1]).strip("`").strip()
            if v.startswith("<") and v.endswith(">"):
                continue  # unfilled template placeholder
            if k.startswith("algorithm class"):
                out["algorithm_class"] = v.split("/")[0].strip() or None
            elif k.startswith("parity threshold"):
                out["threshold"] = num(v)
            elif k.startswith("final parity"):
                # only trust decimal / scientific numbers as a parity value ("29/29 tests" is a count)
                out["value"] = num(v) if re.search(r"\d\.\d|\de-?\d", v) else None
                out["value_text"] = v[:160]
                if "❌" in row[1]:
                    out["verdict"] = "partial"
                elif "✅" in row[1] or re.search(r"all (gates|outputs|tests)? ?pass", v, re.I):
                    out["verdict"] = "pass"
            elif k.startswith("audit class"):
                out["audit_class"] = v[:1].upper() if v else None
            elif k.startswith("upstream r package"):
                m = re.search(r"v?`?(\d+[\w.\-]*)`?\s*$", v)
                if m:
                    out["upstream_version"] = m.group(1)
        break
    return out


def readme_citation(readme: str | None) -> str | None:
    if not readme:
        return None
    m = re.search(r"^#{2,3}\s*(?:citation|citing|cite|how to cite)[^\n]*\n(.*?)(?=^#{1,3}\s|\Z)", readme, re.I | re.M | re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        t = strip_md(line.strip().lstrip(">").strip())
        t = re.sub(r"^(if you use|please cite|cite)[^:]*:\s*", "", t, flags=re.I)
        if len(t) > 25 and re.search(r"(19|20)\d{2}", t) and not t.lower().startswith(("```", "@", "and acknowledge")):
            return t[:240]
    return None


# --------------------------------------------------------------------------- #
# pyproject / description helpers                                             #
# --------------------------------------------------------------------------- #

def parse_pyproject(text: str | None) -> dict:
    info: dict = {}
    if not text:
        return info
    try:
        import tomllib  # py311+
        data = tomllib.loads(text)
    except Exception:
        data = None
    if data:
        proj = data.get("project") or data.get("tool", {}).get("poetry") or {}
        info["pypi"] = proj.get("name")
        info["version"] = proj.get("version") if isinstance(proj.get("version"), str) else None
        lic = proj.get("license")
        if isinstance(lic, dict):
            lic = lic.get("text") or lic.get("file")
        info["license"] = lic if isinstance(lic, str) else None
        st = data.get("tool", {}).get("setuptools", {})
        pk = st.get("packages")
        if isinstance(pk, dict):
            inc = (pk.get("find") or {}).get("include") or []
            if inc:
                info["import_name"] = str(inc[0]).rstrip("*").rstrip(".")
        elif isinstance(pk, list) and pk:
            info["import_name"] = str(pk[0]).split(".")[0]
        if not info.get("import_name"):
            inc = ((st.get("packages") or {}).get("find") or {}).get("include") if isinstance(st.get("packages"), dict) else None
            if inc:
                info["import_name"] = str(inc[0]).rstrip("*").rstrip(".")
        if not info.get("import_name"):
            m = re.search(r"^\s*(?:packages|include)\s*=\s*\[\s*\"([A-Za-z_][A-Za-z0-9_]*)\*?\"", text, re.M)
            if m:
                info["import_name"] = m.group(1)
        return info
    # regex fallback (python < 3.11 without tomllib)
    m = re.search(r"^\s*name\s*=\s*\"([^\"]+)\"", text, re.M)
    info["pypi"] = m.group(1) if m else None
    m = re.search(r"^\s*version\s*=\s*\"([^\"]+)\"", text, re.M)
    info["version"] = m.group(1) if m else None
    m = re.search(r"^\s*license\s*=\s*(?:\{\s*text\s*=\s*)?\"([^\"]+)\"", text, re.M)
    info["license"] = m.group(1) if m else None
    m = re.search(r"^\s*(?:packages|include)\s*=\s*\[\s*\"([A-Za-z_][A-Za-z0-9_]*)\*?\"", text, re.M)
    info["import_name"] = m.group(1) if m else None
    return info


UPSTREAM_RE = re.compile(
    r"(?:re-?implementation|re-?write|port|rebuild)\s+of\s+"
    r"(?:the\s+)?(?:R\s+|CRAN\s+|Bioconductor\s+|Bioc\s+|GitHub\s+)*(?:package\s+)?"
    r"([A-Za-z][A-Za-z0-9_.]*(?:'s\s+[A-Za-z][A-Za-z0-9_.]*)?)",
    re.I,
)
SOURCE_RE = re.compile(r"\b(CRAN|Bioconductor|Bioc|GitHub)\b", re.I)
CITATION_RE = re.compile(r"\(([^()]*?(?:et al\.?|[A-Z][a-z]+)[^()]*?\b(19|20)\d{2})\)")


def infer_upstream(repo_name: str, description: str | None, readme: str | None) -> dict:
    desc = description or ""
    up: dict = {"name": None, "source": None, "version": None, "url": None, "citation": None, "license": None, "language": "R"}
    m = UPSTREAM_RE.search(desc) or (UPSTREAM_RE.search(readme[:1500]) if readme else None)
    if m:
        name = m.group(1).replace("'s", "").strip(" .")
        up["name"] = name.split()[-1] if "'s" in m.group(1) else name
    repo_derived = PORT_RE.sub("", repo_name)
    if not up["name"] or up["name"].lower() == repo_derived.lower():
        up["name"] = repo_derived
    m = SOURCE_RE.search(desc) or (SOURCE_RE.search(readme[:1500]) if readme else None)
    if m:
        src = m.group(1)
        up["source"] = {"bioc": "Bioconductor"}.get(src.lower(), src if src.lower() != "github" else "GitHub")
        if up["source"].lower() == "cran":
            up["source"] = "CRAN"
    m = CITATION_RE.search(desc)
    if m:
        up["citation"] = m.group(1).strip()
    if readme:
        for text, url in MD_LINK.findall(readme[:4000]):
            if up["name"] and up["name"].lower() in text.lower() and "omicverse" not in url:
                up["url"] = url
                break
    if not up["url"] and up["name"]:
        if up["source"] == "CRAN":
            up["url"] = f"https://cran.r-project.org/package={up['name']}"
        elif up["source"] == "Bioconductor":
            up["url"] = f"https://bioconductor.org/packages/{up['name']}"
    return up


def infer_omicverse_module(readme: str | None, *keys: str | None) -> str | None:
    if not readme:
        return None
    wanted = [re.sub(r"^(py|rust)[-_]?", "", k.lower()).replace("_", "").replace("-", "") for k in keys if k]
    for m in re.finditer(r"`?((?:omicverse|ov)\.(?:[a-z_]+\.)+[A-Za-z_][A-Za-z0-9_]*)`?", readme):
        mod = m.group(1).replace("omicverse.", "ov.", 1)
        flat = mod.lower().replace("_", "")
        if any(w and w in flat for w in wanted):
            return mod
    return None


# --------------------------------------------------------------------------- #
# port.yaml validation                                                        #
# --------------------------------------------------------------------------- #

def load_port_yaml(text: str, repo_name: str) -> tuple[dict | None, list[str]]:
    warnings: list[str] = []
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return None, [f"port.yaml is not valid YAML: {e}"]
    if not isinstance(data, dict):
        return None, ["port.yaml must be a mapping"]
    schema = str(data.get("schema", ""))
    if not schema.startswith("omicverse-port/"):
        warnings.append(f"schema should be 'omicverse-port/v1' (got {schema!r})")
    if data.get("package") and data["package"] != repo_name:
        warnings.append(f"package {data['package']!r} does not match repo name {repo_name!r}")
    up = data.get("upstream") or {}
    if not isinstance(up, dict) or not up.get("name"):
        warnings.append("upstream.name is required")
    fns = data.get("functions")
    if not isinstance(fns, list) or not fns:
        warnings.append("functions list is empty")
        data["functions"] = []
    clean_fns = []
    for i, f in enumerate(data["functions"]):
        if not isinstance(f, dict):
            warnings.append(f"functions[{i}] is not a mapping")
            continue
        status = str(f.get("status") or ("ported" if f.get("py") else "planned")).lower()
        if status not in STATUS_VALUES:
            warnings.append(f"functions[{i}].status {status!r} not in {STATUS_VALUES}")
            status = "ported" if f.get("py") else "planned"
        parity = f.get("parity")
        if parity is not None and str(parity).lower() not in PARITY_VALUES:
            warnings.append(f"functions[{i}].parity {parity!r} not in {PARITY_VALUES}")
            parity = None
        clean_fns.append({
            "r": f.get("r"),
            "py": f.get("py"),
            "aliases": [str(a) for a in (f.get("aliases") or [])],
            "status": status,
            "parity": str(parity).lower() if parity else None,
            "note": f.get("note"),
            "test": f.get("test"),
        })
    data["functions"] = clean_fns
    if data.get("domain") and data["domain"] not in DOMAINS:
        warnings.append(f"domain {data['domain']!r} not in {sorted(DOMAINS)}")
    return data, warnings


# --------------------------------------------------------------------------- #
# Per-repo build                                                              #
# --------------------------------------------------------------------------- #

def gh_blob(repo: dict, path: str) -> str:
    return f"{repo['html_url']}/blob/{repo.get('default_branch') or 'main'}/{path}"


def gh_raw(repo: dict, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo['full_name']}/{repo.get('default_branch') or 'main'}/{path}"


def coverage_of(functions: list[dict]) -> dict:
    cov = {k: 0 for k in STATUS_VALUES}
    for f in functions:
        cov[f["status"]] = cov.get(f["status"], 0) + 1
    cov["total"] = len(functions)
    cov["r_functions"] = sum(1 for f in functions if f.get("r"))
    return cov


def build_record(gh: GitHub, repo: dict, overrides: dict, verbose: bool = False) -> dict:
    name = repo["name"]
    ref = repo.get("default_branch") or "main"
    ov = overrides.get(name) or {}
    tree = gh.tree(name, ref)
    tree_set = set(tree)

    def has(p: str) -> bool:
        return p in tree_set

    record: dict = {
        "repo": name,
        "full_name": repo["full_name"],
        "html_url": repo["html_url"],
        "description": repo.get("description"),
        "lang": "rust" if name.lower().startswith("rust-") or (repo.get("language") == "Rust") else "python",
        "stars": repo.get("stargazers_count", 0),
        "pushed_at": repo.get("pushed_at"),
        "default_branch": ref,
        "logo_url": next((gh_raw(repo, p) for p in ("logo/logo.svg", "logo/logo.png") if has(p)), None),
        "warnings": [],
    }

    # --- artefacts present in the tree -------------------------------------
    notebooks = sorted(p for p in tree if p.startswith("examples/") and p.endswith(".ipynb") and ".executed" not in p)
    tests = sorted(p for p in tree if p.startswith("tests/") and re.search(r"test_.*\.py$", p))
    manifest_path = next((p for p in ("data/manifest.yaml", "manifest.yaml", "data/manifest.yml") if has(p)), None)
    record["artifacts"] = {
        "readme": gh_blob(repo, "README.md") if has("README.md") else None,
        "audit": gh_blob(repo, "AUDIT.md") if has("AUDIT.md") else None,
        "report": gh_blob(repo, "RECONSTRUCTION_REPORT.md") if has("RECONSTRUCTION_REPORT.md") else None,
        "manifest": gh_blob(repo, manifest_path) if manifest_path else None,
        "math": gh_blob(repo, "MATH.md") if has("MATH.md") else None,
        "notebooks": [{"name": Path(p).name, "url": gh_blob(repo, p)} for p in notebooks],
        "tests_count": len(tests),
        "r_reference_driver": any(p.endswith(".R") for p in tree if p.startswith(("tests/", "examples/"))),
    }

    # --- pyproject ---------------------------------------------------------
    pyproject = parse_pyproject(gh.file_text(name, "pyproject.toml", ref)) if has("pyproject.toml") else {}
    cargo = None
    if has("Cargo.toml") and not pyproject.get("pypi"):
        cargo = gh.file_text(name, "Cargo.toml", ref)
    record["pypi"] = pyproject.get("pypi")
    record["import_name"] = pyproject.get("import_name")
    record["version"] = pyproject.get("version")
    record["license"] = pyproject.get("license")
    if cargo:
        m = re.search(r"^\s*name\s*=\s*\"([^\"]+)\"", cargo, re.M)
        record["crate"] = m.group(1) if m else None
        m = re.search(r"^\s*version\s*=\s*\"([^\"]+)\"", cargo, re.M)
        record["version"] = record["version"] or (m.group(1) if m else None)

    # --- port.yaml first --------------------------------------------------
    port_text = None
    port_path = None
    for cand in PORT_FILE_CANDIDATES:
        if has(cand):
            port_text = gh.file_text(name, cand, ref)
            port_path = cand
            break

    readme = gh.file_text(name, "README.md", ref) if has("README.md") else None
    manifest = None
    if manifest_path:
        try:
            manifest = yaml.safe_load(gh.file_text(name, manifest_path, ref) or "") or {}
        except yaml.YAMLError:
            record["warnings"].append(f"{manifest_path} is not valid YAML")

    if port_text:
        data, warns = load_port_yaml(port_text, name)
        record["warnings"].extend(warns)
        if data is not None:
            record["source"] = "port.yaml"
            record["source_detail"] = [port_path]
            up = data.get("upstream") or {}
            record["upstream"] = {
                "name": up.get("name") or PORT_RE.sub("", name),
                "language": up.get("language") or "R",
                "source": up.get("source"),
                "version": str(up["version"]) if up.get("version") is not None else None,
                "url": up.get("url"),
                "citation": up.get("citation"),
                "license": up.get("license"),
            }
            record["pypi"] = data.get("pypi") or record["pypi"]
            record["import_name"] = data.get("import_name") or record["import_name"]
            record["lang"] = (data.get("language") or record["lang"]).lower()
            record["domain"] = data.get("domain") or ov.get("domain") or "other"
            om = data.get("omicverse") or {}
            record["omicverse"] = {"module": om.get("module"), "since": str(om["since"]) if om.get("since") else None}
            par = data.get("parity") or {}
            record["parity"] = {
                "status": (par.get("status") or "unverified").lower(),
                "algorithm_class": par.get("algorithm_class") or (manifest or {}).get("algorithm_class"),
                "metric": par.get("metric"),
                "threshold": par.get("threshold"),
                "value": par.get("value"),
                "fixture": par.get("fixture"),
                "test": par.get("test"),
            }
            arts = data.get("artifacts") or {}
            for key in ("audit", "report", "compare_notebook", "function_notebook"):
                if arts.get(key):
                    v = str(arts[key])
                    record["artifacts"][key] = v if v.startswith("http") else gh_blob(repo, v)
            record["functions"] = data["functions"]
            record["mapping_quality"] = "curated"
            record["classes"] = [
                {"r": c.get("r"), "py": c.get("py"), "note": c.get("note")}
                for c in (data.get("classes") or []) if isinstance(c, dict)
            ]
            record["coverage"] = coverage_of(record["functions"])
            record["upstream"]["url"] = record["upstream"]["url"] or infer_upstream(name, repo.get("description"), readme)["url"]
            return record
        # invalid port.yaml -> fall through to inference, warnings kept

    # --- inference ---------------------------------------------------------
    record["source"] = "inferred"
    detail: list[str] = ["pyproject"] if pyproject else []
    upstream = infer_upstream(name, repo.get("description"), readme)
    if manifest and isinstance(manifest.get("upstream"), dict):
        mu = manifest["upstream"]
        upstream["name"] = mu.get("name") or upstream["name"]
        upstream["version"] = str(mu["version"]) if mu.get("version") is not None else upstream["version"]
        src = str(mu.get("source") or "")
        if src.startswith("http"):
            upstream["url"] = upstream["url"] or src
            if "github.com" in src:
                upstream["source"] = upstream["source"] or "GitHub"
        elif src:
            upstream["source"] = src
        if mu.get("url"):
            upstream["url"] = mu["url"]
        detail.append("manifest")
    for k, v in (ov.get("upstream") or {}).items():
        upstream[k] = v
    record["upstream"] = upstream
    record["domain"] = ov.get("domain") or "other"
    record["omicverse"] = {"module": ov.get("omicverse_module") or infer_omicverse_module(readme, upstream.get("name"), record.get("import_name"), name), "since": None}

    hints = {"upstream": upstream.get("name"), "pypi": record.get("pypi"), "import_name": record.get("import_name")}
    functions: list[dict] = []
    sections: list[str] = []
    if readme:
        functions, sections = extract_function_rows(readme, hints)
        if functions:
            detail.append("readme-table")

    if has("AUDIT.md"):
        audit = parse_audit(gh.file_text(name, "AUDIT.md", ref) or "")
        detail.append("audit")
        by_key = {norm_key(f["r"]): f for f in functions if f.get("r")}
        for row in audit["exports"]:
            key = norm_key(row["r"])
            if key in by_key:
                by_key[key]["exported"] = True
                by_key[key]["audit_status"] = row["status"]
            else:
                functions.append({
                    "r": row["r"], "py": row["py"], "aliases": [],
                    "status": row["status"], "parity": None, "note": None, "test": None,
                    "exported": True, "_from": "audit",
                })
        record["audit_summary"] = audit["summary"] or None

    mapping_quality = "readme" if functions else "none"
    if has("AUDIT.md") and functions:
        mapping_quality = "readme+audit" if any(f.get("_from") == "readme" for f in functions) else "audit"
    if not functions and record.get("import_name") and has(f"{record['import_name']}/__init__.py"):
        init = gh.file_text(name, f"{record['import_name']}/__init__.py", ref) or ""
        m = re.search(r"__all__\s*(?::\s*[^=]+)?=\s*[\[(]([^\]\)]*)[\])]", init, re.S)
        if m:
            names = re.findall(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']", m.group(1))
            for n in names:
                if n.startswith("_"):
                    continue
                functions.append({"r": None, "py": f"{record['import_name']}.{n}", "aliases": [], "status": "ported",
                                  "parity": None, "note": None, "test": None, "_from": "init"})
            if functions:
                detail.append("__all__")
                mapping_quality = "api-only"
    for f in functions:
        f.pop("_from", None)
    record["mapping_quality"] = mapping_quality
    record["functions"] = functions
    record["classes"] = []
    record["coverage"] = coverage_of(functions)
    record["source_detail"] = detail
    record["parity"] = {
        "status": "gated" if manifest else "unverified",
        "algorithm_class": (manifest or {}).get("algorithm_class"),
        "metric": None, "threshold": None, "value": None,
        "fixture": ((manifest or {}).get("fixture") or {}).get("description") if isinstance((manifest or {}).get("fixture"), dict) else None,
        "test": "tests/test_exact_match.py" if has("tests/test_exact_match.py") else None,
    }
    if manifest and isinstance(manifest.get("outputs"), list) and manifest["outputs"]:
        o = manifest["outputs"][0]
        if isinstance(o, dict):
            record["parity"]["metric"] = o.get("metric")
            record["parity"]["threshold"] = o.get("threshold")
    if has("RECONSTRUCTION_REPORT.md"):
        rep = parse_report(gh.file_text(name, "RECONSTRUCTION_REPORT.md", ref) or "")
        if rep:
            detail.append("report")
            par = record["parity"]
            par["algorithm_class"] = par["algorithm_class"] or rep.get("algorithm_class")
            if rep.get("threshold") is not None:
                par["threshold"] = rep["threshold"]
            if rep.get("value") is None and rep.get("verdict"):
                par["status"] = rep["verdict"]
                par["value_text"] = rep.get("value_text")
            if rep.get("value") is not None:
                par["value"] = rep["value"]
                thr = par.get("threshold")
                lower_is_better = bool(re.search(r"abs|diff|err|rmse|tol|dist|mae|mse", str(par.get("metric") or rep.get("value_text") or ""), re.I))
                ok = thr is None or (rep["value"] <= thr if lower_is_better else rep["value"] >= thr)
                par["status"] = rep.get("verdict") or ("pass" if ok else "partial")
                if rep.get("value_text"):
                    par["value_text"] = rep["value_text"]
            if rep.get("audit_class"):
                par["audit_class"] = rep["audit_class"]
            if rep.get("upstream_version") and not record["upstream"].get("version"):
                record["upstream"]["version"] = rep["upstream_version"]
    if ov.get("parity_status"):
        record["parity"]["status"] = ov["parity_status"]
    if not record["upstream"].get("citation"):
        record["upstream"]["citation"] = readme_citation(readme)
    if not functions:
        record["warnings"].append("no Python<->R mapping table found in README and no AUDIT.md")
    return record


# --------------------------------------------------------------------------- #
# Scaffold: draft port.yaml for repos that lack one                            #
# --------------------------------------------------------------------------- #

def _y(v) -> str:
    """YAML scalar: quoted string, number, bool, or null."""
    if v is None or v == "":
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v), ensure_ascii=False)


def scaffold_yaml(rec: dict) -> str:
    """Draft port.yaml for a repo that has none. Unknowns are `null` with a TODO comment,
    never literal 'TODO' strings (those would be rendered on the website)."""
    up = rec.get("upstream") or {}
    par = rec.get("parity") or {}
    om = rec.get("omicverse") or {}
    art = rec.get("artifacts") or {}
    nbs = art.get("notebooks") or []
    nb_compare = next((f"examples/{n['name']}" for n in nbs if "compare" in n["name"].lower()), None)
    nb_fn = next((f"examples/{n['name']}" for n in nbs if "function" in n["name"].lower()), None)
    gate_status = par.get("status") if par.get("status") in ("pass", "partial") else "unverified"
    L = [
        "# port.yaml — machine-readable manifest read by omicverse.org/ports",
        "# Draft generated by omicverse-org-home/scripts/build_ports.py from this repo's README / AUDIT.md /",
        "# manifest.yaml / pyproject.toml. Lines marked TODO were not recoverable automatically — please",
        "# review every entry. Spec: https://github.com/omicverse/omicverse-org-home/blob/main/docs/PORT_MANIFEST.md",
        "schema: omicverse-port/v1",
        f"package: {_y(rec['repo'])}",
        f"pypi: {_y(rec.get('pypi'))}" + ("" if rec.get("pypi") else "   # TODO: PyPI distribution name"),
        f"import_name: {_y(rec.get('import_name'))}" + ("" if rec.get("import_name") else "   # TODO: top-level import name"),
        f"language: {rec.get('lang', 'python')}",
        f"domain: {rec.get('domain') or 'other'}   # single-cell | spatial | trajectory | bulk | proteomics | metabolomics | genetics | immune | microbiome | hic | stats | visualization | other",
        "upstream:",
        f"  name: {_y(up.get('name'))}",
        f"  source: {_y(up.get('source'))}   # CRAN | Bioconductor | GitHub | other",
        f"  version: {_y(up.get('version'))}" + ("" if up.get("version") else "   # TODO: upstream version the parity test was run against"),
        f"  url: {_y(up.get('url'))}",
        "  license: null   # TODO: upstream R package license (GPL-3, MIT, Artistic-2.0, …)",
        f"  citation: {_y(up.get('citation'))}" + ("" if up.get("citation") else "   # TODO: \"First author et al. (Year) Journal\""),
    ]
    if up.get("language") and up["language"] != "R":
        L.append(f"  language: {_y(up['language'])}")
    L += [
        "omicverse:",
        f"  module: {_y(om.get('module'))}" + ("" if om.get("module") else "   # TODO: e.g. ov.single.pyDoubletFinder, or leave null"),
        "  since: null",
        "parity:",
        f"  status: {gate_status}   # pass | partial | unverified",
        f"  algorithm_class: {_y(par.get('algorithm_class'))}" + ("" if par.get("algorithm_class") else "   # TODO: see omicverse-rebuildr/PARITY_TAXONOMY.md"),
        f"  metric: {_y(par.get('metric'))}" + ("" if par.get("metric") else "   # TODO: pearson | spearman | ari | jaccard | max_abs_diff | …"),
        f"  threshold: {_y(par.get('threshold'))}",
        f"  value: {_y(par.get('value'))}" + ("" if par.get("value") is not None else "   # TODO: measured value on the canonical fixture"),
        f"  fixture: {_y(par.get('fixture').strip() if isinstance(par.get('fixture'), str) else par.get('fixture'))}",
        f"  test: {_y(par.get('test'))}",
        "artifacts:",
        f"  audit: {_y('AUDIT.md' if art.get('audit') else None)}",
        f"  report: {_y('RECONSTRUCTION_REPORT.md' if art.get('report') else None)}",
        f"  compare_notebook: {_y(nb_compare)}",
        f"  function_notebook: {_y(nb_fn)}",
    ]
    fns = rec.get("functions") or []
    if not fns:
        L += [
            "functions: []   # TODO: one entry per upstream R function, e.g.",
            "#  - r: lmFit                    # R name exactly as exported",
            "#    py: pylimma.lm_fit          # dotted Python path",
            "#    status: ported              # ported | partial | planned | skipped",
            "#    parity: exact               # exact | approx | behavioural | none",
            "#    note: null",
        ]
    else:
        api_only = rec.get("mapping_quality") == "api-only"
        L.append("functions:" + ("   # TODO: public Python API only — fill in the `r:` counterpart (or status: skipped) for each" if api_only else ""))
        for f in fns:
            L.append(f"  - r: {_y(f.get('r'))}" + ("   # TODO" if f.get("r") is None else ""))
            L.append(f"    py: {_y(f.get('py'))}")
            if f.get("aliases"):
                L.append(f"    aliases: {json.dumps(f['aliases'], ensure_ascii=False)}")
            L.append(f"    status: {f.get('status') or 'ported'}")
            if f.get("parity"):
                L.append(f"    parity: {f['parity']}")
            if f.get("note"):
                L.append(f"    note: {_y(f['note'])}")
    classes = rec.get("classes") or []
    if classes:
        L.append("classes:")
        for c in classes:
            L.append(f"  - r: {_y(c.get('r'))}")
            L.append(f"    py: {_y(c.get('py'))}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Catalog of every public repo (packages.html)                                #
# --------------------------------------------------------------------------- #

CATALOG_EXCLUDE = {".github", "omicverse-org-home", "omicverse-pages"}
CATEGORIES = {
    "core": "Core",
    "data": "Data structures",
    "port": "Method ports",
    "agent": "Agents & skills",
    "benchmark": "Benchmarks",
    "learn": "Tutorials",
    "tools": "Tools",
}


def default_category(name: str, lang: str | None) -> str:
    n = name.lower()
    if n == "omicverse":
        return "core"
    if re.match(r"^(py|rust)-", n):
        return "port"
    if "bench" in n or "reproducib" in n or n.endswith("-e2e"):
        return "benchmark"
    if "tutorial" in n:
        return "learn"
    if any(k in n for k in ("skill", "claw", "agent", "luria", "dsh-", "tavotto")):
        return "agent"
    if any(k in n for k in ("anndata", "mudata")):
        return "data"
    return "tools"


def build_catalog(gh: GitHub, repos: list[dict], ports: list[dict], overrides: dict) -> list[dict]:
    by_port = {p["repo"]: p for p in ports}
    cat_over = overrides.get("catalog", {}) or {}
    out: list[dict] = []
    for r in sorted(repos, key=lambda x: x["name"].lower()):
        name = r["name"]
        if name in CATALOG_EXCLUDE or r.get("archived") or r.get("fork"):
            continue
        ov = cat_over.get(name, {}) or {}
        port = by_port.get(name)
        lang_gh = r.get("language")
        lang = "rust" if (name.lower().startswith("rust-") or lang_gh == "Rust") else ("python" if lang_gh in ("Python", "Jupyter Notebook", None) and not name.lower().startswith("rust-") else "other")
        if port:
            lang = port["lang"]
        category = ov.get("category") or default_category(name, lang_gh)
        logo_url = port["logo_url"] if port else None
        if not port and ov.get("logo", True):
            tree = gh.tree(name, r.get("default_branch") or "main")
            for cand in ("logo/logo.svg", "logo/logo.png"):
                if cand in tree:
                    logo_url = gh_raw(r, cand)
                    break
        entry = {
            "name": name,
            "full_name": r["full_name"],
            "html_url": r["html_url"],
            "description": ov.get("description") or (port["description"] if port else r.get("description")) or "",
            "category": category,
            "lang": ov.get("lang") or lang,
            "language": lang_gh,
            "stars": r.get("stargazers_count", 0),
            "pushed_at": r.get("pushed_at"),
            "license": ov.get("license") or (port.get("license") if port else None) or ((r.get("license") or {}).get("spdx_id") if isinstance(r.get("license"), dict) else None),
            "docs": ov.get("docs") or (r.get("homepage") or None),
            "pypi": ov.get("pypi") or (port.get("pypi") if port else None),
            "version": ov.get("version") or (port.get("version") if port else None),
            "topics": r.get("topics") or [],
            "logo_url": logo_url,
            "domain": (port["domain"] if port else ov.get("domain")),
            "upstream": ({"name": port["upstream"].get("name"), "source": port["upstream"].get("source"), "url": port["upstream"].get("url")} if port else None),
            "parity_status": (port["parity"]["status"] if port else None),
            "functions_total": (port["coverage"]["total"] if port else None),
            "catalog_url": (f"ports.html#{name}" if port else None),
            "paper": ov.get("paper"),
        }
        if (entry["license"] or "").upper() in ("NOASSERTION", "NONE", "OTHER"):
            entry["license"] = None
        out.append(entry)
    return out


# --------------------------------------------------------------------------- #
# main                                                                        #
# --------------------------------------------------------------------------- #

def summarize(records: list[dict]) -> dict:
    s = {
        "packages": len(records),
        "python": sum(1 for r in records if r["lang"] == "python"),
        "rust": sum(1 for r in records if r["lang"] == "rust"),
        "with_port_yaml": sum(1 for r in records if r["source"] == "port.yaml"),
        "functions_total": sum(r["coverage"]["total"] for r in records),
        "functions_ported": sum(r["coverage"]["ported"] for r in records),
        "functions_partial": sum(r["coverage"]["partial"] for r in records),
        "functions_planned": sum(r["coverage"]["planned"] for r in records),
        "functions_skipped": sum(r["coverage"]["skipped"] for r in records),
        "with_parity_gate": sum(1 for r in records if r["parity"]["status"] in ("pass", "gated", "partial")),
        "with_audit": sum(1 for r in records if r["artifacts"].get("audit")),
        "domains": {},
        "upstream_sources": {},
    }
    for r in records:
        s["domains"][r["domain"]] = s["domains"].get(r["domain"], 0) + 1
        src = (r["upstream"] or {}).get("source") or "unknown"
        s["upstream_sources"][src] = s["upstream_sources"].get(src, 0) + 1
    return s


def main() -> int:
    global ORG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "src" / "assets" / "ports.json")
    ap.add_argument("--catalog-out", type=Path, default=ROOT / "src" / "assets" / "catalog.json",
                    help="catalog of every public repo for packages.html (pass '' to skip)")
    ap.add_argument("--org", default=ORG)
    ap.add_argument("--cache", type=Path, default=None, help="directory for cached API responses")
    ap.add_argument("--only", default=None, help="comma-separated repo names to restrict to")
    ap.add_argument("--overrides", type=Path, default=ROOT / "scripts" / "ports_overrides.yaml")
    ap.add_argument("--scaffold", type=Path, default=None, help="write draft port.yaml files here (repos without one)")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    ORG = args.org

    overrides: dict = {}
    overrides_full: dict = {}
    if args.overrides and args.overrides.exists():
        overrides_full = yaml.safe_load(args.overrides.read_text()) or {}
        overrides = overrides_full.get("repos", overrides_full)

    gh = GitHub(resolve_token(), args.cache, args.verbose)
    if not gh.token:
        print("warning: no GitHub token; unauthenticated rate limit is 60 req/h", file=sys.stderr)

    repos = gh.paginate(f"orgs/{ORG}/repos", {"type": "public"})
    ports = [r for r in repos if PORT_RE.match(r["name"]) and not r.get("archived") and not r.get("fork")]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        ports = [r for r in ports if r["name"] in wanted]
    ports.sort(key=lambda r: r["name"].lower())
    print(f"[ports] {len(ports)} port repositories", file=sys.stderr)

    records: list[dict] = []
    for repo in ports:
        try:
            rec = build_record(gh, repo, overrides, args.verbose)
        except Exception as e:  # keep going; one broken repo must not kill the catalog
            print(f"[ports] {repo['name']}: ERROR {e}", file=sys.stderr)
            continue
        flag = "port.yaml" if rec["source"] == "port.yaml" else "inferred "
        print(f"[ports] {repo['name']:<20} {flag}  fn={rec['coverage']['total']:<4} "
              f"domain={rec['domain']:<12} upstream={rec['upstream'].get('name')}"
              + (f"  WARN: {'; '.join(rec['warnings'])}" if rec["warnings"] else ""), file=sys.stderr)
        records.append(rec)

    out = {
        "schema": SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "org": ORG,
        "domains": DOMAINS,
        "summary": summarize(records),
        "packages": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"[ports] wrote {args.out} ({args.out.stat().st_size // 1024} KB, {gh.calls} API calls)", file=sys.stderr)

    if args.catalog_out and str(args.catalog_out) and not args.only:
        catalog = build_catalog(gh, repos, records, overrides_full)
        cat_doc = {
            "schema": "omicverse-catalog/v1",
            "generated_at": out["generated_at"],
            "categories": CATEGORIES,
            "domains": DOMAINS,
            "packages": catalog,
        }
        args.catalog_out.write_text(json.dumps(cat_doc, ensure_ascii=False, indent=1) + "\n")
        print(f"[ports] wrote {args.catalog_out} ({len(catalog)} repos, {args.catalog_out.stat().st_size // 1024} KB)", file=sys.stderr)

    if args.scaffold:
        args.scaffold.mkdir(parents=True, exist_ok=True)
        n = 0
        for rec in records:
            if rec["source"] == "port.yaml":
                continue
            (args.scaffold / f"{rec['repo']}.port.yaml").write_text(scaffold_yaml(rec))
            n += 1
        print(f"[ports] wrote {n} draft port.yaml files to {args.scaffold}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

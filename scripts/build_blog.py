#!/usr/bin/env python3
import base64
import html
import io
import json
import keyword
import re
import shutil
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
BLOG_DIR = ROOT / "src" / "blog"
BLOG_ASSET_DIR = ROOT / "src" / "assets" / "blog"


POSTS = [
    {
        "slug": "nanostring-cosmx-workflow",
        "title": "Analyzing NanoString CosMx Data",
        "category": "Spatial",
        "source": PROJECT / "omicverse-tutorials/docs/Tutorials-space/t_nanostring_preprocess.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_nanostring_preprocess_wechat.md",
        "excerpt": "Read CosMx data, validate FOV-level spatial structure, inspect segmentation quality, and prepare inputs for downstream spatial modeling.",
    },
    {
        "slug": "visium-hd-workflow",
        "title": "Analyzing Visium HD Data",
        "category": "Spatial",
        "source": PROJECT / "omicverse-tutorials/docs/Tutorials-space/t_visium_hd_preprocess.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_visium_hd_preprocess_wechat.md",
        "excerpt": "Work with Visium HD bin-level output, tissue images, spatially variable genes, low-dimensional representations, and segmentation-derived views.",
    },
    {
        "slug": "xenium-workflow",
        "title": "Analyzing Xenium Data",
        "category": "Spatial",
        "source": PROJECT / "omicverse-tutorials/docs/Tutorials-space/t_xenium_preprocess.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_xenium_preprocess_wechat.md",
        "excerpt": "Load a 10x Xenium outs folder into AnnData, keep cell polygon boundaries, run QC and Leiden clustering, then project clusters back onto tissue space.",
    },
    {
        "slug": "atera-workflow",
        "title": "Reading and Preprocessing Atera Data",
        "category": "Spatial",
        "source": PROJECT / "omicverse-core/omicverse_guide/docs/Tutorials-space/t_atera_preprocess.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_atera_preprocess_wechat.md",
        "excerpt": "Use OmicVerse to read 10x Atera whole-transcriptome spatial data, align expression, centroids, boundaries, nuclei, morphology channels, and annotations.",
    },
    {
        "slug": "cellpose-visium-hd",
        "title": "Cell Segmentation for Visium HD with Cellpose",
        "category": "Segmentation",
        "source": PROJECT / "omicverse-tutorials/docs/Tutorials-space/t_cellpose.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_cellpose_wechat.md",
        "excerpt": "Connect Visium HD 2 um bins, H&E images, Cellpose segmentation, and bin-to-cell aggregation in a pure Python workflow.",
    },
    {
        "slug": "plot1cell-python",
        "title": "Circular UMAPs with the Python Version of plot1cell",
        "category": "Visualization",
        "source": PROJECT / "omicverse-tutorials/docs/Tutorials-plotting/t_plot1cell.ipynb",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/t_plot1cell_wechat.md",
        "excerpt": "Use ov.pl.plot1cell to place UMAP or t-SNE cells inside a circular layout and add cluster-aware metadata rings around the embedding.",
    },
    {
        "slug": "leiden-resolution-selection",
        "title": "How to Choose Leiden Resolution",
        "category": "Single-cell",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/compare_resolution_methods_pbmc8k_wechat.md",
        "manual_markdown": """
# How to Choose Leiden Resolution: Comparing `leiden`, `auto_resolution`, and `champ`

When running single-cell clustering, almost everyone eventually asks the same question: what should the Leiden `resolution` be?

If the value is too low, distinct biological populations can be merged. If it is too high, a stable cell population can be fragmented into many small clusters. The numbers themselves, such as `0.5`, `1.0`, or `1.2`, do not have intrinsic biological meaning; they are controls for the granularity of community detection.

This tutorial asks a practical question: which OmicVerse tools can help choose a Leiden resolution?

We use `ov.datasets.pbmc8k()` because it includes curated `predicted_celltype` labels, making it possible to compare clustering results against a biological reference.

| Method | Function | Main idea |
|---|---|---|
| Manual Leiden | `ov.pp.leiden(adata, resolution=r)` | The user chooses the resolution directly |
| bootstrap-ARI | `ov.single.auto_resolution()` | Choose the resolution that is most stable under data perturbation |
| CHAMP | `ov.single.auto_resolution(method='champ')` | Choose the partition that is most stable across the modularity landscape |

The key point is that `auto_resolution` and `champ` answer different questions. The bootstrap-ARI workflow asks which resolution is stable under resampling. CHAMP asks which partition is stable as the gamma parameter changes. Neither method replaces biological interpretation; both provide stronger starting points than an arbitrary default.

## Environment setup

```python
import os, io, contextlib
os.environ.setdefault("OMICVERSE_DISABLE_LLM", "1")

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score
import omicverse as ov
ov.style()
```

## Load and preprocess PBMC8k

```python
adata = ov.datasets.pbmc8k()
adata.var_names_make_unique()
```

The dataset includes `predicted_celltype`, so later results can be scored against the curated cell type annotation.

```python
adata = ov.pp.qc(
    adata,
    tresh={"mito_perc": 0.2, "nUMIs": 500, "detected_genes": 250},
    doublets_method="scrublet",
)
ov.pp.preprocess(adata, mode="shiftlog|pearson", n_HVGs=2000)
adata.raw = adata
adata = adata[:, adata.var.highly_variable]
ov.pp.scale(adata)
ov.pp.pca(adata, layer="scaled", n_pcs=50)
ov.pp.neighbors(adata, n_neighbors=15, use_rep="scaled|original|X_pca")
ov.pp.umap(adata)
```

After QC, the example retains 7,677 cells and 2,000 highly variable genes. All methods use the same neighbor graph, so the comparison is controlled.

## Baseline: manual Leiden

```python
ov.pp.leiden(adata, resolution=0.5, key_added="leiden_r05")
ov.pp.leiden(adata, resolution=1.0, key_added="leiden_r10")
```

In this run, `resolution=0.5` produced 13 clusters and `resolution=1.0` produced 18 clusters. That behavior is expected: higher resolution usually means more clusters. The problem is that more clusters do not necessarily mean better biology.

## Bootstrap-ARI with `auto_resolution`

`ov.single.auto_resolution()` uses null-adjusted bootstrap-ARI stability by default. It repeatedly subsamples and reclusters at candidate resolutions, then subtracts a null background estimated from permuted data.

```python
with contextlib.redirect_stdout(io.StringIO()):
    _, autores_best, autores_scores = ov.single.auto_resolution(
        adata,
        resolutions=[0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5],
        n_subsamples=5,
        n_null_subsamples=3,
        random_state=0,
        key_added="leiden_auto",
    )
print(f"auto_resolution chose r = {autores_best}")
```

In the PBMC8k example, `auto_resolution` selected `r = 0.4`.

## CHAMP

CHAMP follows a different logic. Instead of asking which resolution survives bootstrap perturbation, it looks for stable partitions across the modularity landscape.

```python
_, champ_best_r, champ_df = ov.single.auto_resolution(
    adata,
    method="champ",
    key_added="leiden_champ",
)
```

In the same PBMC8k run, CHAMP returned an equivalent Leiden resolution around `r = 0.356`, with a stable gamma range near `[0.08, 0.21]`.

## What the comparison showed

On PBMC8k, the automatic methods performed better than manually choosing `resolution=0.5` or `resolution=1.0`. CHAMP had a slightly higher ARI, while bootstrap `auto_resolution` had a slightly higher NMI.

| Method | Clusters | ARI | NMI |
|---|---:|---:|---:|
| Manual Leiden, r=0.5 | 13 | lower | lower |
| Manual Leiden, r=1.0 | 18 | lower | lower |
| auto_resolution, r=0.4 | 11 | 0.822 | 0.807 |
| CHAMP, gamma in [0.08, 0.21] | 8 | 0.829 | 0.794 |

The practical reading is simple: automatic resolution selection is useful, but it should be treated as a reproducible starting point. Marker genes, known cell states, sample design, and downstream biological questions still decide whether a clustering is useful.
""",
        "excerpt": "Compare manual Leiden, bootstrap stability, and CHAMP on PBMC8k to choose a reproducible starting resolution for single-cell clustering.",
    },
    {
        "slug": "omicverse-2-1-update",
        "title": "What Changed in OmicVerse 2.1.x",
        "category": "Release",
        "manual_markdown": """
# What Changed in OmicVerse 2.1.x

OmicVerse `2.1.x` is not just a small maintenance update. From `v2.0.0` to the current development tree, the project accumulated hundreds of commits, hundreds of changed files, and close to one hundred thousand added lines of code. Two major branches, metabolomics and 16S / microbiome analysis, were also moving toward the merge window.

The update focuses on trajectory inference, spatial omics, preprocessing and I/O, plotting, the agent runtime, and new multi-omics modules.

To update:

```bash
pip install -U omicverse
```

## Update overview

### PP module

- Added a pure-Python `pydoubletfinder` backend for doublet detection.
- Automatically detects mitochondrial prefixes, avoiding manual `MT-` versus `mt-` handling.
- Upgraded Harmony to `harmonypy v0.2.0`, with GPU, CPU NumPy, and Apple Silicon MLX backends.
- Improved memory handling in `torch_pca` and `covariance_eigh`.
- Added the Rust-backed `anndataoom` out-of-memory AnnData reader.

### Single module

- Added `ov.single.Monocle`, a pure Python rebuild of Monocle 2 that avoids `rpy2` and a separate R environment.
- Continued work on dynamic trajectory tools, including lineage-aware trend plotting and improvements around Palantir and Slingshot visualization.

### Space module

- Added `ov.io.read_xenium` for full Xenium `outs/` ingestion.
- Converts Xenium `cell_boundaries` into WKT polygons that can be passed directly to `ov.pl.spatialseg`.
- Added `ov.io.write_visium_hd_cellseg` to export cell-level AnnData back into a Space Ranger v4-compatible directory structure.
- Added CosMx FOV-aware plotting, including multi-FOV layout and per-FOV overlays.
- Added CellSAM support and renamed `stardist()` to the more general `cellseg()`.
- Added `method="cellcharter"` to `ov.utils.cluster`.

### Plotting module

- Added Marsilea-based heatmap plotting.
- Added a set of cell-cell communication plotting APIs.
- Added `ov.pl.create_custom_colormap`.
- Added half-violin boxplots and started consolidating older plotting APIs.
- Improved legend behavior for subset plotting.

### Agent module

- Reworked `ov.Agent`, Jarvis, and OVAgent runtime internals.
- Added Codex OAuth support.
- Moved multiple message channels onto a unified `MessageRuntime`.
- Added sandboxing, timeouts, stdout guards, retries, and security hardening.

### New modules

- Added `ov.metabol` for metabolomics workflows, including ID mapping, MSEA, Mummichog, SERRF, DGCA, ASCA / MixedLM, ROC, and biomarker panels.
- Added `ov.micro` and `ov.alignment` for 16S / microbiome analysis from amplicons to microbiome AnnData objects.

## Why the update matters

The theme of this release is reducing dependency friction while making high-resolution spatial workflows more complete. Xenium, Visium HD, and CosMx are no longer only file formats that can be read; they now have fuller analysis paths that connect I/O, preprocessing, segmentation, plotting, and export.

The pure-Python Monocle 2 rebuild points in the same direction. When core methods no longer require an R bridge, they become easier to install, easier to run in notebooks and pipelines, and easier to expose to agents.

For day-to-day users, the headline is practical: update OmicVerse if you need modern spatial data support, more robust preprocessing, richer plotting, or a more capable agent runtime.
""",
        "excerpt": "A compact English release note for the 2.1.x line: pure-Python Monocle, Xenium and Visium HD workflows, plotting updates, agent runtime work, metabolomics, and microbiome support.",
    },
    {
        "slug": "anthropic-mythos-security",
        "title": "What Anthropic Mythos Preview Signals for Agent Security",
        "category": "Agents",
        "wechat_source": PROJECT / "omicverse-tutorials/wechat_md/anthropic_mythos_preview_wechat.md",
        "manual_markdown": """
# What Anthropic Mythos Preview Signals for Agent Security

The original WeChat note discussed Anthropic's security report on Claude Mythos Preview and Project Glasswing. The relevant takeaway for a scientific computing community is not that every model suddenly becomes an autonomous attacker. It is that capable agents are moving closer to workflows where they can inspect systems, reason about vulnerabilities, assemble tools, and act across a computer environment.

That matters for omics agents because the same capabilities that make an analysis agent useful also create risk:

- file-system access,
- package installation,
- shell execution,
- notebook execution,
- remote data fetching,
- credential handling,
- report generation.

## From code generation to operational access

Earlier AI coding tools mostly produced snippets. Modern agents can run commands, inspect outputs, retry after failures, and chain multiple tools. In bioinformatics, that is attractive because workflows are messy: data formats differ, dependencies break, and notebooks need iterative execution.

The security implication is direct: once an agent can operate a real environment, the boundary is no longer just the prompt. The boundary includes filesystem permissions, network access, secrets, sandbox policy, package provenance, and human review checkpoints.

## What agent-ready omics needs

OmicVerse agents should be useful without being opaque. A safe workflow needs:

- explicit input and output contracts,
- provenance for commands, packages, and datasets,
- bounded execution environments,
- guarded access to credentials,
- logs that a human can audit,
- recoverable failure states,
- reproducible reports rather than hidden notebook state.

## Practical direction

The long-term lesson is not to avoid agents. It is to design them like scientific instruments: powerful, constrained, inspectable, and calibrated. For omics, that means the agent layer should sit on top of stable APIs, documented workflows, and clear permission boundaries.
""",
        "excerpt": "A security-oriented note on why increasingly capable agents need bounded execution, provenance, credential discipline, and auditable scientific workflows.",
    },
]


def escape_attr(value):
    return html.escape(str(value), quote=True)


def inline_md(text):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{escape_attr(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>', text)
    return text


def highlight_python(code):
    out = []
    last = (1, 0)
    builtins = {
        "print", "len", "range", "str", "int", "float", "list", "dict", "set",
        "tuple", "zip", "enumerate", "open", "Path", "True", "False", "None",
    }
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        for tok in tokens:
            token_type, token, start, end, _ = tok
            if token_type in {tokenize.ENCODING, tokenize.ENDMARKER}:
                continue
            line, col = start
            last_line, last_col = last
            if line > last_line:
                out.append("\n" * (line - last_line))
                out.append(" " * col)
            else:
                out.append(" " * max(0, col - last_col))

            cls = ""
            if token_type == tokenize.COMMENT:
                cls = "tok-comment"
            elif token_type == tokenize.STRING:
                cls = "tok-string"
            elif token_type == tokenize.NUMBER:
                cls = "tok-number"
            elif token_type == tokenize.NAME:
                if keyword.iskeyword(token):
                    cls = "tok-keyword"
                elif token in builtins:
                    cls = "tok-builtin"
            elif token_type == tokenize.OP:
                cls = "tok-op"

            escaped = html.escape(token)
            out.append(f'<span class="{cls}">{escaped}</span>' if cls else escaped)
            last = end
    except tokenize.TokenError:
        return html.escape(code)
    return "".join(out)


def highlight_code(code, lang):
    lang = (lang or "").lower()
    if lang in {"python", "py"}:
        return highlight_python(code)
    if lang in {"bash", "sh", "shell", "zsh"}:
        escaped = html.escape(code)
        escaped = re.sub(r"(^|\n)(\s*#.*)", r'\1<span class="tok-comment">\2</span>', escaped)
        escaped = re.sub(r"\b(pip|python|python3|conda|git|cd|mkdir|export)\b", r'<span class="tok-builtin">\1</span>', escaped)
        return escaped
    return html.escape(code)


def extract_wechat_figures(path, max_figures=12):
    if not path or not path.exists():
        return ""
    matches = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", path.read_text())
    if not matches:
        return ""
    lines = ["## Figures"]
    for idx, (_, src) in enumerate(matches[:max_figures], 1):
        lines.append(f"![Figure {idx}]({src})")
    return "\n\n".join(lines)


def markdown_to_html(markdown):
    lines = markdown.strip().splitlines()
    blocks = []
    para = []
    list_items = []
    table = []
    code = []
    in_code = False
    code_lang = ""

    def flush_para():
        nonlocal para
        if para:
            blocks.append(f"<p>{inline_md(' '.join(x.strip() for x in para))}</p>")
            para = []

    def flush_list():
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(f"<li>{inline_md(item)}</li>" for item in list_items) + "</ul>")
            list_items = []

    def flush_table():
        nonlocal table
        if table:
            rows = []
            for i, row in enumerate(table):
                cells = [c.strip() for c in row.strip("|").split("|")]
                tag = "th" if i == 0 else "td"
                if i == 1 and all(set(c.replace(":", "").replace("-", "")) == set() for c in cells):
                    continue
                rows.append("<tr>" + "".join(f"<{tag}>{inline_md(c)}</{tag}>" for c in cells) + "</tr>")
            blocks.append("<table>" + "".join(rows) + "</table>")
            table = []

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            if in_code:
                code_text = chr(10).join(code)
                blocks.append(f'<pre><code class="language-{escape_attr(code_lang)}">{highlight_code(code_text, code_lang)}</code></pre>')
                code = []
                code_lang = ""
                in_code = False
            else:
                flush_para(); flush_list(); flush_table()
                code_lang = line.strip("`").strip()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue

        if not line.strip():
            flush_para(); flush_list(); flush_table()
            continue
        if line.startswith("<!--"):
            continue
        if line.startswith("# "):
            flush_para(); flush_list(); flush_table()
            blocks.append(f"<h1>{inline_md(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            flush_para(); flush_list(); flush_table()
            blocks.append(f"<h2>{inline_md(line[3:].strip())}</h2>")
            continue
        if line.startswith("### "):
            flush_para(); flush_list(); flush_table()
            blocks.append(f"<h3>{inline_md(line[4:].strip())}</h3>")
            continue
        if line.lstrip().startswith("- "):
            flush_para(); flush_table()
            list_items.append(line.lstrip()[2:].strip())
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            flush_para(); flush_table()
            list_items.append(re.sub(r"^\s*\d+\.\s+", "", line).strip())
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_para(); flush_list()
            table.append(line)
            continue
        if re.match(r"!\[[^\]]*\]\([^)]+\)", line.strip()):
            flush_para(); flush_list(); flush_table()
            alt, src = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", line.strip()).groups()
            caption = f"<figcaption>{inline_md(alt)}</figcaption>" if alt else ""
            blocks.append(f'<figure><img src="{escape_attr(src)}" alt="{escape_attr(alt)}" loading="lazy" />{caption}</figure>')
            continue
        para.append(line)

    flush_para(); flush_list(); flush_table()
    return "\n".join(blocks)


def output_image_markdown(cell, slug, cell_index):
    lines = []
    figure_index = 0
    asset_dir = BLOG_ASSET_DIR / slug
    asset_dir.mkdir(parents=True, exist_ok=True)
    for output in cell.get("outputs", []):
        data = output.get("data") or {}
        for mime, ext in (("image/png", "png"), ("image/jpeg", "jpg")):
            payload = data.get(mime)
            if not payload:
                continue
            figure_index += 1
            encoded = "".join(payload) if isinstance(payload, list) else payload
            filename = f"cell-{cell_index:03d}-{figure_index}.{ext}"
            (asset_dir / filename).write_bytes(base64.b64decode(encoded))
            lines.append(f"![Output figure](../assets/blog/{slug}/{filename})")
            break
    return "\n\n".join(lines)


def notebook_to_markdown(path, slug):
    nb = json.loads(path.read_text())
    chunks = []
    asset_dir = BLOG_ASSET_DIR / slug
    if asset_dir.exists():
        shutil.rmtree(asset_dir)
    for idx, cell in enumerate(nb.get("cells", []), 1):
        source = "".join(cell.get("source", [])).strip()
        if not source:
            continue
        if cell.get("cell_type") == "markdown":
            chunks.append(source)
        elif cell.get("cell_type") == "code":
            chunks.append("```python\n" + source + "\n```")
            figures = output_image_markdown(cell, slug, idx)
            if figures:
                chunks.append(figures)
    return "\n\n".join(chunks)


def article_shell(post, article_html):
    title = escape_attr(post["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — OmicVerse</title>
  <link rel="icon" type="image/png" href="../assets/omicos-logo.png" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../styles.css" />
  <script src="../script.js" defer></script>
</head>
<body>
  <header class="site-header">
    <a class="brand" href="../index.html" aria-label="OmicVerse home">
      <img class="brand-logo" src="../assets/omicos-logo.png" alt="" />
      <span>OmicVerse</span>
    </a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-links">Menu</button>
    <nav class="nav-links" id="nav-links" aria-label="Primary navigation">
      <a href="../packages.html">Packages</a>
      <a href="../learn.html">Learn</a>
      <a href="../people.html">People</a>
      <a aria-current="page" href="../blog.html">Blog</a>
      <a href="../events.html">Events</a>
      <a href="../about.html">About</a>
      <a href="../join.html">Join</a>
      <a class="nav-cta" href="https://github.com/omicverse" target="_blank" rel="noopener">GitHub ↗</a>
    </nav>
  </header>

  <main class="article page-width">
    <a class="article-back" href="../blog.html">← Back to blog</a>
    <p class="overline">{html.escape(post["category"])}</p>
    {article_html}
  </main>

  <footer class="footer page-width">
    <span class="footer-brand">
      <img src="../assets/omicos-logo.png" alt="" style="width:14px; height:14px;" />
      <a href="../blog.html" style="color:inherit; font-weight:500;">← Back to blog</a>
    </span>
    <span class="footer-links">
      <a href="../index.html">Home</a>
      <a href="../packages.html">Packages</a>
      <a href="../learn.html">Learn</a>
      <a href="../about.html">About</a>
      <a href="../join.html">Join</a>
    </span>
  </footer>
</body>
</html>
"""


def blog_index(posts):
    cards = []
    for post in posts:
        cards.append(f"""        <a href="blog/{escape_attr(post["slug"])}.html">
          <span class="t-name">{html.escape(post["category"])}</span>
          <span class="t-desc"><strong style="font-weight:500; color:var(--ink);">{html.escape(post["title"])}</strong> {html.escape(post["excerpt"])}</span>
          <span class="t-arrow">Read →</span>
        </a>""")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Blog — OmicVerse</title>
  <link rel="icon" type="image/png" href="assets/omicos-logo.png" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="styles.css" />
  <script src="script.js" defer></script>
</head>
<body>
  <header class="site-header">
    <a class="brand" href="index.html" aria-label="OmicVerse home">
      <img class="brand-logo" src="assets/omicos-logo.png" alt="" />
      <span>OmicVerse</span>
    </a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-links">Menu</button>
    <nav class="nav-links" id="nav-links" aria-label="Primary navigation">
      <a href="packages.html">Packages</a>
      <a href="learn.html">Learn</a>
      <a href="people.html">People</a>
      <a aria-current="page" href="blog.html">Blog</a>
      <a href="events.html">Events</a>
      <a href="about.html">About</a>
      <a href="join.html">Join</a>
      <a class="nav-cta" href="https://github.com/omicverse" target="_blank" rel="noopener">GitHub ↗</a>
    </nav>
  </header>

  <main>
    <section class="page-hero page-width">
      <p class="overline">Blog</p>
      <h1>Tutorials and technical notes from OmicVerse.</h1>
    </section>

    <section class="page-width">
      <div class="t-list blog-list">
{chr(10).join(cards)}
      </div>
    </section>
  </main>

  <footer class="footer page-width">
    <span class="footer-brand">
      <img src="assets/omicos-logo.png" alt="" style="width:14px; height:14px;" />
      OmicVerse
    </span>
    <span class="footer-links">
      <a href="index.html">Home</a>
      <a href="packages.html">Packages</a>
      <a href="learn.html">Learn</a>
      <a href="people.html">People</a>
      <a href="events.html">Events</a>
      <a href="about.html">About</a>
      <a href="join.html">Join</a>
    </span>
  </footer>
</body>
</html>
"""


def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    for old in BLOG_DIR.glob("*.html"):
        old.unlink()
    for post in POSTS:
        if post.get("manual_markdown"):
            markdown = post["manual_markdown"]
            figures = extract_wechat_figures(post.get("wechat_source"))
        else:
            markdown = notebook_to_markdown(post["source"], post["slug"])
            figures = ""
        if figures:
            markdown = f"{markdown}\n\n{figures}"
        article_html = markdown_to_html(markdown)
        (BLOG_DIR / f"{post['slug']}.html").write_text(article_shell(post, article_html))
    (ROOT / "src" / "blog.html").write_text(blog_index(POSTS))


if __name__ == "__main__":
    main()

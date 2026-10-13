# `port.yaml` — the per-repo manifest behind omicverse.org/ports

The [R-port catalog](https://omicverse.org/ports.html) lists every `py-*` / `rust-*`
repository in the `omicverse` org and, for each one, the one-to-one map from
upstream R functions to their Python/Rust counterparts.

The catalog is **generated, not hand-written**. `scripts/build_ports.py` walks the
org once a day (GitHub Actions, see `.github/workflows/sync-ports.yml`), reads one
file per port repo, and writes `src/assets/ports.json`, which `ports.html` renders
client-side.

```
py-<pkg>/port.yaml  ──┐
py-<pkg2>/port.yaml ──┼──▶ scripts/build_ports.py ──▶ src/assets/ports.json ──▶ ports.html
rust-<pkg>/port.yaml ─┘        (daily cron / dispatch)
```

## What a port repo needs

Exactly **one file at the repo root: `port.yaml`**. Nothing else on the website
side has to change when a new port is published — the next sync picks it up.

Until a repo ships `port.yaml`, the builder falls back to *inference* from files the
[omicverse-rebuildr](https://github.com/omicverse/omicverse-rebuildr) protocol
already produces, in this order:

| Fallback source | What is extracted |
|---|---|
| `README.md` "What's included" table (`Python \| R counterpart \| …`) | function pairs, aliases, notes, ✅/❌/⏳ status |
| `AUDIT.md` (from `engine/r_function_audit.py`) | exported R functions and whether a Python name was found |
| `data/manifest.yaml` | upstream version/source, algorithm class, parity metric & threshold |
| `pyproject.toml` | PyPI name, import name, version, license |
| `<import_name>/__init__.py` `__all__` | public Python API, when no mapping table exists at all |
| repo description | upstream name, source (CRAN / Bioconductor / GitHub), citation |

Inferred rows are shown with an **auto** badge; curated rows get **curated**.
Domain for inferred rows comes from `scripts/ports_overrides.yaml`.

A draft `port.yaml` for every repo that lacks one can be generated with
`python scripts/build_ports.py --scaffold <dir>` — review it, fix the `TODO`s and
commit it to the port repo.

## Schema (`omicverse-port/v1`)

```yaml
schema: omicverse-port/v1           # required
package: py-limma                   # repo name (must match)
pypi: python-limma                  # PyPI distribution (`pip install …`)
import_name: pylimma                # `import pylimma`
language: python                    # python | rust
domain: bulk                        # see "Domains" below

upstream:
  name: limma                       # required — upstream package name, R casing
  source: Bioconductor              # CRAN | Bioconductor | GitHub | other
  version: "3.60.4"                 # version the port tracks (string)
  url: https://bioconductor.org/packages/limma
  license: GPL-2
  citation: "Ritchie ME et al. (2015) Nucleic Acids Res 43:e47"
  language: R                       # optional; R (default) | Python | …

omicverse:
  module: ov.bulk.pyDEG             # where the port surfaces inside omicverse, or null
  since: "2.1.0"

parity:
  status: pass                      # pass | partial | unverified
  algorithm_class: deterministic    # from omicverse-rebuildr PARITY_TAXONOMY.md
  metric: max_abs_diff              # pearson | spearman | ari | jaccard | max_abs_diff | …
  threshold: 1e-6
  value: 2.1e-9                     # measured on the canonical fixture
  fixture: "GSE64810, 20 samples"   # one line
  test: tests/test_exact_match.py

artifacts:                          # repo-relative paths or full URLs (all optional)
  audit: AUDIT.md
  report: RECONSTRUCTION_REPORT.md
  compare_notebook: examples/compare_R_vs_Python.ipynb
  function_notebook: examples/function_by_function_R_parity.ipynb

functions:                          # one entry per upstream R function — exports first
  - r: lmFit                        # R name exactly as exported (NAMESPACE)
    py: pylimma.lm_fit              # dotted Python path users actually call
    aliases: [pylimma.lmFit]        # optional camelCase / legacy aliases
    status: ported                  # ported | partial | planned | skipped
    parity: exact                   # exact | approx | behavioural | none  (optional)
    note: "coefficients bit-exact; sigma to 1e-9"
    test: tests/test_lmfit.py       # optional
  - r: plotMDS
    py: null
    status: skipped
    note: "plotting only — use scanpy / matplotlib"

classes:                            # optional — R S4/S3 class ↔ Python class
  - r: MArrayLM
    py: pylimma.MArrayLM
```

### Field vocabulary

| Field | Values | Meaning |
|---|---|---|
| `functions[].status` | `ported` | callable in Python, covers the R behaviour users rely on |
| | `partial` | callable, but some arguments / code paths missing |
| | `planned` | not yet available; listed so users know it is tracked |
| | `skipped` | deliberately not ported (plotting, defunct, Shiny…) — say why in `note` |
| `functions[].parity` | `exact` | bit-exact / identical to R on the fixture |
| | `approx` | matches within a stated tolerance or correlation threshold |
| | `behavioural` | same semantics, numerics intentionally differ (e.g. different RNG) |
| | `none` | no comparison against R exists |
| `parity.status` | `pass` / `partial` / `unverified` | package-level verdict of the pre-registered gate |

### Domains

`single-cell`, `spatial`, `trajectory`, `bulk`, `proteomics`, `metabolomics`,
`genetics`, `immune`, `microbiome`, `hic`, `stats`, `visualization`, `other`.
(Add a new one in `DOMAINS` inside `scripts/build_ports.py` first.)

## Validate locally

```bash
# from omicverse-org-home
python scripts/build_ports.py --only py-limma --cache /tmp/ports-cache --out /tmp/ports.json
```

Warnings (`WARN: …`) are printed per repo; the catalog still builds but the row
falls back to inference when `port.yaml` is unreadable.

## Keeping the catalog fresh

* **Daily**: `.github/workflows/sync-ports.yml` runs at 03:17 UTC, regenerates
  `src/assets/ports.json`, and commits it when it changed.
* **On demand**: *Actions → Sync R-port catalog → Run workflow*.
* **From a port repo** (optional): fire a `repository_dispatch` so the site
  refreshes minutes after `port.yaml` changes. Add to the port repo:

  ```yaml
  # .github/workflows/notify-home.yml
  name: Notify omicverse.org
  on:
    push:
      branches: [main, master]
      paths: [port.yaml, README.md, AUDIT.md]
  jobs:
    ping:
      runs-on: ubuntu-latest
      steps:
        - run: |
            curl -sS -X POST \
              -H "Authorization: Bearer ${{ secrets.ORG_HOME_DISPATCH_TOKEN }}" \
              -H "Accept: application/vnd.github+json" \
              https://api.github.com/repos/omicverse/omicverse-org-home/dispatches \
              -d '{"event_type":"port-manifest-updated","client_payload":{"repo":"${{ github.repository }}"}}'
  ```

  `ORG_HOME_DISPATCH_TOKEN` is a fine-grained PAT with *Contents: read & write*
  on `omicverse-org-home` only, stored as an org-level secret.

## Suggested rebuildr integration

`omicverse-rebuildr` already generates `AUDIT.md` from the upstream `NAMESPACE`.
The natural next step is for `engine/r_function_audit.py` to also emit
`port.yaml` (`--port-yaml port.yaml`), so every new port ships the manifest on
day one, and for `CHECKLIST.md` / `RECONSTRUCTION_REPORT.md` §5 to list
"`port.yaml` committed" as a mandatory item.

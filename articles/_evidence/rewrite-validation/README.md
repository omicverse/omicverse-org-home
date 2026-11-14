# Reproduction of report-v2 experiments

This bundle records the 2026-11-11 internal report revision. It is not a public
package release, and does not contain installed R/Python libraries. Python scripts require `--workspace PATH`; R scripts take that path as their first argument. The workspace must contain the documented `repos/` and `outputs/` layout. This is not a standalone installer. `evidence.zip` contains the recorded outputs, matrix inputs, reference-oracle source and vector figures; extract its contents into the corresponding workspace output directories before rerunning.

## Required sources and inputs

- Original CytoTRACE checkout at f4ff6c0ab93cc704eef44e17adcd5c6baf09703a,
  including its two marrow R data files.
- Original SPLIT checkout at f226987f0fecf2847646bda50a64886e0ea432a9.
- Installed SPATA2 3.1.4, Seurat, Matrix, dplyr and dbscan; CytoTRACE's HiClimR,
  ccaPP and nnls dependencies. `spatial/sessionInfo.txt` and
  `cyto/sessionInfo.txt` record versions.
- Current `rewrite-split`, `rewrite-spata2` and `rewrite-cytotrace` Python
  checkouts. Source hashes accompany the bundle; local repairs are not a new
  package version.
- Earlier `outputs/rewrite-validation/spatial` exports and package fixtures.
- Earlier Scissor audit matrices, graph, CV lambda sequence and corrected
  reference oracle. Its provenance distinguishes original and corrected semantics.

## Commands used

From the workspace root, with process-local LANG/LC_ALL set to C for R:

```text
Rscript outputs/rewrite-validation/report-v2/cyto_reference.R /path/to/workspace
python outputs/rewrite-validation/report-v2/cyto_compare.py --workspace /path/to/workspace
Rscript outputs/rewrite-validation/report-v2/spatial_reference.R /path/to/workspace
python outputs/rewrite-validation/report-v2/spatial_compare.py --workspace /path/to/workspace
Rscript outputs/rewrite-validation/report-v2/cox_tolerance.R /path/to/workspace
python outputs/rewrite-validation/report-v2/cox_tolerance.py --workspace /path/to/workspace
python outputs/rewrite-validation/report-v2/figures.py --workspace /path/to/workspace
python outputs/rewrite-validation/report-v2/build_review.py --workspace /path/to/workspace
```

The CytoTRACE and figure runs used the reference-parity Python environment with
OPENBLAS_NUM_THREADS and OMP_NUM_THREADS set to one. The Scissor run used the
existing scissor-release environment, also with those thread limits. The review
builder used the existing omicverse environment with PYTHONUTF8=1. Do not infer
that all experiments share one Python dependency environment. See the per-env
version records and original Scissor provenance.

## Interpretation rules

- The six marrow runs are subsets of two datasets, not six biological replicates.
- The top-3,000-variance experiment is an input restriction diagnostic, not an
  implementation of every HVG method.
- SPLIT graph inputs are shared. Scores and balance decisions are independently
  computed in R, but independent neighbor-graph construction is not certified.
- SPATA2 geometry uses a placeholder expression assay only to construct the
  original package container; no expression-biological conclusions use it.
- The tighter Cox run evaluates the 100-point full-data path, not a rerun of
  every cross-validation fold. Its acceptance tolerance is unchanged.
- Timings are single observations with unequal certificate work for Cox;
  they are not a controlled general speed benchmark.

Raw output tables are retained even when results fail an earlier tolerance.
The HTML review pages omit nonexistent article-PDF download controls. Vector
PDFs for each figure are provided; complete articles have not been typeset as
publication PDFs. Public src/dist trees remain unchanged.

## Complete author-review papers (2026-11-14)

The four manuscript folders now include `review.pdf`: six pages each, compiled with the repository's OmicVerse LaTeX template. All 24 pages were visually inspected; no overfull boxes or missing glyphs remain. These are explicitly unpublished author-review copies. `final-review.json` records the scoped technical assessment; author/coauthor approval and maintainer publication remain separate.

Regenerate the PDFs using an existing template checkout and Tectonic executable:

```text
python articles/_evidence/rewrite-validation/build_review_pdfs.py --template /path/to/template --tectonic /path/to/tectonic --output /path/to/review-output
python articles/_evidence/rewrite-validation/build_report_review.py --output /path/to/html-review
```

`latex-review-source.zip` contains the generated TeX, template class/license and figures. Long identifiers are breakable and a footer macro handles the older fancyhdr bundled by Tectonic. The scientific body, figures and source hashes remain the inputs; no public article directory is created by these review commands. Numeric text was rounded consistently to the saved CSV/JSON values without changing data or acceptance tolerances.


## Publication submission (2026-11-14)

The authors confirmed the metadata and scoped conclusions for submission. Publication sources now live in articles/<slug>/, with full PDFs and web assets prepared in src/. The site is not claimed deployed until the maintainer merges the PR. The review PDFs remain as archival author-review copies. Use build_publication_pdfs.py with the same --template/--tectonic/--output arguments to regenerate the approved publication PDFs.

The complete evidence archive is served from the repository raw-file URL rather than the static-site asset directory because it exceeds the hosting per-file asset limit. Its SHA-256 remains recorded in evidence.sha256.

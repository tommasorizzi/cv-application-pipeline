# CV application pipeline

The generator uses your ChatGPT-authenticated Codex CLI to extract candidate evidence, analyze each job, tailor structured content, review the writing, audit every claim and compile two PDFs. The renderer follows the three uploaded CV examples: 10pt Latin Modern, A4 with 1.3cm margins, teal ruled headings, a large left-aligned name, labelled bullets and compact skill categories.

## Setup

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
sudo apt-get install latexmk texlive-latex-extra texlive-fonts-recommended lmodern poppler-utils
codex login
```

Use ChatGPT login; no API key is needed. Generation sends professional source text and job content to the Codex service. Identity scans and photos are inventoried but excluded; other unclassified evidence is recorded for review. It does not send applications to employers. No model call happens when running local tests or the layout preview.

If Codex is installed through VS Code, the pipeline can find the extension's bundled executable even when a normal terminal does not have `codex` on `PATH`. Lookup checks `PATH`, common user installation paths, then the native binaries in VS Code extension directories. To choose a specific executable, set `CV_CODEX_BIN=/full/path/to/codex`. The variable is a file path, not a shell command.

## Generate

```bash
.venv/bin/python scripts/initialize_profile.py
.venv/bin/python scripts/generate_application.py path/to/job.txt --company "Example AB" --role "Simulation Engineer"
.venv/bin/streamlit run app/dashboard.py
```

Initialization scans all CVs, cover letters and candidate context recursively, validates exact source quotations and requires coverage for every professional document. The old mechanically seeded profile is archived before replacement. A changed corpus triggers a new extraction; unchanged sources use the saved profile. Review `profile/initialization_report.md`, particularly conflicts, omissions and uncertain facts. Only explicit facts are eligible; derived/uncertain/conflicting facts are excluded. Explicit still means source-stated, not independently proven. Model extraction and semantic review can make mistakes: read the documents before submitting them.

Sources are extracted individually with `[document/total]` progress and cached after quotation validation. Rerunning after Ctrl+C reuses completed documents. A changed document is re-extracted; removing a document excludes its evidence from the next profile even if its cache remains on disk. A compact final pass reconciles extracted facts without sending all full documents again. `--force` on the initialization script bypasses caches deliberately.

The university transcript contributes named coursework and documented academic knowledge. Those are distinguished from professional practice throughout extraction, job matching, drafting and auditing. A course title does not establish an unmentioned software skill or advanced practical proficiency.

The runtime stages are job analysis, drafting, style revision, independent factual audit, LaTeX compilation, page count and PDF text extraction. Every candidate field carries fact IDs; the audit includes the complete claim → fact → source chain. Semantic review must cover every rendered claim; merely knowing an ID is insufficient. At most two correction cycles are allowed. No fixed-text fallback silently replaces a failed Codex call.

`applications/DATE_company_role/` contains the untouched job, inputs, profile/source snapshots, intermediate structured data, private model traces, audit and status. PDFs become available at the top level only after all checks succeed. Completed runs are never overwritten. Inputs, profile revision, source hashes and code/template hashes are recorded for reproducibility.

```bash
# Optional analysis without drafting
.venv/bin/python scripts/generate_application.py job.txt --analyze-only
# Revision creates a new run; all factual and PDF checks run again
.venv/bin/python scripts/generate_application.py job.txt --revision-of applications/PRIOR_RUN --notes "Emphasize LS-DYNA" --cv-length 2
```

`--language`, `--notes`, `--company`, `--role`, `--url` and `--cv-length` are passed to drafting. Fonts and margins stay fixed; overlong documents are shortened through content revision. The compiler rejects missing glyphs, text beyond margins, missing contact/skill text and extra pages. Additional language glyph support may be required beyond English/Italian/Swedish.

## Local tests and template preview

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/preview_layout.py
```

The preview uses explicitly selected source-backed content to demonstrate the new renderer, not live job tailoring. Automated tests use synthetic fixtures and fake model responses; an authenticated live run is a separate acceptance test. Never publish this repository: source documents, profile and generation traces contain personal data.

## Interrupted live runs

Codex account usage limits are reported separately from authentication errors, including the CLI's reset time when available. Wait for that allowance to reset and rerun the generation command. Diagnostics are written during model calls under each run's `traces/` directory, including when a call times out. A failed extraction does not replace the active profile, and failed application runs do not publish PDFs.

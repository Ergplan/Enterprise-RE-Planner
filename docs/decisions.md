# Decisions log

Dated entries. Every deviation from `docs/MASTER-PROMPT.md` is one.

## 2026-10-31 — Plan approved, repository seeded

- Product name ergPLAN under jouleWise; a separate product, not part of House of Rama.
- Every client-visible number carries regulation, page and a link opening the stored PDF at that page (invariant 1).
- First states: Uttar Pradesh (NPCL, PVVNL) and Maharashtra (MSEDCL). Then Karnataka, Gujarat, Rajasthan, Tamil Nadu, Telangana, Andhra Pradesh, Punjab, Haryana at Stage 8.
- Most clients have only bills: profile synthesis from 12 bills is a Stage 2 deliverable.
- IEX prices come from CSVs uploaded by jouleWise in the application.
- The regulation reader (tariff orders → draft rule rows with citations) is built in Stage 1, not later.
- Deliverable is a live shareable plan link with voice what-if and a jouleWise analyst view; PDF export of the same page.
- Thermal: captive coal and gas with waste heat as must-run; station fixed cost treated as sunk.
- Build machine: laptop Compose to Stage 4, then a Google Cloud VM in asia-south2.
- Stack and tooling as section 4 of the master prompt.

## 2026-11-01 — Stage 0 decisions

- **Model provider: OpenAI only for the app.** The regulation reader, explanations, voice and the stage reviewer use the OpenAI key from the Mac mini (`~/Downloads/Keys.rtf`, copied into the git-ignored `.env` only). No Anthropic API key is used anywhere; Claude builds on the subscription. Master prompt section 4 updated.
- **tariff-oder is upstream.** `Ergplan/tariff-oder` already reads tariff orders into reviewed, published facts with page-level evidence. ergPLAN imports its releases (`regreader/tariff_oder.py`) instead of rebuilding extraction; a direct OpenAI reader with a verbatim-quote grounding check covers documents tariff-oder does not (OA/banking regulations, CERC orders). Master prompt section 4 and Stage 1 updated.
- **Corpus from the Mac mini.** The tariff orders in `~/Downloads/India_DISCOM_Tariff_Orders_Final_2026` and `~/Downloads/Tariff Orders` are the regulation corpus. Their index `tariff-library.json` (regulator URL, schedule page ranges) is committed at `packages/rulebooks/corpus/`; the PDFs live in git-ignored `data/corpus/` and are registered by `python -m ergplan.documents.corpus`.
- **Build workspace without Docker.** The cloud build workspace has no Docker daemon. Services run natively there (Postgres 16 via `pg_ctl`, uvicorn, `next dev`); `docker/compose.yaml` is the deliverable for the Mac mini and is not exercised in the workspace. Flagged in known-gaps until someone runs it on the mini.
- **Harmony is vendored**, not installed as a package: `Ergplan/designsystem` has no published npm package. Copied to `apps/web/public/vendor/harmony` with the commit in `ORIGIN.txt`; `tools/dev/sync-harmony.sh` re-copies.
- **The document viewer renders pages as images** (`/documents/{id}/pages/{n}.png`) with an "Open the PDF at this page" link, because embedded PDF viewers are blank in headless browsers and inconsistent across browsers. The citation link `/documents/{id}#page=N` still opens the real PDF.
- **`SourcedValue.source_refs` is a list** (at least one), where invariant 1's prose says `source_ref`: a derived value carries every input's ref.
- **Web reaches the API through `/api/*` rewrites**, so the PDF link is same-origin.

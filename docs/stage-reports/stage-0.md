# Stage 0 report — skeleton

Date: 1 Nov 2026 · Builder: Claude (subscription) in the cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

- **API** (`apps/api`, Python 3.12, FastAPI, SQLAlchemy 2, Alembic): layout of master prompt 5.1 with every package stubbed and its stage named; `core.settings`, `core.units` (unit enum, the only conversions), `core.money` (Decimal parsing, floats refused), `core.sourced` (`SourceRef`, `SourcedValue` with at least one ref, `derive`, `stated`, `assumed`; a regulation/order ref must carry document, page and quote and resolves to `/documents/{id}#page=N`); `db.base.session_scope(actor, role)`; migration 0001 (`source_documents`, `model_calls`).
- **Documents store**: register a PDF by SHA-256 (same bytes → same row), page count, page PNG, page text; endpoints `/documents`, `/documents/{id}` (inline PDF), `/meta`, `/pages/{n}.png`, `/pages/{n}/text`.
- **Corpus loader** (`python -m ergplan.documents.corpus`): registers the PDFs indexed in `packages/rulebooks/corpus/tariff-library.json` with regulator URL and page hints parsed from the notes. **5 real orders registered** in the dev database: UPERC NPCL FY 2026-27 (423 pp., schedule 352–400), UPERC state DISCOMs FY 2026-27 (501 pp., schedule 408–458), MERC MSEDCL MYT Case 217/2024 (827 pp.), MERC Case 75/2025 orders of 25 Jun 2025 and 25 Mar 2026.
- **Web** (`apps/web`, Next.js 15.5, TypeScript strict): ergOS Harmony vendored with origin; the Harmony shell (ergPLAN wordmark, six journey steps disabled until their stage, analyst links, theme switch, jouleWise logo); `/`, `/documents` (library), `/documents/[id]?page=N` (rendered page, previous/next, section links from page hints, regulator's copy, open the PDF at this page). Checked in both themes with Playwright screenshots; no console errors.
- **Compose** for the Mac mini: postgres, api (migrates then serves), web (standalone), billx (built from `BILLX_REPO`), caddy.
- **Watcher** (`tools/watch/watch.py`): ruff, ruff format, mypy --strict, pytest, alembic drift, web typecheck, vitest, rulebook schema validation, field-trace drift, CLAUDE.md sync. **All 10 green.** CI runs the same with `--once`.
- **Reviewer** (`tools/review/run.sh N`): OpenAI, fresh context, diff + CLAUDE.md + stage prompt, fixed checklist, JSON findings, exits 1 on a code defect.
- **Tests**: 30 API tests (units, money, SourcedValue rules, documents service, corpus loader, every endpoint, architecture rules: only `providers/` may import a model SDK, pure packages never import `providers/`); 3 web tests.

## Skipped, and why

- `docker compose up` was not run: the build workspace has no Docker daemon. The same services ran natively (Postgres 16, uvicorn, next dev) and every check passed against them. First compose run is on the Mac mini (known-gaps).
- The Stage 0 e2e "upload a PDF, open it at page 3 in the web shell" ran with a real 423-page order instead (page 384 rendered in the viewer); Playwright shows the page image, since embedded PDF viewers are blank in headless browsers.

## Deviations from the master prompt

All recorded in `docs/decisions.md` (1 Nov 2026): OpenAI-only app models (no Anthropic key); tariff-oder as the upstream tariff-order pipeline; corpus from the Mac mini; native services instead of Docker in the workspace; Harmony vendored; page-image viewer; `source_refs` as a list.

## Reviewer findings

`docs/stage-reports/stage-0-review.md` (16 findings). Tokens in/out: 65443/2066.

| Finding | Resolution |
| --- | --- |
| `model_calls.cost_usd` is USD, not INR (flagged code defect) | **By design, not changed.** OpenAI prices and invoices in USD; this is internal telemetry, never a client value. Converting would need an FX rate that is itself a sourced value. Client-facing money stays INR. |
| `anthropic` still a dependency although the app is OpenAI-only | **Fixed**: removed from `pyproject.toml`. |
| Invariants 1–8 only structurally prepared | By design at Stage 0; each lands with its stage. |

## Open questions

1. Should the reviewer's cost (USD) appear in stage reports as INR at a stated rate, or stay USD?
2. The Mac mini's `~/apps` and `~/Documents` were not searched (folder access was declined). Are there OA/banking regulations or CERC orders there that should join the corpus?
3. `Banking Rule - Uttar Pradesh.pdf` (23 MB) and the RTM/DAM 15-minute files on the mini were not staged before the interruption; I'll stage them at Stage 1 and Stage 2 unless you'd rather I didn't.

## Cost

Reviewer: one gpt-5.1 call. Tokens in/out: 65443/2066. Builder: Claude subscription.

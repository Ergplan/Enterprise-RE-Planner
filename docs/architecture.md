# ergPLAN architecture

Living document. Updated in the same commit as any code that changes it (rule 14).

## Components

```
Browser ──► web (Next.js 15, ergOS Harmony, :3000)
              │  /api/* rewritten to the API (same origin, so /api/documents/{id}#page=N opens in place)
              ▼
            api (FastAPI, :8000) ── documents/ (PDF store by SHA-256, page PNG and text)
              │                 ── rulebook/, regreader/        (Stage 1)
              │                 ── intake/ ──► billx sidecar    (Stage 2)
              │                 ── engine/, settlement/, optimizer/  (pure, Stages 3–6)
              │                 ── providers/ ──► OpenAI        (only model caller)
              ▼
            PostgreSQL 16  (alembic migrations; audit triggers from Stage 1)
            data/documents/<sha256>.pdf   (the regulation corpus, git-ignored)
```

Upstream sources: `Ergplan/tariff-oder` (published, reviewed tariff-order facts, Stage 1 adapter), billx (bills, contract esgos-1.1), IEX CSV uploads (Stage 2), the regulation corpus registered from `packages/rulebooks/corpus/tariff-library.json`.

## Data model

| Table | Holds | Writer | Audited by | Since |
| --- | --- | --- | --- | --- |
| `source_documents` | One row per regulation PDF: title, regulator, state, utilities, SHA-256, pages, order date, regulator URL (`url_public`), notes, `page_hints` (named PDF page ranges such as `schedule: [352, 400]`) | `documents.service.register` | — (immutable once written; same bytes return the same row) | 0 |
| `model_calls` | One row per OpenAI call: model, prompt name and version, purpose, tokens, cost, status | `providers` | — | 0 |

## Critical path

bill → `intake.site_intake.build()` → `engine.tariff_eval.replay()` → `engine.landed_cost.evaluate()` → `settlement.simulate()` → `optimizer.solve()` → `optimizer.resettle()` → `report.plan.build()`. Stage 0 builds the citation end of it: `core.sourced.SourcedValue` (every client number) and `documents.service` (the page a citation opens).

## Packages (apps/api/ergplan)

| Package | Holds | Stage |
| --- | --- | --- |
| `core` | `settings` (env and `.env`), `units` (the unit enum and the only conversions), `money` (Decimal parsing, floats refused), `sourced` (`SourceRef`, `SourcedValue`, `derive`, `stated`, `assumed`), `ids` | 0 |
| `db` | `base` (engine; `session_scope(actor, role)` sets `ergplan.actor`/`ergplan.role` for triggers), `models` | 0 |
| `documents` | `service` (register by SHA-256, page count, render page PNG, page text), `corpus` (register the indexed corpus with regulator URLs and page hints; `python -m ergplan.documents.corpus --root …`) | 0 |
| `platform` | `app` (FastAPI, `/health`), `routers/documents` | 0 |
| `rulebook`, `regreader`, `providers`, `intake`, `engine`, `settlement`, `optimizer`, `voice`, `report` | Empty, docstring names the stage | 1–7 |

## API surface

| Method | Path | What |
| --- | --- | --- |
| GET | `/health` | Database version and migration head |
| GET | `/documents?jurisdiction=` | Registered documents |
| POST | `/documents` | Upload a PDF (multipart `file`, `title`, `regulator`, `jurisdiction`, `document_kind`, `url_public`) |
| GET | `/documents/{id}` | The PDF, `Content-Disposition: inline`, so `#page=N` opens at the page |
| GET | `/documents/{id}/meta` | The row |
| GET | `/documents/{id}/pages/{n}.png` | Page image (pypdfium2) |
| GET | `/documents/{id}/pages/{n}/text` | Page text layer |

## Web (apps/web)

ergOS Harmony vendored at `public/vendor/harmony` (origin in `ORIGIN.txt`, re-copied by `tools/dev/sync-harmony.sh`); `app/ergplan.css` adds tables and the viewer using tokens only. `components/Shell.tsx` is the 264 px sidebar (six journey steps, disabled until their stage ships; jouleWise analyst links) and top bar with the theme switch. Pages: `/` (how it works), `/documents` (library), `/documents/[id]?page=N` (rendered page with previous/next, section links from `page_hints`, regulator's copy, open the PDF at this page).

## Deployment

`docker/compose.yaml`: postgres, api (migrates then serves), web (Next standalone), billx (built from `BILLX_REPO`, default a sibling `billx` checkout), caddy (`:8080`, `/api/*` → api). Mac mini first; Google Cloud VM later. The build workspace has no Docker daemon, so Stage 0 ran the same services natively (Postgres 16, uvicorn, next dev).

## What changed

- **Stage 0**: skeleton, `SourcedValue`, documents store and corpus loader (5 real orders registered: UPERC NPCL and state DISCOMs FY 2026-27, MERC MSEDCL MYT and two Case 75/2025 orders), Harmony shell, documents library and page viewer, compose, watcher, CI, reviewer.

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
| `model_calls` | One row per OpenAI call: model, prompt name and version, purpose, tokens, cost (USD), status | `providers.openai_client` | — | 0 |
| `jurisdictions` | States, regulators, DISCOMs (billx profile ids), groups (`uppcl`) with parents | `rulebook.service.sync_jurisdictions` from `packages/rulebooks/jurisdictions.yaml` | — | 1 |
| `rulebook_versions` | One version of one family for one jurisdiction: status draft/approved/superseded/rejected, effective dates, origin, golden status, approver | `rulebook.service` only | trigger `ergplan_audit`; gate trigger `ergplan_version_gate` (analyst role + all golden tests passed) | 1 |
| `rules` | Rule rows: `scope`, `body` (family schema), `source_ref`, `field_refs`, `label`, `review` | `rulebook.service` only | trigger `ergplan_audit`; trigger `ergplan_rules_frozen` (rows of a non-draft version cannot change) | 1 |
| `rule_tests`, `rule_test_runs` | Golden cases per jurisdiction and family; their runs per version | `rulebook.golden` | `ergplan_audit` on `rule_tests` | 1 |
| `audit_log` | Every write to the audited tables: actor, action, before, after | triggers | — | 1 |
| view `rules_approved` | Rules of approved versions: the only rows engines read (invariant 2) | — | — | 1 |

## Critical path

bill → `intake.site_intake.build()` → `engine.tariff_eval.replay()` → `engine.landed_cost.evaluate()` → `settlement.simulate()` → `optimizer.solve()` → `optimizer.resettle()` → `report.plan.build()`. Stage 0 builds the citation end of it: `core.sourced.SourcedValue` (every client number) and `documents.service` (the page a citation opens).

## Packages (apps/api/ergplan)

| Package | Holds | Stage |
| --- | --- | --- |
| `core` | `settings` (env and `.env`), `units` (the unit enum and the only conversions), `money` (Decimal parsing, floats refused), `sourced` (`SourceRef`, `SourcedValue`, `derive`, `stated`, `assumed`), `ids` | 0 |
| `db` | `base` (engine; `session_scope(actor, role)` sets `ergplan.actor`/`ergplan.role` for triggers), `models` | 0 |
| `documents` | `service` (register by SHA-256, page count, render page PNG, page text), `corpus` (register the indexed corpus with regulator URLs and page hints; `python -m ergplan.documents.corpus --root …`) | 0 |
| `documents` (Stage 1) | `ocr` (tesseract fallback for scanned pages, stored under `data/ocr/<sha256>/`) | 1 |
| `rulebook` | `schemas` (JSON Schemas with refs), `scope` (`matches`, `specificity`, `norm_code`), `service` (propose, revise, update_row, delete_row, duplicate, run_golden, approve, reject; jurisdictions and chain), `golden` (files → `rule_tests`, evaluation with `where` filters), `repository` (`approved_rules`, `applicable` — engines' only door), `sandbox` (drafts, analyst only), `yaml_io` (export approved → `packages/rulebooks/states`, import, restore keeping version and origin), `cli` | 1 |
| `regreader` | `direct` (pages → OpenAI → grounded rows), `grounding` (quote on page, fragments, OCR word order, numbers printed, worded zero and waiver), `tariff_oder` (published facts → rows), `voltage` (band phrases), `locate` (topic pages) | 1 |
| `providers` | `openai_client.call_json` (versioned prompt, retries, `model_calls` row), `prompts/regreader_<family>_v2.md`, `prices.yaml` | 1 |
| `platform` | `app` (FastAPI, `/health`), `auth` (dev headers until Stage 8), `routers/documents`, `routers/rulebooks`, `routers/regreader` | 0–1 |
| `intake`, `engine`, `settlement`, `optimizer`, `voice`, `report` | Empty, docstring names the stage | 2–7 |

## API surface

| Method | Path | What |
| --- | --- | --- |
| GET | `/health` | Database version and migration head |
| GET | `/documents?jurisdiction=` | Registered documents |
| POST | `/documents` | Upload a PDF (multipart `file`, `title`, `regulator`, `jurisdiction`, `document_kind`, `url_public`) |
| GET | `/documents/{id}` | The PDF, `Content-Disposition: inline`, so `#page=N` opens at the page |
| GET | `/documents/{id}/meta` | The row |
| GET | `/documents/{id}/pages/{n}.png` | Page image (pypdfium2) |
| GET | `/documents/{id}/pages/{n}/text` | Page text (text layer, or OCR for scanned pages) |
| GET | `/rulebooks/jurisdictions`, `/rulebooks/families` | Jurisdictions; family JSON Schemas |
| GET | `/rulebooks/versions?jurisdiction=&family=&status=`, `/rulebooks/versions/{id}` | Versions; one version with rows and golden results |
| POST | `/rulebooks/versions` | Propose a draft (analyst) |
| PUT, DELETE | `/rulebooks/versions/{id}/rows/{rid}` | Edit or delete a draft row (analyst) |
| POST | `/rulebooks/versions/{id}/golden`, `/approve`, `/reject`, `/duplicate` | Golden run, approval gate, reject, copy into a draft (analyst) |
| GET | `/regreader/locate/{document_id}?topic=` | Pages that print a topic |
| POST | `/regreader/direct` | Read pages into a draft (analyst; OpenAI) |
| POST | `/regreader/tariff-oder` | Import tariff-oder published facts into drafts (analyst) |

## Web (apps/web)

ergOS Harmony vendored at `public/vendor/harmony` (origin in `ORIGIN.txt`, re-copied by `tools/dev/sync-harmony.sh`); `app/ergplan.css` adds tables and the viewer using tokens only. `components/Shell.tsx` is the 264 px sidebar (six journey steps, disabled until their stage ships; jouleWise analyst links) and top bar with the theme switch. Pages: `/` (how it works), `/documents` (library), `/documents/[id]?page=N` (rendered page with previous/next, section links from `page_hints`, regulator's copy, open the PDF at this page).

## Deployment

`docker/compose.yaml`: postgres, api (migrates then serves), web (Next standalone), billx (built from `BILLX_REPO`, default a sibling `billx` checkout), caddy (`:8080`, `/api/*` → api). Mac mini first; Google Cloud VM later. The build workspace has no Docker daemon, so Stage 0 ran the same services natively (Postgres 16, uvicorn, next dev).

## Rulebooks seeded (Stage 1)

| Jurisdiction | Families | Source | Golden tests |
| --- | --- | --- | --- |
| `npcl` | tariff_schedule (HV-2 urban, 4 voltage bands), tod_slots (summer, winter), oa_charge (wheeling 1.03, CSS by band, AS 0) | UPERC NPCL FY 2026-27 order pp. 315–388 | 26 |
| `uppcl` (PVVNL, MVVNL, PuVVNL, DVVNL, KESCO) | tariff_schedule, tod_slots, oa_charge (wheeling 0.9318, OA distribution losses, CSS) | UPERC State DISCOMs FY 2026-27 order pp. 379–446 | 24 |
| `UP` | oa_charge (intra-state transmission 0.3075/kWh, ISTS loss 1.56%, STU loss 3.18%), settlement (captive banking, CRE Regulations 2024) | UPERC State DISCOMs order pp. 377, 384; CRE Regulations 2024 pp. 14–20 (OCR) | 16 |
| `msedcl` | tariff_schedule (HT I(A), HT II; EHV and HT), tod_slots, oa_charge (CSS 2.11), settlement (monthly ToD-slot banking) | MERC Case 75/2025 post-remand order of 25 Mar 2026, pp. 77–106 | 25 |

## What changed

- **Stage 1**: migration 0002 (rulebook tables, audit/frozen/approval triggers, `rules_approved` view); rulebook package; regulation reader (direct with grounding, tariff-oder import); OpenAI provider with versioned prompts; OCR fallback; document ids derived from SHA-256; rulebook and reader API; analyst UI; 12 approved rulebooks for UP and Maharashtra with 91 golden tests; committed rulebooks round-trip test.
- **Stage 0**: skeleton, `SourcedValue`, documents store and corpus loader (5 real orders registered: UPERC NPCL and state DISCOMs FY 2026-27, MERC MSEDCL MYT and two Case 75/2025 orders), Harmony shell, documents library and page viewer, compose, watcher, CI, reviewer.

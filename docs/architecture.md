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
| `clients`, `sites`, `connections` | Who, where, which supply (DISCOM, category, voltage, contract demand, kind); `provenance` JSONB per field (bill / client_stated / assumption with its source_ref) | `intake.site_intake.build` | — | 2 |
| `bills` | billx's whole result per bill (`billx_result` JSONB with every field's proof and verification), status, `accepted`, `accepted_by` (engine / human / bill_confirmations), file SHA-256 (the PDF kept under `data/bill_files/`) | `intake.bills.ingest`, `intake.bills.confirm` | — | 2 |
| `bill_confirmations` | One row per client confirmation or correction of a bill value: path, value, who, when (invariant 7) | `intake.bills.confirm` | append-only | 2 |
| `assets` | Existing rooftop PV, captive thermal, waste heat, BESS, DG with params validated per kind | `intake.site_intake.build` | — | 2 |
| `load_profiles` | Versioned 15-minute year per connection: provenance measured/synthesised/stated (check constraint), zlib-compressed Decimal kW, `method` JSONB (shape, per-month targets and achieved values, the intake it was built from) | `intake.site_intake.synthesise`, `intake.measured_upload.store` | — | 2 |
| `price_vintages`, `price_series` | One vintage per uploaded IEX file (segment, SHA-256, rows, duplicates, dates, superseded_by); 15-minute MCP and MCV per (vintage, day, block) | `intake.iex_loader.store` | rows never deleted; a replaced vintage is marked superseded so pinned runs replay | 2 |

## Critical path

bill → `intake.bills.ingest()` → `intake.site_intake.build()` → `engine.tariff_eval.replay()` → `engine.landed_cost.evaluate()` → `settlement.simulate()` → `optimizer.solve()` → `optimizer.resettle()` → `report.plan.build()`. Stage 0 builds the citation end of it: `core.sourced.SourcedValue` (every client number) and `documents.service` (the page a citation opens).

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
| `platform` | `app` (FastAPI, `/health`), `auth` (dev headers until Stage 8), `routers/documents`, `routers/rulebooks`, `routers/regreader`, `routers/intake`, `routers/prices`, `routers/cost` (loads approved rules, calls the engines), `routers/landed` (step 3, limits) | 0–4 |
| `intake` | `billx_client` (contract esgos-1.1 over HTTP, submit and poll), `bill_fields` (billx field objects → Decimals with verification), `bills` (ingest once per file, review, one-click confirm, values with `bill` source_refs), `defaults` (normative defaults as `assumption` refs; printed category → order category; billx profile → DISCOM), `site_intake` (`SiteIntake` of `Fact`s, `from_bills`, `build`, `synthesise`), `profile_synthesis` (shapes → a year, window energy exact, peak = MD × PF), `measured_upload` (meter CSV, gaps), `iex_loader` (xlsx/csv snapshots, vintages, coverage) | 2 |
| `engine` | Pure, no database or network: `scope` (connection facts → scope context; `pick`/`first` nearest jurisdiction then most specific row), `tariff_eval` (`evaluate(schedule, tod, MonthQuantities)` → cited lines: demand on billing demand with floor and excess, energy by ToD slot with surcharge/rebate, retail wheeling, FPPCA, duty, PF, LF, minimum charge, taxes, prompt-payment rebate; what a row does not state becomes a named gap), `replay` (billx elements → billed line groups; quantities and ToD zones from the bill; group-by-group comparison; match / explained / unexplained), `avoided_cost` (month × 96-block rate matrix, rate cards per month and slot, annual energy and demand lines), `gaps` (the named rule gaps, mirrored in known-gaps) | 3 |
| `engine` (Stage 4) | `landed_cost` (20 sources; `evaluate(spec, ctx, Scenario, oa_rows, ists_waivers, settlement)` → waterfall: price, injection charges, loss gross-up, capacity charges over scheduled energy, drawal charges, banking upper bound, ISTS waiver, exemptions with sunset; `coefficient()` = a·P + b for block series), `lcoe` / `lcos` (CRF, LCOE with degradation, LCOS; every input an assumption ref) | 4 |
| `settlement`, `optimizer`, `voice`, `report` | Empty, docstring names the stage | 4–7 |

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
| POST | `/bills` | Upload a bill PDF (multipart `file`, optional `connection_id`); billx reads it (once per file); returns each bill with its fields, verification and what still needs confirming |
| GET | `/bills/{id}`, `/bills/{id}/file` | One bill; the stored PDF inline (a `bill` source_ref opens it at `#page=N`) |
| POST | `/bills/{id}/confirm` | Confirm or correct one value (`path`, `value`); the bill becomes usable when nothing is outstanding |
| GET | `/intake/shapes` | The eight industry shapes |
| POST | `/intake/from-bills` | A `SiteIntake` prefilled from accepted bills (not saved), with `overrides` |
| POST | `/sites` | Save a `SiteIntake` (new or `connection_id`) and synthesise a load profile version |
| GET | `/connections/{id}`, `/connections/{id}/intake` | The connection with site, client, bills, profiles; the intake its latest profile was built from |
| GET | `/connections/{id}/profile?version=`, `/connections/{id}/profile.csv` | Profile summary (months as `SourcedValue`s, a week for the chart); all 35,040 blocks |
| POST | `/connections/{id}/profile/measured` | Upload a meter CSV as a measured profile version |
| POST | `/prices` | Upload an IEX file (analyst; `segment`, `replace`); 409 on overlap |
| GET | `/prices/vintages?segment=`, `/prices/coverage?segment=` | Vintages; blocks per day of live vintages |
| GET | `/connections/{id}/replay` | Each accepted bill rebuilt from the tariff in force on its period end, line groups with billed, computed (SourcedValue), difference, status and the gap that explains it; the computed tariff lines |
| GET | `/connections/{id}/landed-cost?scenario=` | Every source's waterfall per ToD slot at the meter (SourcedValue lines), the grid's avoided cost per slot, regulatory limits, gaps; `scenario` is JSON: month, as_of, geoa, per-source price, ownership, commissioning date, capacity, CUF, equity cost |
| GET | `/rulebooks/limits?connection_id=` | Approved regulatory limits that apply to the connection |
| GET | `/prices/vintages/{id}` | One price vintage (a `market` source_ref resolves here) |
| GET | `/connections/{id}/avoided-cost?as_of=&version=` | Avoided cost of a grid kWh: 12 × 96 matrix (INR/kWh), rate cards with cited components and the kVAh/kWh factor, annual energy and demand lines; `as_of` picks the tariff (default today) |

## Web (apps/web)

ergOS Harmony vendored at `public/vendor/harmony` (origin in `ORIGIN.txt`, re-copied by `tools/dev/sync-harmony.sh`); `app/ergplan.css` adds tables and the viewer using tokens only. `components/Shell.tsx` is the 264 px sidebar (six journey steps, disabled until their stage ships; jouleWise analyst links) and top bar with the theme switch. Pages: `/` (how it works), `/documents` (library), `/documents/[id]?page=N` (rendered page with previous/next, section links from `page_hints`, regulator's copy, open the PDF at this page). Stage 2: `/plan/intake` (journey step 1: drop bills, confirm values billx could not verify, or type the facts; then "what we understood" with a provenance chip on every value), `/plan/site?c=` (step 4: the profile with a week chart and months with their sources, the site description and existing assets, rebuild), `/prices` (analyst: upload, vintages, coverage calendar per segment). `components/intake/*`, `components/prices/*`, `lib/intake.ts`. Stage 3: `/plan/today?c=` (journey step 2: each bill rebuilt beside the real one with differences highlighted, page chips that open the order PDF at the page with the quote on hover, a "how computed" table, the named gaps; the avoided-cost heatmap month × time of day with rate cards), `components/cost/*`, `lib/cost.ts`. Stage 4: `/plan/landed?c=&month=&view=analyst` (journey step 3: comparison bars of every source against the grid by slot; one card per source with its waterfall, citations and "saves/costs vs grid"; the jouleWise view lists the rule rows behind each card; month switch).

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

- **Stage 4**: `engine/landed_cost.py`, `engine/lcoe.py`, `engine/lcos.py`; `/connections/{id}/landed-cost`, `/rulebooks/limits`, `/prices/vintages/{id}`; `SourceRef` kind `market` (IEX prices cite their vintage); journey step 3; rulebook corrections through the gate: UP `oa_charge` v2 (ISTS loss only for inter-state), NPCL v4 and UPPCL v3 (wheeling, losses, CSS, AS apply to inter-state OA consumers too; captive and group-captive CSS exemption from CRE Regulations 2024 Reg. 11.II, p. 13); draft six-consumer spreadsheets `tests/fixtures/landed_cost_up.csv`, `landed_cost_mh.csv` (awaiting jouleWise approval).

- **Stage 3**: engine (scope, tariff evaluator, bill replay, avoided cost, named gaps); `/connections/{id}/replay` and `/avoided-cost`; journey step 2; `SourceRef.url` serialised on every ref (and ignored on input); UP `rate_block` default (urban, assumed); MSEDCL `tod_slots` v3 (peak +25% for HT industrial and commercial, MYT order p. 565), NPCL and UPPCL `tariff_schedule` v2 (billable demand ≥ 75% of contract, excess at 200%, general provisions pp. 354–355 and 410–411); fifteen real bills read through billx and cached under `data/bills/billx-results/` (gitignored) for the replay test.

- **Stage 2**: migration 0006 (clients, sites, connections, bills, bill_confirmations, assets, load_profiles, price_vintages, price_series); `SourceRef` kind `bill` (bill id and billx path, opens the stored bill at its page); intake package (billx client, bill review and confirmations, SiteIntake with sourced defaults, profile synthesis from eight shapes, meter upload, IEX loader); intake and prices API; journey steps 1 and 4 and the analyst prices page; billx contract fixtures in `apps/api/tests/fixtures/billx/` (synthetic, copied from billx `contract/examples`); real-bill end-to-end (NPCL and MSEDCL) through the running billx.

- **Stage 1**: migration 0002 (rulebook tables, audit/frozen/approval triggers, `rules_approved` view); rulebook package; regulation reader (direct with grounding, tariff-oder import); OpenAI provider with versioned prompts; OCR fallback; document ids derived from SHA-256; rulebook and reader API; analyst UI; 12 approved rulebooks for UP and Maharashtra with 91 golden tests; committed rulebooks round-trip test.
- **Stage 0**: skeleton, `SourcedValue`, documents store and corpus loader (5 real orders registered: UPERC NPCL and state DISCOMs FY 2026-27, MERC MSEDCL MYT and two Case 75/2025 orders), Harmony shell, documents library and page viewer, compose, watcher, CI, reviewer.

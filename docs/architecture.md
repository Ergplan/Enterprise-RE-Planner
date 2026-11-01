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
| `scenarios` | What to size for a connection: `spec` JSONB (`optimizer.scenarios.ScenarioSpec`: candidates with ownership, quoted price, max/min MW; as-of date; resolution 15 or 60 min; contract-demand step option; lapse price; grid emission factor; sensitivity ranges) | `platform.routers.runs.create_scenario` | trigger `ergplan_audit` | 6 |
| `runs` | One solve: status queued/running/done/failed/failed_resettle (check), the spec as run, `pins` (every rulebook version read, load profile id and version, price vintages by segment, solver version, as-of), solver stats (status, MIP gap, seconds, objective), `replay_of` | `platform.runs` (create, execute; the worker) | trigger `ergplan_audit` (refuses a write without `ergplan.actor`) | 6 |
| `share_links` | Token (unguessable, 24 random bytes) → connection; who made it; revoked_at | `report.share.create` | — | 7 |
| `explanations` | Model-drafted explanation per input (SHA-256 of prompt + the SourcedValues explained), with the `model_calls` id | `report.explain.explain` | — (each draft is a `model_calls` row) | 7 |
| `users` | Email, role analyst/client (analyst: `ERGPLAN_ANALYST_DOMAIN` or `ERGPLAN_ANALYST_EMAILS`), last sign-in | `platform.routers.auth.verify` | — | 8 |
| `login_tokens`, `auth_sessions` | One-time sign-in links and signed-in browsers, by SHA-256 only; expiry, used/revoked | `platform.routers.auth` | — | 8 |
| `run_results` | Per run: client summary (SourcedValues), re-settlement check per month, the settled dispatch (zlib JSON per block), `digest` (SHA-256 of the canonical summary, compared on replay) | `platform.runs.execute` | written once per run with the audited `runs` update | 6 |

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
| `platform` | `app` (FastAPI, `/health`), `auth` (dev headers until Stage 8), `routers/documents`, `routers/rulebooks`, `routers/regreader`, `routers/intake`, `routers/prices`, `routers/cost` (loads approved rules, calls the engines), `routers/landed` (step 3, limits), `routers/settle` (analyst settlement) | 0–5 |
| `intake` | `billx_client` (contract esgos-1.1 over HTTP, submit and poll), `bill_fields` (billx field objects → Decimals with verification), `bills` (ingest once per file, review, one-click confirm, values with `bill` source_refs), `defaults` (normative defaults as `assumption` refs; printed category → order category; billx profile → DISCOM), `site_intake` (`SiteIntake` of `Fact`s, `from_bills`, `build`, `synthesise`), `profile_synthesis` (shapes → a year, window energy exact, peak = MD × PF), `measured_upload` (meter CSV, gaps), `iex_loader` (xlsx/csv snapshots, vintages, coverage) | 2 |
| `engine` | Pure, no database or network: `scope` (connection facts → scope context; `pick`/`first` nearest jurisdiction then most specific row), `tariff_eval` (`evaluate(schedule, tod, MonthQuantities)` → cited lines: demand on billing demand with floor and excess, energy by ToD slot with surcharge/rebate, retail wheeling, FPPCA, duty, PF, LF, minimum charge, taxes, prompt-payment rebate; what a row does not state becomes a named gap), `replay` (billx elements → billed line groups; quantities and ToD zones from the bill; group-by-group comparison; match / explained / unexplained), `avoided_cost` (month × 96-block rate matrix, rate cards per month and slot, annual energy and demand lines), `gaps` (the named rule gaps, mirrored in known-gaps) | 3 |
| `engine` (Stage 4) | `landed_cost` (20 sources; `evaluate(spec, ctx, Scenario, oa_rows, ists_waivers, settlement)` → waterfall: price, injection charges, loss gross-up, capacity charges over scheduled energy, drawal charges, banking upper bound, ISTS waiver, exemptions with sunset; `coefficient()` = a·P + b for block series), `lcoe` / `lcos` (CRF, LCOE with degradation, LCOS; every input an assumption ref) | 4 |
| `settlement` | `simulate` (pure: blocks with slot and slot classes, sources with set-off category, the approved rule → per-block grid drawal, set-off (against load and at source), deposits net of the charge in kind, withdrawals, unbanked surplus; per period lapse and balances by bucket; granularities block_15min, hourly, tod_slot_monthly, monthly_aggregate, annual; FIFO lots; drawal windows with months; carry-over with the higher/lower ceiling; FY-end lapse), `statement` (the year as cited SourcedValue lines) | 5 |
| `intake` (Stage 5) | `generation` (normative 15-minute generation from `packages/profiles/cuf`, scaled to annual CUF; hybrid = solar + wind) | 5 |
| `optimizer` | `model` (pure Pyomo: `Problem` of blocks, grid rates and demand terms, candidate sources, batteries, thermal units, the settlement rule and limits → `build()` the sizing MILP; `build_settlement()` the settlement pass; `netting()` shares `settlement.simulate.Bank`'s bucket and window logic; `coarsen()`, `chunk()`), `highs_solve.solve()` (sizing on hourly blocks → 15-minute dispatch month by month with sizes fixed → settlement pass per banking period; HiGHS one thread, time limit and MIP gap from settings), `resettle.resettle()` (the judge: `settlement.simulate()` on the solver's dispatch, monthly comparison, costs from the judge's quantities, `status_quo()`), `scenarios` (spec models, IRR, payback, repricing) | 6 |
| `platform` (Stage 6) | `runs` (assemble a `Problem` from approved rules through a recording `rulebook.repository.Reader`, the load profile and price vintages; execute, store with pins; replay through `Reader(pins)` → `repository.pinned_rules`), `worker` (`python -m ergplan.platform.worker`: claims queued runs with `FOR UPDATE SKIP LOCKED`) | 6 |
| `report` (Stage 7) | `plan.build()` (the live plan: facts, settled scenarios, the recommended one, editable assumptions, every cited document with its pages; the jouleWise view adds pins, rule versions, solver and judge margins), `share` (tokens), `whatif.evaluate()` (sizes held, change applied, hourly dispatch and settlement, the judge again, one sentence from the numbers), `pdf.export()` (Playwright Chromium prints `/p/{token}?print=1`), `explain.explain()` (OpenAI through `providers/`, prompt `explain_v1`, cached) | 7 |
| `platform` (Stage 8) | `auth` (session cookie from the email link; development headers only when `ERGPLAN_ENV=dev`; the app-wide `guard`: public routes, sign-in, ownership of connections, sites, bills, scenarios and runs by the client's creator), `mail` (SMTP or the log), `routers/auth` (`/auth/request`, `/auth/verify`, `/auth/me`, `/auth/logout`); security headers; CORS with credentials for the public URL only in production | 8 |
| `voice` (Stage 7) | `tools` (typed tools: SiteIntake setters for intake, what-if setters for the plan; `apply()` validates and returns the new state and one sentence) | 7 |
| `providers` (Stage 7) | `realtime_secret()` (ephemeral OpenAI Realtime client secret with the session's instructions `voice_v1` and tools), `chat_with_tools()` (text chat with the same tools) | 7 |

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
| POST | `/connections/{id}/settle` | Analyst: settle open-access sources (normative curve or 15-minute kW) against the latest load profile under the approved settlement rule → cited statement, month table with bucket balances |
| GET | `/rulebooks/limits?connection_id=` | Approved regulatory limits that apply to the connection |
| GET | `/prices/vintages/{id}` | One price vintage (a `market` source_ref resolves here) |
| POST, GET | `/sites/{id}/scenarios` | Create a scenario (analyst; `connection_id`, `name`, `spec`); list a site's scenarios with each one's latest original run (clients see only settled runs) |
| POST | `/scenarios/{id}/run?wait=` | Queue a run for the worker (analyst); `wait=true` solves in the request |
| GET | `/runs/{id}` | Status, pins, solver stats, the summary (sizes, annual cost before/after, saving, capex, payback, IRR, emissions, settlement, contract demand, binding constraints in plain words with citations, sensitivities, provenance); analyst block with the re-settlement check and cost lines. 404 to clients unless the run settled (invariant 6) |
| GET | `/runs/{id}/dispatch?start=&days=` | The settled dispatch for up to 14 days (default: the week with the highest load) |
| POST | `/runs/{id}/replay?wait=` | Recompute from the pins (analyst); `identical_to_original` compares every result to the paisa (invariant 5) |
| POST | `/connections/{id}/plan?as_of=&resolution_min=&wait=` | Size the three standard scenarios for a connection, no analyst needed; nothing duplicated |
| GET | `/connections/{id}/plan` | The plan for a connection (client view) |
| POST | `/connections/{id}/share` | A share token for the plan (`/p/{token}`) |
| GET | `/p/{token}?view=` | The live plan, logged out; `view=analyst` (analyst role only, else 403) adds the jouleWise view |
| GET | `/p/{token}/pdf` | The plan printed by Chromium, citations as numbered notes, documents as an appendix |
| POST | `/p/{token}/whatif` | Price, capacity, contract demand, sources off, rules date → hourly settled answer and one sentence |
| POST | `/p/{token}/explain` | An explanation of a waterfall or a binding constraint, with the sourced values beside it |
| POST | `/voice/session` | Ephemeral OpenAI Realtime secret (intake or plan mode) with the session's tools |
| POST | `/voice/tool`, GET `/voice/tools?mode=` | Run one tool on the browser-held state (the Realtime model's function calls are relayed here); the tool schemas |
| POST | `/chat` | Text chat with the same tools (the model asks, the API runs, the model reads back) |
| POST | `/auth/request`, `/auth/verify`, `/auth/logout`; GET `/auth/me` | Sign-in by email link; session cookie; who is signed in, whether sign-in is required, whether they have a password |
| POST | `/auth/login`, `/auth/password`, `/auth/users` | Sign-in by email and password (10 wrong tries in 15 minutes are refused); set or change one's password (the current one to change it); an analyst adds a person or resets a password |
| GET | `/rulebooks/coverage?on=` | Per state: which rule families are approved on the date, else "not yet sourced" |
| GET | `/connections/{id}/avoided-cost?as_of=&version=` | Avoided cost of a grid kWh: 12 × 96 matrix (INR/kWh), rate cards with cited components and the kVAh/kWh factor, annual energy and demand lines; `as_of` picks the tariff (default today) |

## Web (apps/web)

ergOS Harmony vendored at `public/vendor/harmony` (origin in `ORIGIN.txt`, re-copied by `tools/dev/sync-harmony.sh`); `app/ergplan.css` adds tables and the viewer using tokens only. `components/Shell.tsx` is the 264 px sidebar (six journey steps, disabled until their stage ships; jouleWise analyst links) and top bar with the theme switch. Pages: `/` (how it works), `/documents` (library), `/documents/[id]?page=N` (rendered page with previous/next, section links from `page_hints`, regulator's copy, open the PDF at this page). Stage 2: `/plan/intake` (journey step 1: drop bills, confirm values billx could not verify, or type the facts; then "what we understood" with a provenance chip on every value), `/plan/site?c=` (step 4: the profile with a week chart and months with their sources, the site description and existing assets, rebuild), `/prices` (analyst: upload, vintages, coverage calendar per segment). `components/intake/*`, `components/prices/*`, `lib/intake.ts`. Stage 3: `/plan/today?c=` (journey step 2: each bill rebuilt beside the real one with differences highlighted, page chips that open the order PDF at the page with the quote on hover, a "how computed" table, the named gaps; the avoided-cost heatmap month × time of day with rate cards), `components/cost/*`, `lib/cost.ts`. Stage 4: `/plan/landed?c=&month=&view=analyst` (journey step 3: comparison bars of every source against the grid by slot; one card per source with its waterfall, citations and "saves/costs vs grid"; the jouleWise view lists the rule rows behind each card; month switch). Stage 5: `/settlement?c=` (analyst settlement explorer: sources, the year's cited statement, month-by-month stacks of set-off, bank and grid with bucket balances). Stage 6: `/plan/optimise?c=&as_of=` (journey step 5: scenario cards side by side with sizes, saving, cost before and after, payback, IRR, grid CO₂; analysts queue the three standard scenarios at 15 minutes or hourly; the settled dispatch for a chosen week as a stacked chart under the load line; binding constraints with citation chips; price sensitivities; the judge's agreement for analysts), `components/optimise/*`, `lib/runs.ts`. Stage 7: the rail remembers the site (`?c=` → localStorage) so every step opens it; `/plan/intake` "Tell me about your site" door is voice or text with the intake tools, then the same review as typing; `/plan/report?c=` (step 6: build my plan, progress, share); `/p/[token]` (the live plan without the rail: recommended option with citations, the options compared, each source's waterfall with "Explain", binding constraints, what-if chips and voice/text what-if, documents appendix, the jouleWise view for analysts; `?print=1` the printed layout with numbered notes); `components/plan/*`, `components/voice/VoicePanel.tsx` (WebRTC to OpenAI Realtime with the ephemeral secret; tool calls relayed to `/api/voice/tool`), `lib/plan.ts`.

## Deployment

**Google Cloud VM `replanner` (1 Nov 2026, the server):** `docker/compose.prod.yaml` over `compose.yaml` (Caddy on 80/443, TLS for `SITE_ADDRESS`); `tools/dev/vm-install.sh` installs and updates from a git bundle over SSH (from the Mac mini); `tools/dev/vm.sh` runs compose with `.env`; `tools/dev/vm-push.sh` does the same from a Mac with the Google Cloud CLI; backups by root's cron.

**Mac mini (1 Nov 2026, LAN alternative):** `docker/compose.mini.yaml` over `compose.yaml` and `compose.prod.yaml` — Caddy on LAN port 80, production mode, worker concurrency 4; `tools/dev/mini.sh` runs compose with `.env`; `tools/dev/mini-install.sh` installs and updates it from a git bundle; backups by launchd into `~/ergplan-backups`. `python -m ergplan.platform.signin EMAIL` issues a sign-in link; `python -m ergplan.intake.iex_loader FILE…` loads prices from disk.

Stage 8: `docker/compose.prod.yaml` over `docker/compose.yaml` on the VM (only Caddy exposed; automatic TLS for `SITE_ADDRESS`; `ERGPLAN_ENV=prod`; worker concurrency); `tools/dev/backup.sh` nightly (pg_dump + data/ tarball, 14 days, optional bucket); `docs/deploy.md` is the runbook.


`docker/compose.yaml`: postgres, api (migrates then serves), web (Next standalone), billx (built from `BILLX_REPO`, default a sibling `billx` checkout), docling (docling-serve CPU, billx's `docling` reader; billx reaches it at `http://docling:5001`), caddy (`:8080`, `/api/*` → api). The images build from the repository root with `.dockerignore`; the whole stack was first built and run in Docker on 1 Nov 2026.

## Rulebooks seeded (Stages 1 and 8)

| Jurisdiction | Families | Source | Golden tests |
| --- | --- | --- | --- |
| `npcl` | tariff_schedule (HV-2 urban, 4 voltage bands), tod_slots (summer, winter), oa_charge (wheeling 1.03, CSS by band, AS 0) | UPERC NPCL FY 2026-27 order pp. 315–388 | 26 |
| `uppcl` (PVVNL, MVVNL, PuVVNL, DVVNL, KESCO) | tariff_schedule, tod_slots, oa_charge (wheeling 0.9318, OA distribution losses, CSS) | UPERC State DISCOMs FY 2026-27 order pp. 379–446 | 24 |
| `UP` | oa_charge (intra-state transmission 0.3075/kWh, ISTS loss 1.56%, STU loss 3.18%), settlement (captive banking, CRE Regulations 2024) | UPERC State DISCOMs order pp. 377, 384; CRE Regulations 2024 pp. 14–20 (OCR) | 16 |
| `msedcl` | tariff_schedule (HT I(A), HT II; EHV and HT), tod_slots, oa_charge (CSS 2.11), settlement (monthly ToD-slot banking) | MERC Case 75/2025 post-remand order of 25 Mar 2026, pp. 77–106 | 25 |
| `ka_escoms` (BESCOM, MESCOM, CESC, HESCOM, GESCOM) | tariff_schedule (HT-2(a)), tod_slots | KERC FY 2026-27 order | 12 |
| `tg_discoms` (TGSPDCL, TGNPDCL) | tariff_schedule (HT-I(A), kVAh by voltage), tod_slots | TGERC FY 2026-27 order p. 281 | 11 |
| `tgspdcl`, `tgnpdcl` | oa_charge (CSS HT-I(A) by voltage; aggregate T&D charge Rs/kWh by voltage) | TGERC FY 2026-27 order pp. 152–154 | 15 |
| `pspcl` | tariff_schedule (LS general industry, two CD bands, 80 % floor) | PSERC FY 2026-27 order pp. 225–226 | 7 |
| `pspcl` | oa_charge (wheeling per MW and NRSE 2 % in kind, T&D losses by voltage, CSS Large Supply) | PSERC FY 2026-27 order pp. 238–239 | 8 |
| `ka_escoms`; `bescom`, `mescom`, `cesc`, `hescom`, `gescom` | oa_charge (CSS HT-2(a) common, additional surcharge not levied; per ESCOM HT wheeling and HT loss) | KERC Tariff Order 2025 pp. 249–250, 260, 266 | 25 |

| `gj_discoms` (DGVCL, MGVCL, PGVCL, UGVCL) | tariff_schedule (HTP-I: demand slabs, excess over contract, energy by billing demand, HV/EHV rebate), tod_slots (peak adder by billing demand, day concession) | GERC tariff schedule from 1 Apr 2026 (MGVCL order pp. 159, 173–175) | 18 |
| `ap_discoms` (APSPDCL, APCPDCL, APEPDCL) | tariff_schedule (HT-III(A) Industry (General), kVAh, by voltage, 80 % floor), tod_slots (high/low grid demand seasons) | APERC FY 2026-27 order Table 11 p. 197, p. 232 | 12 |

RJ, HR and TN are registered jurisdictions with no approved rules ("not yet sourced"; see `docs/known-gaps.md`).

## What changed

- **Stage 8**: sign-in by email link and access control (`platform/auth.py`, `platform/mail.py`, `routers/auth.py`; tables `users`, `login_tokens`, `auth_sessions`, `bills.uploaded_by`, migration 0009); bills read once per file but owned per uploader; security headers; `/login` and `/login/verify` pages and a signed-in bar; server pages forward the session cookie; approved-rule cache in `rulebook.repository` (cleared when the approved set changes); worker `--concurrency`; `tools/dev/secrets-check.py` in the watcher and CI; `docker/compose.prod.yaml`, Caddy TLS by `SITE_ADDRESS`, `tools/dev/backup.sh`, `docs/deploy.md`. Breadth: Karnataka, Telangana and Punjab rulebooks approved with golden tests (`packages/rulebooks/golden/{ka,ts,pb}`, `states/{ka,ts,pb}`), jurisdictions and DISCOM aliases for 18 more DISCOMs, `seed/stage8-jobs.yaml` (seed script takes a jobs file), `GET /rulebooks/coverage` and the coverage table on `/rulebooks`, "not yet sourced" notes on the options board and the live plan. `docs/release-notes/` (new folder; the 1.0 release note). Plan page response time checked in the suite (cached plan under 1 s).
- **Stage 7**: `report/` (plan, share, whatif, pdf, explain), `voice/tools.py`, providers `realtime_secret` and `chat_with_tools` with prompts `voice_v1` and `explain_v1`; tables `share_links`, `explanations` (migration 0008); routers `plan` and `voice`; settings `ergplan_web_internal_url`; Playwright (Python) for PDF export (also in the API image); journey step 6, `/p/[token]`, voice on intake, the rail carries the site; `tools/dev/billx_stub.py` and `tools/dev/e2e-journey.sh` (isolated browser end-to-end on real bills); `next.config` `distDir` from `NEXT_DIST_DIR`.
- **Stage 6**: `optimizer/` (model, highs_solve, resettle, scenarios); `platform/runs.py` and `platform/worker.py`; tables `scenarios`, `runs`, `run_results` with audit triggers on `scenarios` and `runs` (migration 0007, `db/sql/0007_runs_audit.sql`); `rulebook.repository.Reader` and `pinned_rules` (replay); `units` gains years, tCO2, tCO2/MWh; settings `ergplan_optimizer_time_limit_s`, `ergplan_optimizer_mip_gap`; compose service `worker`; pytest marker `slow` (15-minute site solves, run by CI's site step); journey step 5.
- **Stage 5**: `settlement/simulate.py`; hand-worked settlement cases in `apps/api/tests/settlement/cases/` mirrored in `packages/rulebooks/golden/<state>/settlement-cases.yaml`; normative generation curves `packages/profiles/cuf/` and `intake/generation.py`; landed-cost waterfall exposes the delivered share after losses; `POST /connections/{id}/settle`; analyst settlement explorer.

- **Stage 4**: `engine/landed_cost.py`, `engine/lcoe.py`, `engine/lcos.py`; `/connections/{id}/landed-cost`, `/rulebooks/limits`, `/prices/vintages/{id}`; `SourceRef` kind `market` (IEX prices cite their vintage); journey step 3; rulebook corrections through the gate: UP `oa_charge` v2 (ISTS loss only for inter-state), NPCL v4 and UPPCL v3 (wheeling, losses, CSS, AS apply to inter-state OA consumers too; captive and group-captive CSS exemption from CRE Regulations 2024 Reg. 11.II, p. 13); draft six-consumer spreadsheets `tests/fixtures/landed_cost_up.csv`, `landed_cost_mh.csv` (awaiting jouleWise approval).

- **Stage 3**: engine (scope, tariff evaluator, bill replay, avoided cost, named gaps); `/connections/{id}/replay` and `/avoided-cost`; journey step 2; `SourceRef.url` serialised on every ref (and ignored on input); UP `rate_block` default (urban, assumed); MSEDCL `tod_slots` v3 (peak +25% for HT industrial and commercial, MYT order p. 565), NPCL and UPPCL `tariff_schedule` v2 (billable demand ≥ 75% of contract, excess at 200%, general provisions pp. 354–355 and 410–411); fifteen real bills read through billx and cached under `data/bills/billx-results/` (gitignored) for the replay test.

- **Stage 2**: migration 0006 (clients, sites, connections, bills, bill_confirmations, assets, load_profiles, price_vintages, price_series); `SourceRef` kind `bill` (bill id and billx path, opens the stored bill at its page); intake package (billx client, bill review and confirmations, SiteIntake with sourced defaults, profile synthesis from eight shapes, meter upload, IEX loader); intake and prices API; journey steps 1 and 4 and the analyst prices page; billx contract fixtures in `apps/api/tests/fixtures/billx/` (synthetic, copied from billx `contract/examples`); real-bill end-to-end (NPCL and MSEDCL) through the running billx.

- **Stage 1**: migration 0002 (rulebook tables, audit/frozen/approval triggers, `rules_approved` view); rulebook package; regulation reader (direct with grounding, tariff-oder import); OpenAI provider with versioned prompts; OCR fallback; document ids derived from SHA-256; rulebook and reader API; analyst UI; 12 approved rulebooks for UP and Maharashtra with 91 golden tests; committed rulebooks round-trip test.
- **Stage 0**: skeleton, `SourcedValue`, documents store and corpus loader (5 real orders registered: UPERC NPCL and state DISCOMs FY 2026-27, MERC MSEDCL MYT and two Case 75/2025 orders), Harmony shell, documents library and page viewer, compose, watcher, CI, reviewer.

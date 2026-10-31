# ergPLAN — Master Prompt

Version 1.0 · 31 Oct 2026 · jouleWise | ergPLAN · repository `Ergplan/Enterprise-RE-Planner`

ergPLAN tells an industrial consumer, from its electricity bills alone, what each unit of power costs it today and what the cheapest green replacement costs delivered to its meter — in its state, under its DISCOM's tariff and its state's open-access and banking rules — and then sizes the mix (rooftop, BTM BESS, open-access solar, wind, BESS, pumped storage, IEX purchase) that replaces grid and thermal power at the lowest annual cost. Every number a client sees carries the regulation, page and a link that opens the actual PDF at that page.

The approved development plan this prompt implements: https://claude.ai/artifact/NLparJwTT1PM2CmNYA7BFi (a copy is `docs/development-plan.md`).

---

## 1. How to use this prompt

- This file is committed once. Sections 2 to 5 are copied verbatim into `CLAUDE.md`, which Claude Code reads in every session.
- Each stage is one Claude Code session on the build machine, inside `tmux`. The person types one line: `Run Stage N of docs/MASTER-PROMPT.md`. The agent reads the stage prompt from this file, works, and stops at the stage boundary with a stage report.
- Nothing is pasted twice. Questions the agent has are written into the stage report, numbered; the person answers them numbered in one message at the start of the next session.
- The person reads each report and spot-checks one invariant by hand (a grep, a curl, a click) before starting the next stage.

---

## 2. Operating rules

1. Work stage by stage. Never start the next stage's work early. If a stage needs something from a later stage, write a stub that raises `NotImplementedError` with the stage number and note it in the report.
2. Every stage ends with: watcher green, the app running under `docker compose up`, the reviewer's findings fixed, a stage report in `docs/stage-reports/stage-N.md`, a commit tagged `stage-N-done`, and a STOP.
3. Tag the commit at each stage start (`stage-N-start`) so the stage diff is well defined.
4. Write tests with the code, not after. Kinds: unit for every rule evaluation, settlement transition and formula; integration for every API endpoint; one end-to-end per stage on real input (a real bill, a real tariff order page, a real IEX CSV). Golden tests for every rulebook version.
5. Read `tools/watch/status.json` before every commit. Never commit over a red check. Never skip, delete or mark a test expected-failure to get green. If a test is wrong, fix the test and say so in the commit message.
6. Small commits after each working increment, in imperative mood, each naming the stage: `stage 3: tariff evaluator handles kVAh billing`.
7. Reference repositories are read-only inputs. `Ergplan/designsystem` (ergOS Harmony) is consumed as a package; `Ergplan/tariff-oder` and `Ergplan/FDRE` (tariff-order and tender readers) and the billx repository may be read for patterns and copied with the origin in a comment, never imported at runtime. billx runs as a container and is spoken to over HTTP only.
8. One language per layer: TypeScript in `apps/web`, Python in `apps/api`. No framework hopping mid-build. No second ORM, no second HTTP client, no second state library.
9. Every external model call goes through `apps/api/ergplan/providers/` — the only package that imports a model SDK (a test enforces this). Typed input and output, a versioned prompt loaded from `apps/api/ergplan/providers/prompts/<name>_v<n>.md` (never edited in place; a change is a new version), bounded retries, and one log row per call in `model_calls` with tokens and cost. No model call in `engine/`, `settlement/`, `optimizer/` or `rulebook/` (a test enforces this too).
10. Keep the folder layout of section 5 exactly. A new folder is added to `docs/architecture.md` in the same commit that creates it. No `utils/`, `helpers/`, `misc/`, `temp/`, `old/`, `v2/`.
11. Secrets by environment variable only, read in `ergplan/core/settings.py`, with a committed `.env.example`. Never a key in code, a test, a log or a report.
12. Security is deferred until Stage 8: simple email + magic-link login, two roles (`analyst`, `client`), share links by unguessable token. No OAuth, no RBAC matrix, no rate limiting before Stage 8. Do not add them early; do not forget them at Stage 8.
13. The quality that wins ties: **regulatory traceability beats speed**. A number without a `source_ref` does not reach a client screen, even if that means the screen says "not yet sourced".
14. Living documents (`docs/architecture.md`, `docs/decisions.md`, `docs/known-gaps.md`, `docs/field-trace.md`) are updated in the same commit as the code that changes them.
15. Money and energy are `Decimal` in Python and strings over the wire. Never a float in a stored or returned value. Rates are stored with the unit the regulation uses (`INR/kWh`, `INR/kVA/month`, `INR/MW/month`, `percent`) and converted by one function in `ergplan/core/units.py`.
16. Independent review. Before each stage report, from Stage 0 onward, run `tools/review/run.sh` — a reviewer on a model from a different family than the builder, in a fresh context with no access to this session. It receives only three things: the stage diff (`git diff stage-N-start..HEAD`), `CLAUDE.md`, and the stage prompt. It answers a fixed checklist and nothing else: (a) every invariant upheld, citing file and line, or the violation; (b) every endpoint added has a test; (c) every write to `rules`, `rulebook_versions`, `runs` is audited; (d) generated documents regenerate without diff; (e) any claim in the draft stage report that the code does not support. Fix every finding and rerun the reviewer until it reports no new code defect. Findings that cannot be resolved by code (by-design behaviour, statements a diff cannot prove, decisions pending from the person) are listed in the report with a one-line rationale and do not block the stage.
17. The stage report states: what was built; what was skipped and why; deviations from this prompt; reviewer findings and their fixes; open questions, numbered; real model cost for the stage (builder and reviewer, from `model_calls` and the Claude Code session).
18. When a definition-of-done check is not met, fix the system, not the check. Correct abstention ("the regulation does not state this") is never scored as a failure.

---

## 3. Invariants

These hold in every stage and override anything else in this document. If a stage prompt conflicts with an invariant, the invariant wins and the agent flags the conflict in the report.

1. **Every value a client sees carries a `source_ref`.** Any number returned by a client-facing endpoint (landed cost line, avoided cost line, settlement quantity, regulatory limit, tariff rate) is a `SourcedValue {value, unit, source_ref}`, and `source_ref` names `document_id`, `page`, `quote` and resolves to `/documents/{document_id}#page={page}`, which opens the stored PDF at that page. Pydantic rejects a `SourcedValue` without a `source_ref`; a derived number carries the `source_ref`s of every input it was derived from. Values the client typed or ergPLAN assumed carry a `source_ref` of kind `client_stated` or `assumption` and render as editable chips, never as sourced facts.
2. **Only approved rulebook versions reach a client.** `engine/`, `settlement/` and `optimizer/` load rules through `rulebook.repository.approved_rules()` which reads the database view `rules_approved` (`status = 'approved'` and effective on the evaluation date). Draft versions are evaluated only by `rulebook.sandbox`, used only by analyst endpoints. A test creates a draft rule with an absurd value and asserts no client endpoint's output changes.
3. **Single writer for rules.** `rules` and `rulebook_versions` are written only by `rulebook.service` (`propose`, `revise`, `approve`, `supersede`). A database trigger appends every change to `audit_log` (who, when, before, after) and rejects any write where the session variable `ergplan.actor` is unset. Approval requires an actor with role `analyst` and all golden tests for that jurisdiction green; the trigger rejects an approval with failing tests recorded.
4. **No model decides a number.** `engine/`, `settlement/`, `optimizer/` and `rulebook/` import nothing from `providers/` (a test walks the import graph). The LLM proposes rule rows from PDFs, drafts explanations and runs the voice; a person approves rules and the engines compute.
5. **Runs are reproducible.** Every `run` pins the `rulebook_version_id` of every rule it used, the `price_vintage_id`, the `load_profile_version_id` and the solver version; `POST /runs/{id}/replay` recomputes it and the test asserts identical results to the paisa.
6. **The optimizer never has the last word.** Every optimizer result is re-settled by `settlement.simulate()` on the solver's dispatch; a disagreement above `settings.resettle_tolerance_kwh` marks the run `failed_resettle` and the client never sees it.
7. **billx is the only bill reader.** ergPLAN stores billx's result (`bills.billx_result` JSONB, with every field's `proof` and `verification`) and uses only bills with `accepted: true` or a client's explicit per-field confirmation recorded in `bill_confirmations`. ergPLAN never runs OCR or a model on a bill.
8. **Provenance on every input.** `load_profiles.provenance` is `measured`, `synthesised` or `stated`; `price_series.vintage_id` names the uploaded CSV and its sha256; every client-facing result shows the provenance of its load profile and prices.

---

## 4. Locked decisions

Not reopened unless analysis of the codebase shows something materially better, and then only with a dated entry in `docs/decisions.md`.

| Area | Decision | Why |
| --- | --- | --- |
| Repository | `Ergplan/Enterprise-RE-Planner`, single repo, layout of section 5 | One prompt, one CLAUDE.md, one watcher |
| Frontend | Next.js 15 (App Router) + TypeScript + ergOS Harmony from `Ergplan/designsystem` (tokens, `eg-` kit, `window.ErgOS`, jouleWise logo) | Same look as ergOS and esgOS |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, `Decimal` money | Engines are Python; billx and TenderOS are too |
| Optimizer | Pyomo model solved by HiGHS (`highspy`) | Open source, fast MILP, proven in TenderOS |
| Database | PostgreSQL 16; rules as JSONB validated against JSON Schema files in `packages/rulebooks/schemas/`; audit by trigger | Rules editable without a code change; versions and provenance built in |
| Rule authoring | Form editor in the analyst UI + YAML import/export of a whole jurisdiction; the regulation reader proposes drafts from PDFs with page citations | Analysts work in forms or files; the LLM never approves |
| Bill reading | billx container (its `docker/engine.Dockerfile`, image tag pinned in compose), API mode `esgos-1.1`, `wait: true` | Already built; ergPLAN is its second consumer |
| Voice | OpenAI Realtime API (WebRTC from the browser with an ephemeral token minted by the API); the voice calls typed tools that fill `SiteIntake` or run a what-if | Voice is a mouth, not a mind |
| Model provider for the app | OpenAI only (regulation reader, explanations, voice, reviewer), keys in `.env`. No Anthropic API key is used; Claude is the builder on the subscription only | Decision of 31 Oct 2026 |
| Tariff-order extraction | `Ergplan/tariff-oder` is the upstream pipeline for tariff orders (retail schedule, wheeling, OA loss, CSS, additional surcharge, banking, green tariff). `regreader/tariff_oder.py` imports its published facts (API `/explorer/sources/{id}/tariff` and `/network`, or its `export.zip`) and maps them to draft rule rows; its evidence (PDF page, printed page, excerpt) becomes the `source_ref`. Documents are matched by SHA-256 | Reviewed extraction already exists; ergPLAN does not rebuild it |
| Regulation reading (fallback) | `regreader/direct.py` reads pages tariff-oder does not cover (OA and banking regulations, GEOA rules, CERC sharing and waiver orders) with an OpenAI model through `providers/`, prompt-versioned; every proposed row's `quote` must be found verbatim (whitespace-normalised) in that page's text layer or the row is rejected (grounding check). Page ranges come from `packages/rulebooks/corpus/tariff-library.json` | Reviewed by a person; never approves |
| Document corpus | The regulation PDFs on the Mac mini (`~/Downloads/India_DISCOM_Tariff_Orders_Final_2026`, `~/Downloads/Tariff Orders`, `Banking Rule - Uttar Pradesh.pdf`) are registered into `source_documents` with their regulator URL (`url_public`) from the library index; the app stores and serves the PDF itself | The client sees both the stored page and the regulator's link |
| Prices | IEX CSVs uploaded by an analyst in the app; parsed by `intake/iex_loader.py` into `price_series` with a `vintage` | jouleWise has the CSVs |
| Load profiles | Synthesised from 12 bills using `packages/profiles/` shapes, exactly matching monthly kWh, ToD split and recorded MD; measured 15-minute upload when it exists | Most clients have only bills |
| Reports | Live shareable plan link `/p/{token}` with voice what-if; jouleWise analyst view toggle; PDF export via headless Chromium of the same page | One page, three audiences |
| Deployment | Docker Compose: `web`, `api`, `worker`, `postgres`, `billx`, `caddy`; laptop until Stage 5, then a Google Cloud VM in `asia-south2` | Same shape as houseoframa |
| Access (until Stage 8) | Email magic link; roles `analyst` and `client`; share links by token | Speed now, security at launch |
| Builder and reviewer | Claude Code builds (subscription); `tools/review/run.sh` reviews with an OpenAI model (`REVIEWER_MODEL`) | Different families, different blind spots |
| Test data | Synthetic bills from billx's `contract/examples`; two real anonymised bills per DISCOM supplied by the person into `data/bills/` (gitignored) | Real layouts without real names in git |
| Tie-break | Regulatory traceability beats speed | Rule 13 |

---

## 5. Folder layout, continuous testing, living documents

### 5.1 Layout

```
Enterprise-RE-Planner/
  CLAUDE.md                      sections 2–5 of this file, verbatim
  README.md
  .env.example
  docker/
    compose.yaml                 web, api, worker, postgres, billx, caddy
    api.Dockerfile
    web.Dockerfile
    caddy/Caddyfile
  apps/
    web/                         Next.js 15, TypeScript, ergOS Harmony
      app/                       routes: /(client)/plan, /p/[token], /(analyst)/rulebooks, /documents
      components/                Harmony-based components only; no second UI kit
      lib/                       typed API client generated from openapi.json
      tests/                     vitest + playwright
    api/
      pyproject.toml
      alembic/                   migrations, one per stage increment
      ergplan/
        core/                    settings.py, units.py, money.py, sourced.py (SourcedValue, SourceRef), ids.py
        db/                      engine, session, models (SQLAlchemy), views, triggers (SQL files)
        documents/               source PDFs: storage, sha256, page serving at /documents/{id}#page=N
        rulebook/                schemas loader, models, repository (approved_rules), service (propose/approve), sandbox, yaml_io, golden
        regreader/               tariff_oder.py (import published facts), direct.py (OpenAI reader + grounding check) → draft rule rows
        providers/               THE ONLY package importing model SDKs; prompts/ versioned; model_calls log
        intake/                  billx_client, site_intake, profile_synthesis, iex_loader, measured_upload
        engine/                  tariff_eval (bill replay, avoided cost), landed_cost, waterfall, scope (applicability) — pure
        settlement/              simulate(): block/ToD/monthly netting, banking, lapse, set-off — pure
        optimizer/               pyomo_model, highs_solve, scenarios, resettle — pure
        voice/                   realtime token minting, tool schemas for intake and what-if
        report/                  plan page data, share tokens, pdf export
        platform/                FastAPI app, routers per area, auth (magic link), roles
      tests/                     mirrors ergplan/ one-for-one; tests/e2e/ for stage end-to-ends
  packages/
    rulebooks/
      schemas/                   JSON Schema per rule family + source_ref.schema.json (committed in this repo at Stage 0)
      states/<state>/<family>/<version>.yaml   exported approved rulebooks (regenerated by yaml_io; CI checks drift)
      golden/<state>/*.yaml      golden test cases per jurisdiction
      corpus/                    tariff-library.json: the regulation corpus index (path, regulator URL, schedule page ranges)
    profiles/
      shapes/                    industry load shapes (15-min, normalised) with provenance notes
      cuf/                       solar and wind hourly CUF curves by state and technology
  data/                          gitignored: bills/, documents/, iex/, postgres volume
  tools/
    watch/                       watcher: writes status.json and watch.log
    review/                      run.sh: independent reviewer (different model family)
    dev/                         seed, reset, make-bill-fixture
  docs/
    MASTER-PROMPT.md             this file
    development-plan.md          the approved plan
    architecture.md              living: components, data model, critical path, API surface, deployment, "what changed"
    decisions.md                 living: dated decisions log
    known-gaps.md                living
    field-trace.md               generated: every client-visible field → table.column → source_ref kind
    stage-reports/stage-N.md
```

### 5.2 Continuous testing

`tools/watch/` is a service started by `docker compose up` beside the app. On every save it runs, in order: `ruff` (lint + format check), `mypy --strict` on `ergplan/`, `pytest` for the changed package then the full suite (excluding `@pytest.mark.external`), `alembic check` for migration drift, `pnpm typecheck` and `vitest` in `apps/web`, the JSON Schema validation of every YAML under `packages/rulebooks/`, and the regeneration of `docs/field-trace.md` and `packages/rulebooks/states/` with a diff check. It writes `tools/watch/status.json` (`{"green": bool, "checks": {...}, "at": iso}`) and `tools/watch/watch.log`. The agent reads `status.json` before every commit. The same checks run in GitHub Actions on push. Tests that call billx, OpenAI or Anthropic are marked `external` and run only in the stage end-to-end.

### 5.3 Living documents

- `docs/architecture.md`: component diagram (text), data model table (every table, its writer, its audit), the critical path with real function names (bill → `intake.site_intake.build()` → `engine.tariff_eval.replay()` → `engine.landed_cost.evaluate()` → `settlement.simulate()` → `optimizer.solve()` → `optimizer.resettle()` → `report.plan.build()`), the API surface, deployment, and a "what changed in Stage N" list per stage.
- `docs/decisions.md`: dated entries; every deviation from this prompt is one.
- `docs/known-gaps.md`: what is not yet right, with the stage that fixes it.
- `docs/field-trace.md`: generated from Pydantic response models — every client-visible field, the table and column it comes from, and which `source_ref` kinds it may carry. CI fails on drift or on a field with no owner.

---

## 6. Plan

Ordered by what becomes permanent earliest.

| Stage | Name | Permanent things it creates | Machine |
| --- | --- | --- | --- |
| 0 | Skeleton | Layout, compose, Harmony wiring, watcher, CI, `SourcedValue`, documents store | Laptop |
| 1 | Rulebook and regulation reader | Rule tables, schemas, versioning, approval trigger, golden runner, YAML I/O, analyst editor, PDF → draft rows; UP and Maharashtra seeded | Laptop |
| 2 | Intake and site | billx client, `SiteIntake`, clients/sites/connections/assets, profile synthesis, IEX CSV upload | Laptop |
| 3 | Avoided cost | Tariff evaluator, bill replay, avoided-cost waterfall | Laptop |
| 4 | Landed cost | OA charge evaluator, scope engine, ISTS waiver, IEX segments, source cards | Laptop |
| 5 | Settlement simulator | Block/ToD/monthly netting, banking, lapse, set-off | VM |
| 6 | Optimizer | Pyomo + HiGHS, thermal unit commitment, scenarios, re-settlement | VM |
| 7 | Journey, voice, live plan | Six-step client journey, Realtime intake and what-if, `/p/{token}`, analyst view, PDF | VM |
| 8 | Breadth and launch | Eight states, login, performance, final test pass, deployment | VM |

---

## 7. Stage prompts

### Stage 0 — Skeleton

```
Run Stage 0: the skeleton. Build nothing of the domain except SourcedValue and the documents store.

Do:
- Create the layout of section 5.1 exactly. Empty packages get an __init__.py and a one-line docstring naming their stage.
- apps/api: FastAPI app with GET /health; settings.py reading .env; SQLAlchemy + Alembic with an initial migration creating `source_documents` (id, title, regulator, jurisdiction, document_kind, file_sha256, pages, effective_from, effective_to, url_public, uploaded_by, uploaded_at) and `model_calls` (id, provider, model, prompt_name, prompt_version, purpose, tokens_in, tokens_out, cost_inr, status, started_at, ended_at, ref_type, ref_id).
- ergplan/core/sourced.py: SourceRef {kind: regulation|order|client_stated|assumption|measured|derived, document_id?, page?, quote?, effective_from?, note?} and SourcedValue {value: Decimal, unit: str, source_refs: list[SourceRef] (min 1)}. Pydantic validation rejects an empty list. units.py with the unit enum and conversions (INR/kWh, INR/kVAh, INR/kVA/month, INR/kW/month, INR/MW/month, INR/MWh, percent, kWh, kVAh, kW, kVA, MW).
- ergplan/documents: upload a PDF (analyst only, later; no auth yet), store under data/documents/<sha256>.pdf, record a row, serve GET /documents/{id} with Content-Disposition inline so `#page=N` works in browsers, and GET /documents/{id}/pages/{n}.png rendered by pypdfium2 for thumbnails.
- apps/web: Next.js 15 + TypeScript; install ergOS Harmony from Ergplan/designsystem as a package (or vendor its tokens and eg- kit under apps/web/components/harmony with origin noted); a shell with the jouleWise | ergPLAN header, a left rail with the six journey steps (disabled), a /documents page listing stored PDFs and opening one at a page. Dark and light from Harmony tokens.
- docker/compose.yaml: web, api, postgres (16), billx (image built from the billx repo's docker/engine.Dockerfile, env BILLX_API_MODE=esgos-1.1, BILLX_TOKEN from .env), caddy; healthchecks on each.
- tools/watch per 5.2, writing status.json; GitHub Actions workflow running the same.
- tools/review/run.sh: takes the stage number, builds the three inputs, calls the OpenAI model named in .env (REVIEWER_MODEL), writes docs/stage-reports/stage-N-review.md, exits non-zero if any finding is a code defect.
- docs/architecture.md, decisions.md, known-gaps.md created with real content; field-trace generator producing an empty table.
- Tests: unit for SourcedValue (rejects empty source_refs, Decimal only), units conversions, documents sha256 dedupe; integration for /health and /documents; one e2e: `docker compose up`, upload a PDF, open it at page 3 in the web shell.

Done when: `docker compose up` serves the Harmony shell at :3000 and the API at :8000; billx /v1/health answers through the compose network; the watcher is green; the reviewer reports no new code defect; docs/stage-reports/stage-0.md is written. STOP.
```

### Stage 1 — Rulebook and regulation reader

```
Run Stage 1: the rulebook. This is the most permanent stage; take the data model slowly and get the approval path right. Do not build intake, engines or UI journey.

Data model (Alembic migration):
- jurisdictions (id, kind: state|regulator|discom|stu, name, state_code, parent_id). Seed CERC, all states, and the DISCOMs billx knows by billx profile id (pvvnl, mvvnl, dvvnl, npcl, msedcl, tgspdcl, apcpdcl, gescom, tangedco, avvnl, pspcl) plus BESCOM, MESCOM, CESC, HESCOM, MGVCL, UGVCL, DGVCL, PGVCL, JVVNL, JdVVNL, DHBVN, UHBVN.
- rulebook_versions (id, family, jurisdiction_id, version, status: draft|approved|superseded, effective_from, effective_to, created_by, created_at, approved_by, approved_at, golden_status, notes).
- rules (id, rulebook_version_id, family, scope JSONB, body JSONB, source_ref JSONB, position). GIN index on scope. CHECK that body validates against the family schema is done in the service (Postgres has no JSON Schema), and a trigger rejects a rules write without ergplan.actor.
- rule_tests (id, jurisdiction_id, family, name, given JSONB, expect JSONB, source_ref JSONB) and rule_test_runs (id, rulebook_version_id, test_id, passed, actual JSONB, ran_at).
- audit_log (id, table_name, row_id, action, actor, at, before JSONB, after JSONB) written by trigger on rules, rulebook_versions, rule_tests.
- View rules_approved: rules joined to approved versions, effective on current_date unless an evaluation date is passed by the repository.

Families and schemas: load the seven JSON Schemas committed at packages/rulebooks/schemas/ (settlement, tariff_schedule, oa_charge, regulatory_limit, ists_waiver, net_metering, tod_slots) plus source_ref.schema.json. Do not change a schema without a decisions.md entry; the schemas are reference data (section 8).

Service: rulebook.service with propose(family, jurisdiction, rows, actor) → draft version; revise(version, rows, actor); run_golden(version) → records rule_test_runs and sets golden_status; approve(version, actor) → requires role analyst and golden_status green, supersedes the previous approved version for the same family+jurisdiction+overlapping effective dates; supersede(version, actor). repository.approved_rules(family, jurisdiction, on_date, scope_filter) and sandbox.rules(version_id, ...).

YAML I/O: export a jurisdiction's approved rulebooks to packages/rulebooks/states/<state>/<family>/<version>.yaml (deterministic ordering); import a YAML as a draft. The watcher regenerates the export and fails on drift.

Regulation reader (regreader/), two doors into the same draft rows:
- tariff_oder.py: import a published release from Ergplan/tariff-oder (TARIFF_ODER_URL + token, or an export.zip / exchange folder) and map its families to ergPLAN families — retail_tariff → tariff_schedule (+ tod_slots from tod_adjustment rows with a time_band), wheeling_charge/oa_loss/cross_subsidy_surcharge/additional_surcharge/green_tariff → oa_charge, banking_rule → settlement (banking fields), transmission_reference → oa_charge (stu_transmission). Evidence pdf_page, printed_page and excerpt become source_ref page and quote; the document is matched by SHA-256 (registered here if missing). Unmappable facts are listed, not dropped silently. Tested against fixtures shaped exactly as packages/contracts/openapi.json of tariff-oder.
- direct.py: for documents tariff-oder does not cover, render the page range the analyst picks (default from packages/rulebooks/corpus/tariff-library.json), call the OpenAI model through providers/ with prompt regreader_<family>_v1 returning candidate rows each with page and a verbatim quote; reject any row whose quote is not found in that page's text layer (whitespace- and case-normalised); validate against the schema; write a draft version.
Both show each row beside the page image with the quote highlighted for the analyst to accept, edit or reject. Neither approves.

Analyst UI (apps/web/(analyst)/rulebooks): jurisdictions → families → versions; a version page with the rows as a form generated from the schema (every field labelled with its schema description and unit), the source document opened at the cited page beside it, golden test results, and Approve. Harmony components only.

Seed two states from their real orders, registered from the corpus (data/corpus, copied from the Mac mini's Downloads): Uttar Pradesh (UPERC NPCL FY 2026-27 order, schedule PDF pages 352-400; UPERC state DISCOMs FY 2026-27 order, schedule pages 408-458; Banking Rule - Uttar Pradesh) and Maharashtra (MERC MSEDCL MYT order Case 217/2024 and Case 75/2025 orders). Every seeded row cites a page. Where the person has not supplied a document, leave the family empty and list it in known-gaps rather than inventing a value. Write at least five golden tests per state per family that has rows.

Tests: unit for every service transition (draft→approved requires green golden; approve supersedes; write without actor rejected by trigger; draft invisible through rules_approved; schema violation rejected); integration for every endpoint; e2e: upload the NPCL order, run the reader on the retail schedule pages, accept rows, run golden, approve, see the YAML export appear.

Done when: both states have approved tariff_schedule, tod_slots and oa_charge versions with page citations; the invariant-2 test (absurd draft invisible to approved_rules) passes; YAML export regenerates without diff; reviewer reports no new code defect; stage report with the list of regulation documents still needed. STOP.
```

### Stage 2 — Intake and site

```
Run Stage 2: intake. Everything the engines will later read about a client. No cost calculation yet.

Data model: clients (id, name, gstin?, created_by), sites (id, client_id, name, state, address, industry_shape_id, shifts, land_acres?, roof_sqm?), connections (id, site_id, discom_id, consumer_number, tariff_category, voltage_kv, contract_demand_kva, connection_kind: ht|eht|lt), bills (id, connection_id, billx_job_id, bill_month, accepted, accepted_by, billx_result JSONB, created_at), bill_confirmations (id, bill_id, path, value, confirmed_by, at), assets (id, site_id, kind: rooftop_pv|captive_thermal|waste_heat|bess|dg, params JSONB validated per kind: for captive_thermal fuel, gcv, heat_rate_kcal_per_kwh, capacity_mw, technical_minimum_pct, ramp_up_mw_per_block, ramp_down_mw_per_block, min_up_blocks, min_down_blocks, variable_cost_inr_per_kwh or fuel_price, aux_consumption_pct, must_run: bool), load_profiles (id, connection_id, version, provenance: measured|synthesised|stated, resolution_min: 15, year_start, series stored as a compressed array of 35,040 Decimals in kW, method JSONB, created_at), price_vintages (id, segment, file_sha256, filename, uploaded_by, rows, date_from, date_to), price_series (vintage_id, ts, block, segment, mcp_inr_per_mwh, volume_mw?).

billx client (intake/billx_client.py): POST /v1/jobs multipart with options {contract:"1.1", wait:true, account_ref:<connection id>}; poll GET /v1/jobs/{id} when 202; store the result; accepted = result.accepted; for needs_review bills return the review_reasons and the disputed field objects so the client UI can ask for one-click confirmations, recorded in bill_confirmations. Map billx profile id → discom jurisdiction. Fields consumed (by contract path): utility.name, tariff.category, connection.tariff_category, demand.contract_kva, demand.max_kva, energy.kwh, energy.kvah, energy.billed_units, energy.tod[], energy.power_factor, charges.energy, charges.demand, charges.by_code[], open_access.re_kwh, open_access.non_re_kwh, open_access.banked_kwh, net_metering.import_kwh, net_metering.export_kwh, green_tariff.kwh, totals.current_charges, totals.net_payable, totals.due_date_rebate, period.*. Voltage is not on most bills: ask the client, with the category's usual voltage as the default chip.

SiteIntake (intake/site_intake.py): one Pydantic model filled by any door — bills, typed form, voice tools (Stage 7 reuses these tool schemas). Fields: state, discom, voltage_kv, category, contract_demand_kva, monthly {kwh|kvah, tod split, max_kva, pf, bill_inr} for 1–12 months, shifts, industry_shape, existing assets. Every field has a provenance (bill|client_stated|assumption) and ergPLAN's normative defaults are applied by intake/defaults.py which records each assumption as a SourceRef of kind assumption. Back-solving units from a bill amount uses the approved tariff schedule (Stage 3 completes this; stub now).

Profile synthesis (intake/profile_synthesis.py): packages/profiles/shapes/<id>.yaml holds a normalised weekly 15-minute shape (672 values) per industry type with notes on its origin; synthesise a year by (a) scaling each month's shape to the bill's kWh, (b) reshaping within ToD windows so the ToD split equals the bill's to 0.1 %, (c) scaling peaks so the month's maximum equals the recorded MD in kVA × PF, (d) honouring weekly offs and declared shutdowns. Provide eight shapes to start: continuous_process, two_shift, single_shift, cold_storage, textile_spinning, steel_induction, pharma_formulation, food_processing. Record method JSONB. Measured upload: CSV of 15-minute kW or kWh with timestamp, validated for gaps.

IEX loader (intake/iex_loader.py): analyst uploads an IEX CSV (DAM, RTM, GDAM, G-TAM, TAM, HP-DAM market snapshot formats); detect the format by header, parse 15-minute blocks, reject overlaps with an existing vintage unless replace is chosen, store price_series with vintage. Show a coverage calendar per segment in the analyst UI.

UI: client journey step 1 (Drop a bill / Tell me about your site / Type the facts) and step 4 (Describe the site: shifts, shape, assets) in Harmony; analyst pages for price uploads. The journey steps 2, 3, 5, 6 remain disabled.

Tests: unit for every SiteIntake validation and default, profile synthesis properties (monthly kWh exact, ToD split within 0.1 %, max equals MD), IEX parser on one real file per segment supplied by the person into data/iex/; integration for every endpoint; e2e: a real PVVNL or NPCL bill (data/bills/) dropped end to end becomes a connection with twelve-month data and a synthesised profile.

Done when: the e2e passes on two real bills from different DISCOMs; a needs_review bill round-trips through confirmation; six IEX CSVs are loaded with vintages; reviewer clean. STOP.
```

### Stage 3 — Avoided cost

```
Run Stage 3: the tariff evaluator and the bill replay. Pure functions in engine/; no model calls, no network.

engine/scope.py: given a rule's scope JSONB and an evaluation context (jurisdiction, connection kind, voltage band, category, source, ownership, capacity, date), return whether the rule applies. Scope grammar is in source_ref.schema.json's sibling scope definition inside each family schema. Unit-test every operator.

engine/tariff_eval.py: evaluate an approved tariff_schedule + tod_slots for a connection and a month's quantities (kWh or kVAh by ToD slot, max kVA, PF, days) → a list of SourcedValue lines: fixed/demand charge (on billing demand = max(recorded, X % of contract) as the schedule states), energy charge per slot, ToD surcharge/rebate per slot, FPPCA/fuel surcharge, electricity duty, PF incentive/penalty, load factor incentive, minimum charges, excess demand penalty, prompt payment rebate, taxes; and totals. Every line carries the rule row's source_ref. kVAh billing is handled as the schedule states.

Bill replay (engine/replay.py): for each accepted bill, evaluate the schedule on the bill's own quantities and compare line by line with billx's charges.by_code[] and totals; produce a ReplayReport {lines: [{code, billed, computed, difference, explanation}], total_difference, status: match|explained|unexplained}. A difference is "explained" only if a named rule gap in known-gaps.md or a billx flag covers it.

Avoided cost (engine/avoided_cost.py): for each 15-minute block of the load profile, the marginal avoided cost of one kWh of grid energy in that block: energy charge of the slot + ToD adjustment + FPPCA + duty + taxes on energy (+ kVAh factor when billed in kVAh), as SourcedValue; and the fixed-side terms as separate annual SourcedValues: demand charges at current contract demand, LF incentive at current grid units, PF effect, rebates. Return a Waterfall {blocks: 35,040 values, annual: lines}.

API: GET /connections/{id}/replay, GET /connections/{id}/avoided-cost. UI: journey step 2 "See today's cost" — the rebuilt bill beside the real one, differences highlighted, every line with its citation on hover and a link that opens the PDF at the page; a 15-minute avoided-cost heatmap (month × time of day).

Tests: unit per line type with hand-computed expectations from the UPERC and MERC schedules; replay of ten accepted bills (synthetic + real) within ₹1 per line or explained; integration; e2e from bill drop to step 2 screen.

Done when: replay status is match or explained on all ten bills, with the unexplained list empty or filed in known-gaps with the rule gap named; every line on the step-2 screen opens its PDF page; reviewer clean. STOP.
```

### Stage 4 — Landed cost

```
Run Stage 4: landed cost for every source. Pure functions in engine/; the IEX price series and the oa_charge, ists_waiver, regulatory_limit, net_metering rulebooks are the inputs.

engine/landed_cost.py: evaluate(source, connection, block_or_slot, scenario_params) → Waterfall of SourcedValue lines, in this order and with these semantics:
1. generation price P: PPA tariff (scenario input, source client_stated/assumption), or IEX MCP for the segment and block from price_series (+ exchange fee + trader margin rows from oa_charge), or LCOE for rooftop/BTM BESS computed by engine/lcoe.py (capex, O&M, degradation, life, discount rate; CRF), or thermal variable cost from assets.
2. loss gross-up: P and per-kWh transmission/wheeling charges divided by Π(1 − loss_i) for every loss stage the power crosses (ISTS, STU, wheeling) as scope decides.
3. capacity charges (INR/MW/month: ISTS, STU, SLDC) divided by the month's scheduled energy for that source (from the source's CUF profile × capacity; the optimizer later supplies actual).
4. per-kWh charges at the drawal point: wheeling (INR/kWh), CSS, additional surcharge, electricity duty on OA, DSM pass-through, standby/grid support, banking charge on banked units only (settlement decides the banked quantity; Stage 4 reports it on the full injected quantity as an upper bound and labels it so).
5. ISTS waiver: apply the ists_waiver rows by the source's commissioning date (scenario input) to ISTS charges and losses.
6. exemptions by scope: captive (≥ 26 % equity, ≥ 51 % consumption → CSS and AS exempt), GEOA (CSS cap, AS not applicable when contract demand not reduced), state RE waivers with sunset dates; each exemption is a rule row and its application is a line with the rule's source_ref.
Sources: discom_grid, discom_green_tariff, rooftop_pv (net metering/gross/net billing per net_metering rules by size), btm_bess, oa_solar_intra, oa_wind_intra, oa_hybrid_intra, oa_solar_ists, oa_wind_ists, oa_hybrid_ists, oa_bess, pumped_storage, iex_dam, iex_rtm, iex_gdam, iex_gtam, iex_tam, iex_hpdam, captive_thermal, group_captive (adds an equity-cost line).

engine/lcoe.py and engine/lcos.py: levelised cost with every assumption as a SourceRef of kind assumption, editable.

API: GET /connections/{id}/landed-cost?scenario=... returning every source's waterfall per ToD slot and the 15-minute series; GET /rulebooks/limits for the connection (RE cap % of CD, storage mandate, minimum OA size and CD). UI: journey step 3 — one Harmony card per source with the waterfall (INR/kWh at the meter by slot), each line with its citation and PDF link; a comparison bar of all sources against avoided cost by slot; the analyst view shows the assumption chips and the rule rows behind each card.

Tests: unit per component and per exemption with hand-computed expectations; three test consumers (11 kV, 33 kV, 132 kV) in each state against a hand-built spreadsheet committed as tests/fixtures/landed_cost_<state>.csv (the person supplies or approves the spreadsheet); every returned line asserted to carry a source_ref resolving to a stored document; integration; e2e from bill drop to step 3.

Done when: the spreadsheet comparison matches to the paisa for all six consumers and every source, or the difference is a named rule gap; the field-trace shows every step-3 field with an owner; reviewer clean. STOP.
```

### Stage 5 — Settlement simulator

```
Run Stage 5: settlement. Pure, deterministic, exhaustively tested; the optimizer will be checked against it.

settlement/simulate.py: inputs — load profile (35,040 kW), per-source injection profiles (kW), the approved settlement rule for each source's scope, tod_slots, set_off_order. Output — per block: grid drawal, each source's set-off, bank deposits and withdrawals per bucket, banking charge in kind, curtailment; per period: bank balance by bucket, lapse quantities and their payment at the rule's price; and SettlementStatement lines as SourcedValue.
Granularities: block_15min (net each block; surplus → bank or lapse per rule), hourly, tod_slot_monthly (net within slot across the month; surplus by slot → bank buckets per slot or pooled as the rule states), monthly_aggregate, annual.
Banking: deposits only from allowed sources; charge in kind or INR/kWh; period monthly|quarterly|financial_year with carry-over; drawal_windows as (allowed_slots, months) lists; lapse treatment lapses|paid at APPC × factor|paid at RE tariff; withdrawal priority as the rule states (same slot first, else allowed slots in order).
ISTS vs intra-state: separate scopes; an ISTS source whose state disallows banking of ISTS power is netted at block level with surplus sold at a scenario price.

API: POST /connections/{id}/settle with a dispatch → statement. UI: analyst-only settlement explorer showing a month's bank buckets filling and draining.

Tests: unit per granularity and per banking field with small hand-worked examples (table-driven, in tests/settlement/cases/*.yaml and mirrored to packages/rulebooks/golden/); property tests (energy conservation every block; bank never negative; lapse + withdrawals + charge = deposits over a period); e2e: reproduce a year of a real OA consumer's monthly settlement statements supplied by the person (data/settlements/, anonymised) within 0.5 %.

Done when: golden settlement cases for UP and Maharashtra pass; the real statements are reproduced or the gap is a named rule gap; reviewer clean. STOP.
```

### Stage 6 — Optimizer

```
Run Stage 6: the optimizer. Pyomo + HiGHS. The simulator of Stage 5 is the judge.

optimizer/model.py: a MILP over 35,040 blocks of one representative year (option: 8,760 hourly for preview). Variables — capacities per source (continuous; OA sources in MW with a minimum-size indicator binary where the regulatory_limit sets a minimum; BESS kW and kWh; contract demand kVA as a step variable with a change cost), dispatch per block (grid drawal, each OA schedule ≤ capacity × CUF, IEX buy ≤ cap, BESS charge/discharge with SOC and efficiency, bank deposit/withdrawal per bucket, thermal unit output with on/off binaries, curtailment). Constraints — energy balance; settlement linearised per the rule (bank buckets as inventories with window masks; charge in kind as a factor; lapse at period end); regulatory limits (total RE ≤ cap % of CD; storage ≥ mandate; minimum OA size; minimum CD for OA); thermal (technical minimum when on, ramp per block, min up/down time, must-run for waste heat); demand (recorded MD ≤ CD or penalty variable; LF incentive piecewise); client constraints (max roof kWp from roof_sqm, max land). Objective — Σ CRF × capex + Σ landed cost lines × energy (every per-kWh and per-MW term from Stage 4 as coefficients) + fixed and demand charges + penalties − incentives, annual INR. Solver — HiGHS with a time limit and MIP gap from settings; log the gap.
optimizer/resettle.py: run settlement.simulate on the solver's dispatch; compare settled quantities and cost; disagreement above tolerance → run failed_resettle (invariant 6).
optimizer/scenarios.py: scenario = candidate source set + price assumptions + rulebook pins + sensitivity ranges; run as worker jobs (compose `worker`), results in runs/results with every pin.
Outputs: capacities, annual cost before/after, saving, simple payback, IRR, emissions (grid factor as a sourced value), the settled dispatch, the waterfall per source at the chosen sizes, binding constraints named in plain words ("RE capped at 200 % of contract demand by <rule>, page N").

API: POST /sites/{id}/scenarios, POST /scenarios/{id}/run, GET /runs/{id}, POST /runs/{id}/replay (invariant 5). UI: journey step 5 — scenario cards side by side (sizes, saving, payback), the 15-minute dispatch for a chosen week, binding constraints with citations.

Tests: unit for every constraint family on tiny models (3 blocks) with known optima; resettle agreement on every test model; replay identity; a 5 MW test site in each state solves at 15 minutes under two minutes on the VM; integration; e2e from bill drop to step 5.

Done when: both test sites solve within time with resettle agreement and the replay test passes; three scenarios compared on one screen; reviewer clean. STOP.
```

### Stage 7 — Journey, voice, live plan

```
Run Stage 7: the client experience. Nothing new in the engines.

Journey: the six steps as one continuous Harmony flow with the left rail live; assumption chips editable anywhere, re-running what they affect; every number with its citation and PDF link; mobile layout works.
Voice (voice/): mint ephemeral OpenAI Realtime tokens; browser connects by WebRTC; the session's tools are the SiteIntake field setters (Stage 2 schemas) during intake and what-if tools during the plan (set a price, a capacity, a contract demand, toggle a source, pick a state rule version) that run the simulator or a fast hourly optimizer preview and read back the result in one sentence. The system prompt for the voice says: you take inputs and read back results; you never compute, never quote a number that a tool did not return, never state a regulation. Text chat shares the tools.
Live plan (report/): /p/{token} — a shareable page of the plan with the voice what-if enabled; a "jouleWise view" toggle for analysts showing every assumption, rule row, run pin and margin; PDF export via headless Chromium of the same page, with citations as footnotes and the document list as an appendix.
Explanations: short English explanations of each waterfall and of each binding constraint drafted by the Anthropic model through providers/ from the SourcedValues only (prompt explain_v1); displayed as "explanation" with the sourced numbers beside it, never replacing them.

Tests: Playwright end to end — a new client from bill drop to a shareable link with no analyst touch; voice tool-call tests with the Realtime API mocked at the transport (schemas exercised, no network), one marked external real call; PDF export contains every citation; analyst view hidden from client role.

Done when: the e2e passes on two real bills; a voice-only intake produces the same SiteIntake as the typed form for the same facts; /p/{token} works for a logged-out visitor; reviewer clean. STOP.
```

### Stage 8 — Breadth and launch

```
Run Stage 8: breadth and launch.
- Seed Karnataka (KERC combined order: BESCOM, MESCOM, CESC, HESCOM, GESCOM), Gujarat (GERC: MGVCL, UGVCL, DGVCL, PGVCL), Rajasthan, Tamil Nadu, Telangana, Andhra Pradesh, Punjab, Haryana through the regulation reader, each approved by an analyst with golden tests, from documents the person uploads. Where a document is missing, the state shows "not yet sourced" and is listed in known-gaps.
- Login: email magic link; roles analyst|client; share tokens; CORS and headers; secrets check in CI.
- Performance: optimizer worker concurrency; caching of approved rules; response times on the plan page under 1 s for cached runs.
- Deployment: the Google Cloud VM in asia-south2, Compose with Caddy TLS at the jouleWise hostname the person gives; backups of postgres and data/ nightly.
- The one final test pass: every e2e on every seeded state; a written release note.
Done when: eight states approved; deployed; the final pass is green; the release note is in docs/release-notes/. STOP.
```

---

## 8. Reference data

### 8.1 Rule families

| Family | Holds | Key fields (full schema in `packages/rulebooks/schemas/`) |
| --- | --- | --- |
| `tod_slots` | A DISCOM's time-of-day slot definitions per season and category | slots[] {name, start, end, months, surcharge_pct or rebate_pct or rate_delta_inr_per_kwh} |
| `tariff_schedule` | Retail rates for a category and voltage | billing_basis kWh|kVAh; fixed/demand INR/kVA/month with billing-demand rule; energy INR/unit by slot; FPPCA; electricity duty; PF incentive/penalty bands; LF incentive bands; prompt payment rebate; minimum charges; excess demand penalty; taxes |
| `oa_charge` | One charge component (section 2 of the plan) | component enum; basis INR/kWh | INR/kW/month | INR/MW/month | INR/MW/day | percent_in_kind | percent_of_price; value; scope (connection ists|intra, source, ownership, voltage band, category, capacity band); exemptions[] with conditions and sunset |
| `settlement` | How injection is netted, banked and settled | granularity; banking {allowed, charge, period, drawal_windows[], lapse, withdrawal_priority}; set_off_order[]; scope |
| `regulatory_limit` | Caps and mandates | limit enum (re_cap_pct_of_cd, storage_mandate_pct, min_oa_capacity_mw, min_cd_for_oa_kva, max_rooftop_pct_of_sanctioned_load); value; basis; scope |
| `ists_waiver` | CERC ISTS charge and loss waiver schedule by commissioning date | bands[] {commissioned_from, commissioned_to, charges_waived_pct, losses_waived_pct, years} |
| `net_metering` | Rooftop regime by size | regime net_metering|gross_metering|net_billing|behind_meter_only; size bands; export price; banking/settlement for rooftop; grid support charge |

Every rule row has `scope`, `body` (validated by the family schema), `source_ref` (validated by `source_ref.schema.json`) and belongs to a `rulebook_version` with `effective_from`/`effective_to`.

### 8.2 `source_ref`

```yaml
kind: regulation          # regulation | order | client_stated | assumption | measured | derived
document_id: 7f3a…        # row in source_documents; the PDF is stored and served
page: 14                  # 1-based printed page the quote is on
quote: "Banking charges shall be 6% of the energy banked"   # verbatim, ≤ 300 chars
effective_from: 2025-04-01
effective_to: null
note: "applies to intra-state solar and wind; ISTS excluded per clause 12.3"
```

A `derived` SourcedValue carries the union of its inputs' refs. `client_stated` and `assumption` carry no document and render as editable chips.

### 8.3 Bill fields consumed from billx contract 1.1

`utility.name`, `tariff.category`, `connection.tariff_category`, `period.from|to|bill_month`, `demand.contract_kva`, `demand.max_kva`, `energy.kwh`, `energy.kvah`, `energy.billed_units`, `energy.tod[] {slot, kwh}`, `energy.power_factor`, `charges.energy`, `charges.demand`, `charges.by_code[] {code, amount}`, `open_access.re_kwh|non_re_kwh|banked_kwh`, `net_metering.import_kwh|export_kwh`, `green_tariff.kwh`, `totals.current_charges|arrears|due_date_rebate|net_payable`, and per bill `accepted`, `accepted_by`, `status`, `review_reasons[]`, `profile.id`.

### 8.4 Source list to offer the client

`discom_grid`, `discom_green_tariff`, `rooftop_pv`, `btm_bess`, `oa_solar_intra`, `oa_wind_intra`, `oa_hybrid_intra`, `oa_solar_ists`, `oa_wind_ists`, `oa_hybrid_ists`, `oa_bess`, `pumped_storage`, `iex_dam`, `iex_rtm`, `iex_gdam`, `iex_gtam`, `iex_tam`, `iex_hpdam`, `captive_thermal`, `group_captive`.

### 8.5 Load shapes to ship

`continuous_process`, `two_shift`, `single_shift`, `cold_storage`, `textile_spinning`, `steel_induction`, `pharma_formulation`, `food_processing` — each a normalised weekly 15-minute shape with a note on how it was derived; the person may replace any with ergOS measured shapes.

---

## 9. Definition of done

| Stage | Checks before STOP |
| --- | --- |
| 0 | compose up serves web :3000 and api :8000; billx health reachable; SourcedValue rejects empty refs (test); PDF opens at page N from the web shell; watcher green; reviewer clean |
| 1 | Two states with approved `tariff_schedule`, `tod_slots`, `oa_charge`, each row with page citation; absurd-draft-invisible test passes; trigger rejects unattributed write (test); YAML export regenerates without diff; ≥ 5 golden tests per family per state; reader e2e on the NPCL order; reviewer clean |
| 2 | Two real bills from different DISCOMs → connection + 12 months + synthesised profile (kWh exact, ToD within 0.1 %, max = MD); needs_review round-trip; six IEX CSVs loaded with vintages; reviewer clean |
| 3 | Replay of 10 bills: match or explained, unexplained list empty; every step-2 line opens its PDF page; avoided-cost heatmap renders; reviewer clean |
| 4 | Six test consumers × every source match the approved spreadsheet to the paisa or name a rule gap; every returned line has a resolving source_ref (test); field-trace complete for step 3; reviewer clean |
| 5 | Golden settlement cases pass for both states; property tests pass; real statements reproduced within 0.5 % or gap named; reviewer clean |
| 6 | Two 5 MW sites solve at 15 min in < 2 min on the VM; resettle agreement; replay identity; three scenarios on one screen; reviewer clean |
| 7 | Bill drop → shareable link with no analyst touch (Playwright); voice-only intake = typed intake; PDF carries citations; analyst view hidden from clients; reviewer clean |
| 8 | Eight states approved; login and roles; deployed with TLS; final full pass green; release note |

Two honest numbers wherever a rate is reported: the rate over what was attempted, and the coverage of what was attempted over what exists (bills replayed / bills accepted; rule rows sourced / rule rows present). "Not yet sourced" is a correct answer, never a failure.

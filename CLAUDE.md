# ergPLAN — CLAUDE.md

You are building ergPLAN (jouleWise | ergPLAN) in this repository. The full build plan is `docs/MASTER-PROMPT.md`; each session runs one stage of it (`Run Stage N of docs/MASTER-PROMPT.md`). Sections 2–5 of that file are reproduced here verbatim and apply in every session. If this file and the master prompt ever differ, the master prompt is authoritative and this file must be regenerated with `tools/dev/sync-claude-md.sh`.

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
| Regulation reading | Anthropic model through `providers/`, prompt-versioned, output is draft rule rows each with `page` and `quote` | Different family from the voice; reviewed by a person |
| Prices | IEX CSVs uploaded by an analyst in the app; parsed by `intake/iex_loader.py` into `price_series` with a `vintage` | jouleWise has the CSVs |
| Load profiles | Synthesised from 12 bills using `packages/profiles/` shapes, exactly matching monthly kWh, ToD split and recorded MD; measured 15-minute upload when it exists | Most clients have only bills |
| Reports | Live shareable plan link `/p/{token}` with voice what-if; jouleWise analyst view toggle; PDF export via headless Chromium of the same page | One page, three audiences |
| Deployment | Docker Compose: `web`, `api`, `worker`, `postgres`, `billx`, `caddy`; laptop until Stage 5, then a Google Cloud VM in `asia-south2` | Same shape as houseoframa |
| Access (until Stage 8) | Email magic link; roles `analyst` and `client`; share links by token | Speed now, security at launch |
| Builder and reviewer | Claude Code builds; `tools/review/run.sh` reviews with an OpenAI model | Different families, different blind spots |
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
        regreader/               regulation PDF → draft rule rows with page + quote (uses providers/)
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

# billx build prompt, version 4.2: the intelligent, verified-reading bill platform, built on a Mac mini, serving esgOS first

12 Oct 2026 · Joulewise · version 4.2 revises 4.1 with three inputs. **The esgOS change list of 11 Oct 2026** (saved as `docs/esgos-changes-2026-10-11.md`): esgOS (`Ergplan/esgOS`) is the first customer and goes live within days; it accepts OpenAI and Anthropic as providers; it accepts contract 1.1, which is written and served, not proposed; it calls the hosted service on the `esgos` key with permanent storage and runs the embedded image until then; unverified layouts pass for it with `profile.status` saying the layout's state; gas is read generically right after Stage 2; it gets insights on every passed bill and owns its own leads; billx never creates branches in its repository. Those items override anything in 4.1 that conflicts, are recorded in `docs/decisions.md` under "esgOS changes (11 Oct 2026, from Joulewise)", and are not reopened. **A two-week target:** section 13 is now a 14-day sprint in three parallel sessions that ships only what a calling application needs, followed by the roadmap in the 4.1 order. **Three engines, one data contract** (Bill Reader, Bill Auditor, Bill Intelligence; section 1, 10.4) with the principle that billx never silently converts a plausible AI extraction into a financially trusted value (invariant 0). **A sprint with acceptance requirements per period** and a controlled pilot, not general production, on day 14 (13.1). **No cloud project of billx's own:** code, CI and images on GitHub; bills, database and the hosted service on the Mac mini behind a tunnel until O22 says otherwise (section 3.1). From 4.1 it keeps: the 10-bill sample during the build with accuracy measured and tuned in Stage 11; serving mode for any application (6.6); security cut to three items until launch (section 11); all product testing in Stage 11. It supersedes 4.1 and Part B of "billx Developer Guide: super billx" (version 2). Part C of version 2, esgOS's bill engine contract 1.0, stays valid: this build keeps it working unchanged as a subset of the engine's own API (section 6).

**How to use this file.** Save it in the billx repository as `docs/build-prompt.md`, replacing 4.1, and copy sections 1 to 5 into `CLAUDE.md` (for the builder) and `AGENTS.md` (for the reviewer) again. After that, each session starts with one line: `Run Stage N of docs/build-prompt.md` (or `Run day D, session X of docs/build-prompt.md` during the sprint).

**Who does what.** Claude Code, running on the Mac mini (Claude Max plan, with extra usage or a Console API key when limits are reached), is the **builder**. An OpenAI model (gpt-6-astra, through the OpenAI API key) is the **reviewer** in Stage 11 and the **second reader** when test bills are prepared. Both models run in their providers' clouds; only Claude Code, the code, the tests and the confirmed bills live on the Mac. People on the Joulewise team supply real bills, confirm the golden set, check tariff formulas against the orders, and merge each stage.

---

## 1. Mission

**Every bill that arrives, in any form, is read, verified, rechecked against the tariff order, broken into every charge element, and kept permanently in a clean database that users can question in plain language.**

For every bill, in this order:
1. **Intake** in any form: PDF (digital, scanned, password-protected), photo, image, zip, email attachment, API or MCP upload. A file that isn't an electricity bill is identified and the user is told what it appears to be (section 5.0).
2. **Reading** under a documented verification rule: a value the engine marks `verified` met the rule in 5.2 (two independent readers agree, or genuine PDF text tied to the bill's arithmetic). The target is zero silent errors, measured on held-out bills in Stage 11 and in production; it is never advertised as a guarantee. The engine refuses a bill, or holds it for a person, rather than guess (sections 5.1 to 5.3).
3. **Validation:** the bill's own arithmetic (section 5.4).
4. **Formula recheck:** every charge recomputed from the bill's own quantities and printed rates (section 5.5).
5. **Tariff-order recheck:** every charge recomputed independently from the regulator's tariff order for that state, category and month, and compared with what was billed (section 5.5).
6. **Element capture:** energy by TOD slot, demand, FPPCA and its variants, electricity duty, cess, every rebate and surcharge, arrears, subsidies, open-access charges, all coded to one common catalogue (section 5.7).
7. **Permanent storage** of the file, every reading, every value with its proof, every check and recheck, under the terms the user accepted at sign-up. Nothing is overwritten or deleted, except through the erasure command (section 9A.5).
8. **Intelligence:** insights, anomalies, forecasts and a question-and-answer assistant over the user's own bills (sections 9 and 9C).

**Three engines, one data contract.** billx is three engines that share the core schema (Stage 1.1) and the bill record (9A.2), and nothing else. Each is built, tested, released and sold on its own.

| Engine | Does | Never does | Code |
| --- | --- | --- | --- |
| **1. Bill Reader** | Turns PDFs and images into structured fields, values and evidence: intake, document type, readers, consensus, the self-consistency checks of the bill against itself (G-series, formula recheck), the verification decision | Knows no state tariff rule; never changes a value after reading | `billx/reader/`, `billx/core/` |
| **2. Bill Auditor** | Takes a bill record and independently recomputes every charge from the regulator's tariff orders, notices and billing parameters; records match, difference or not computable, with citations | Never re-reads the bill; never changes a value or a verification. Runs again, on the stored record, whenever tariff data changes (`re_audit`, 9A.6) | `billx/auditor/` |
| **3. Bill Intelligence** | Trends, anomalies, forecasts, savings insights, benchmarks and the assistant, for esgOS, ergOS and every other calling application | Reads verified values only; never feeds anything back into reading or auditing | `billx/intelligence/` |

The sprint ships Engine 1 complete, Engine 2's self-consistency part only (the tariff audit is Stage 5b), and Engine 3's six no-tariff insights. The day-14 release therefore describes itself as **a bill-reading and basic-insights service, not a regulatory bill auditor**, and every bill it returns says so in `audit_status`.

**The principle every engine keeps:** billx never silently converts a plausible AI extraction into a financially trusted value. A value is `unverified` until the rule in 5.2 is met, a bill from a draft or unknown layout says so on every result, and a bill that has not been audited against the tariff order says that too, so a downstream financial or ESG report can label what it is built on.

**Surfaces**

| Surface | Who uses it | What they get |
| --- | --- | --- |
| **Product API (serving mode)** | Any application that holds bills its users uploaded: esgOS (`git@github.com:Ergplan/esgOS.git`) first, others later | Sends a bill, gets back the values it needs: each registered product has its own field set and contract mode, and calls the hosted service with one key (section 6.6). esgOS's contract 1.0 keeps working unchanged |
| **Public Bill API** | API customers (free) | The same API with tenant keys and cost recording |
| **MCP connector** | Joulewise clients using Claude, ChatGPT or other LLM apps | Tools to read bills, get verified values, explain charges, find savings and ask the assistant |
| **Clean copies and JSON for MIS** | Clients who keep bill data in their own systems | Standard JSON, CSV and one-page PDF per bill, and JSON built on demand from the database for any account, period or comparison |
| **Bill database** | Users analysing their own bills; Joulewise analysts, with consent (section 9A.4) | Every element of every bill, permanently, as SQL views, JSON, CSV, Excel, Parquet and API series |
| **Assistant** | Users in the web app, the API and MCP | Answers about trends, comparisons and analytics, with every number taken from the database (section 9C) |
| **Comparison lab** | The Joulewise team | Docling and LlamaParse outputs side by side with the verified result, per bill and in aggregate (section 9B) |
| **User web app** | Users uploading and analysing their bills | Upload, a live view of each bill being read, checked and rechecked, the bill database, analytics and the assistant (section 9D) |

And one business purpose: **leads for Joulewise.** Every sign-up and every bill upload, from any Joulewise application or from billx itself, becomes a **contact lead** with a clear name, email and company, shared with Joulewise (section 9.3). Every verified bill is also scanned for savings and billing errors (section 9), and with the user's consent a worthwhile finding becomes a **savings lead** on top.

**Priorities, in order, for every trade-off during the sprint and the roadmap up to Stage 10:** an engine esgOS can run within days (the 0.x image) and call within two weeks (the hosted service); then every value a caller receives carrying its `proof`; then complete capture of every printed element; then coverage; then cost; then speed. The verification *design* (section 5: two independent readers, consensus, one decision rule, the pass rule) is built from Stage 1 because it is cheap and it is what keeps a returned value honest, but its *accuracy is not measured or tuned* until Stage 11: the build runs on a sample of 10 bills per layout, no stage is blocked by an accuracy gate, and `profile.status` tells every caller the layout's state. **In Stage 11 the priorities flip:** zero silent errors first, measured on the full golden set, before the public launch. The product is free and users agree to permanent storage at sign-up, so security is not a priority for this build (section 11); it is hardened in Stage 12.

## 2. Definitions

| Term | Meaning |
| --- | --- |
| **Guaranteed field** | A field the API promises: the list in section 6.4 |
| **Verified field** | A guaranteed field whose verification under the rule in 5.2 is `verified` (or `confirmed` by a person). An acceptance rule, not a guarantee |
| **Verification** | The one decision per field made by `decide` (5.2): `unverified`, `verified`, `disputed` or `confirmed`. Evidence (readings and proof levels) is what it is decided from |
| **Accepted bill** | A bill a caller may use: `passed`, or `confirmed` where the product accepts human-confirmed bills (5.2, 6.6). `passed` itself never changes meaning |
| **Passed bill** | A bill that meets the pass rule of section 5.2; a bill flagged `printed_inconsistency` is passed |
| **Silent error** | A guaranteed field or charge element marked `verified` on an accepted bill that differs from the value a person confirms from the source |
| **Coverage** | Passed bills ÷ bills submitted that are readable bills |
| **Correct refusal** | An unreadable or non-electricity file refused rather than read, where the golden label agrees; never counted as an error |
| **False refusal** | An electricity bill refused as another document type, or as unreadable when a person can read it; always counted, and gated (section 12.4) |
| **Sample set** | 10 real bills per layout, confirmed by a person, used during Stages 0 to 10 to run and demonstrate the engine; all of it is tuning data, none is held out |
| **Golden set** | The full set of confirmed real bills (30 to 60 per layout) built in Stage 11, kept on the Mac (mirrored to the external drive), never in git; the sample set becomes part of its tuning half |
| **Held-out set** | The half of the golden set never used for tuning prompts, profiles or formulas; the launch gate runs on it (12.1 says how it stays clean) |
| **Layout** | One discom's bill design in one period; a profile version describes one. `profile.status` on a bill is `verified` (met its launch gate), `draft` (a profile exists, unmeasured) or `none` (no profile; read by the generic ladder) |
| **Bill record** | The permanent, versioned record of one bill in the database: file, readings, values with proofs, checks, rechecks, elements, insights |
| **Charge element** | One printed charge, rebate, surcharge, duty, cess, arrear or adjustment, coded to the common catalogue (section 5.7) |
| **Comparison reader** | Docling or LlamaParse: run on bills for comparison only; never a proof, never a source of stored values (section 9B) |
| **`detects:`** | The smallest error a check or formula can catch, declared in its definition, so Stage 11 can write its planted-misread test |

**What "zero" can honestly claim.** Zero silent errors in *n* held-out bills bounds the true silent-error rate below about 3 ÷ *n* with 95% confidence (the rule of three): below 20% at 15 bills, 10% at 30, 1% at 300, 0.1% at 3,000. Every report states *n* next to the zero. During Stages 0 to 10 there is no held-out set, so **no accuracy claim is made**: a calling application is told, in `GET /v1/utilities` and in `docs/accuracy/`, that each layout is `unmeasured` and gets every value with its `proof`. The claim starts in Stage 11, with 30 bills per layout giving a weak 20% bound on 15 held out and 60 giving 10%. Production keeps measuring after that (section 12.3), because a gate on a sample is not proof for every future bill.

## 3. Operating rules for the agents

1. **Stages in dependency order, as fast as the machine allows** (section 13). A stage starts as soon as the stages it depends on are merged, not when the previous number is: the dependency table in section 13 says which. Inside a stage, independent items run in parallel builder sessions on git worktrees (3.1), each on its own `stage-N-x` branch, merged into `stage-N` as they finish. Once Stage 5 is done, Stage 10 (coverage) runs beside everything after it. The team may switch to autonomous mode (the agent merges when its own tests are green and the stage's "done when" holds) from day 4 of the sprint (O9).
2. **A stage ends** when its "done when" list holds on synthetic bills, the builder's own tests and CI are green, and `docs/stage-reports/stage-N.md` records what changed, defaults chosen, pending items and model spend. No independent review during the build; it runs once, in Stage 11.
3. **Branches.** Each stage starts from `main` on `stage-N`, tagged `stage-N-start`. Never push to `main`. CI builds one image per commit; a release is a tag on `main`.
4. **Unit tests come with the code,** written by the builder, run by CI; no coverage gate. Every check and formula declares in its definition the smallest error it can detect (`detects:` in the YAML or the docstring); the planted-misread tests that prove it are written in Stage 11. Product-level tests (contract, MCP, Playwright, assistant, privacy, erasure, isolation, append-only, load) are Stage 11 work.
5. **Never commit over red.** Never skip, delete, loosen or mark expected-failure a test. Never narrow a "done when" item. A correct refusal is never counted as wrong; a false refusal always is.
6. **The model transcribes, never calculates.** Every number in `data` is printed on the bill. Formulas, totals, insights and conversions live in code.
7. **Exact numbers.** `Decimal` from reading to response, carried in the Pydantic v2 models of the core schema (Stage 1.1) in strict mode. One test (kept from Stage 1) fails on any float in a result, an export or an MCP tool output.
8. **One implementation per check and formula.** The API, MCP tools, exports, insights, studio and evaluation all call the same validation and formula code.
9. **Model calls only in `billx/providers/`.** Prompts are versioned files under `billx/prompts/`, never edited in place. Every call has a timeout, bounded retries, a cost estimate before it and a usage record after it.
10. **No real bills in git, CI logs, the image, test fixtures, or any request to the reviewer.** Synthetic bills only in the repository. Reports describe bills by discom, layout and input kind, never by consumer or value.
11. **No questions during a stage.** Use the defaults in section 15, record each choice in `docs/decisions.md`, list what only a person can give in `docs/pending-for-user.md`, and continue with synthetic data.
12. **Nothing environment-specific in code.** Hosts, keys, model ids, prices, limits, retention and paths come from configuration.
13. **Living documents change in the same commit as the code:** `docs/architecture.md`, `docs/decisions.md`, `docs/known-gaps.md`, `docs/runbook.md`, `docs/pending-for-user.md`, `docs/api.md`, `docs/mcp.md`, `docs/insights.md`, `docs/data-model.md`, `docs/assistant.md`, `docs/comparison.md`, `docs/accuracy/`.
14. **Rate limits.** On a provider 429, wait 60 seconds and retry with backoff. Record each stage's real spend for every provider (OpenAI, Anthropic, LlamaParse).
15. **Comparison readers never verify.** Docling and LlamaParse outputs are stored and compared; they never become a value in a bill record, never count towards consensus, and never run inside the engine image.
16. **The assistant never states a number it did not get from a tool.** Every figure, trend and comparison it gives is computed by code over verified values in the database, and every answer cites the bills it used.
17. **Append, never overwrite.** A correction, re-read or new profile version creates a new version of a bill record; earlier versions stay readable.

**Independent review** runs once, in Stage 11, over the whole codebase. The reviewer is the OpenAI model on its own key and budget, never the builder's model family. It reviews each stage's diff in order, given only that diff, `CLAUDE.md` and this file, and answers: (a) is every invariant upheld, citing file and line; (b) does every check, formula, proof decision and route have tests including a planted misread; (c) does the API still match section 6 and esgOS contract 1.0 exactly; (d) is there any key, real bill value or consumer name in the diff; (e) does the stage report claim anything the code doesn't support. From sections 5 and 6 and each stage's "done when" list only, never from the code, it writes black-box tests in `tests/independent/stage-N/`. The builder never edits them; a disputed test gets one revision, then goes to the team. **Never sent:** real bills, golden-set data, consumer names, account numbers or amounts. Every request body is searched for the client identifiers before it leaves.

### 3.1 The build machine: Mac mini (Apple silicon, M4 Pro)

The whole build runs on one Mac mini, and billx has no cloud project of its own: code, CI and images live on GitHub, the confirmed bills live on the Mac with an external-drive mirror, and the hosted service runs from the Mac through a tunnel until O22 says it moves. esgOS's registry is esgOS's project.

**Where each job runs**

| Job | Runs on |
| --- | --- |
| Claude Code (builder), the watcher; the reviewer script in Stage 11 | Mac mini |
| The builder's unit tests | Mac mini, natively (arm64), and in CI |
| Studio: sample-set confirmation during the build, the review queue for hosted `needs_review` bills from day 10, golden-set confirmation for Stage 11 | Mac mini, on 127.0.0.1 (Tailscale for the rest of the team), for the person confirming |
| `billx eval` on real bills | Mac mini only, run by hand on the sample set at the end of Stages 1, 4, 5 and each Stage 10 state, for information; on the full golden set, and nightly by launchd, from Stage 11. CI never sees a real bill |
| Both deployment modes end to end (API, workers, Postgres with pgvector, object storage stand-in) | Mac mini, in Docker (arm64 images) |
| The comparison worker (Docling, LlamaParse) and the assistant service (Haystack) | Mac mini in development, each in its own container; hosted in production |
| The shipped `linux/amd64` image and the identifier search over it | GitHub Actions |
| Images | GitHub Container Registry (ghcr.io) from CI; each release also pushed by digest to esgOS's registry (project `esgos-510707`) with `ESGOS_REGISTRY_KEY` |
| The confirmed bills (sample set, golden set) and the golden manifest | `~/billx-data/golden/` on the Mac, mirrored nightly to the external drive; never in git, never in CI |
| The hosted API, workers, Postgres and MinIO (staging and production) | Docker on the Mac mini behind a Cloudflare Tunnel (or Tailscale Funnel) at two fixed HTTPS names; a cloud VM under O22 |

**Machine set-up** (checked by `tools/mac/doctor.sh`, which reports pass or fail per item and never prints a secret):

- macOS current; FileVault on; a standard user account for the agents.
- No sleep while the build runs: in System Settings, prevent automatic sleeping and start up automatically after a power failure; `caffeinate -dimsu` beside each long session.
- Homebrew: Python 3.12 (in a project virtual environment), git, GitHub CLI, tmux, Tesseract, Docker Desktop (or OrbStack), and cloudflared (or Tailscale). An external drive, mounted, for the nightly mirror.
- `~/billx/` the repository; `~/billx-data/golden/` the sample and golden sets with their manifest, mirrored nightly to the external drive and never inside the repository; `~/billx-data/workspaces/` studio workspaces; `~/billx-data/hosted/` the hosted service's volumes (Postgres, MinIO), also mirrored.
- Keys in `~/billx/.env` (git-ignored): `BILLX_OPENAI_API_KEY` (Model A, evaluation, the assistant), `BILLX_ANTHROPIC_API_KEY` (Model B; the Claude Max plan covers Claude Code, not the product's own calls), `OPENAI_BUILD_REVIEW_KEY` (the reviewer, its own project and budget), `LLAMA_CLOUD_API_KEY` (LlamaParse comparisons, from Stage 9), `ESGOS_REGISTRY_KEY` (pushing releases to esgOS's registry), `CLOUDFLARE_TUNNEL_TOKEN` (the hosted service's hostnames), and `ANTHROPIC_CONSOLE_KEY` for Claude Code when the Max plan's limits are reached.
- **One call to each configured model id** (Model A, Model B, the reviewer, the assistant's chat model) with a one-token prompt, so a wrong or retired id is found in Stage 0 and not when Stage 1 starts.

**Running the agents around the clock**

- `tools/mac/session.sh N` starts builder session N (Claude Code in its own worktree) in a tmux window beside the shared watcher and log-tail windows. Every window survives a closed terminal.
- Claude Code runs a stage through its non-interactive mode with a permission allow-list in `.claude/settings.json` (the repository, the project's Python and Docker commands, `git`, `gh` on this repository), so it never waits on a prompt overnight. Anything outside the allow-list stops the stage and goes in the log.
- When the Max plan's five-hour or weekly limit is reached, the session switches to the Console API key if one is configured, otherwise pauses and resumes when the limit resets. Each stage report records time lost to limits. The team keeps a Console key configured so the builder never idles on a plan limit.

**Pace: use the whole machine, all the time.** The Mac mini is the only build machine and it is idle whenever a single session is waiting on a model, a test run or a Docker build. The rule is that it isn't.

- **Up to three builder sessions at once**, each in its own git worktree under `~/billx-worktrees/<branch>/` with its own tmux window, on independent items of the current stage or on the next stage whose dependencies are met (section 13). `tools/mac/session.sh N` starts the Nth session. Items that touch the same files run in one session; the stage prompt lists which items are independent, and the builder records the split in the stage report.
- **Tests use every core.** `pytest -n auto` on all performance and efficiency cores; OCR and `billx eval` run page-parallel across all cores; Docker Desktop (or OrbStack) is given at least 8 cores and half the machine's memory. The studio stays on 127.0.0.1 and is used by a person, so a session that sees the studio in use drops to half the cores for tests.
- **Builds and evaluations run in the background** (`tmux` windows, `caffeinate`), never blocking a session: a session starts an image build or an eval, carries on with the next item, and reads the result when it lands.
- **Never wait on the team inside a session.** A missing input (sample bills, a tariff order, the terms text, esgOS's registry key) goes in `pending-for-user.md` and the session continues with synthetic data or the default in section 15 (rule 11). A stage whose "done when" needs the sample set ends with every other item done and a note of what the sample run will add; the live run is a short follow-up session when the bills arrive.
- **No padding.** Library defaults, generated clients and the simplest structure that meets the "done when" list; no abstractions for a future stage; no refactor outside the stage's items. The living documents are updated, but briefly.
- **Report pace.** Every stage report states wall-clock time, session-hours used, hours lost to plan limits, and the longest single wait and its cause, so the team can remove the next bottleneck.

**Apple silicon and the shipped image**

- Development and tests run natively on arm64. The image is built for both `linux/arm64` (local Docker on the Mac) and `linux/amd64` (what esgOS and Cloud Run run), in GitHub Actions on every merge to `main`. A local `docker buildx --platform linux/amd64` build is for occasional smoke tests only; emulation is slow.
- **Local OCR check in Stage 0.** PaddleOCR must install and read a synthetic bill natively on macOS arm64, in the `linux/arm64` image and in the `linux/amd64` image. If any of the three fails, the agent records it in `decisions.md` and uses RapidOCR (PaddleOCR's models on ONNX Runtime) as the local reader on that platform.

**Where the frameworks live.** Docling and LlamaParse run in the **comparison worker**, a separate image (Docling's dependencies are several gigabytes), and only produce comparison outputs (section 9B). Haystack runs in the **assistant service** (section 9C). None of them is installed in the engine image, and none is a reader that can verify a value (section 5.1).

## 4. Invariants

Each overrides anything else in this file. If a stage prompt conflicts with one, the invariant wins and the agent flags it.

0. **No silent promotion** (always). No code path turns a reading into a verified value except `decide` (5.2), no code path turns a verified value into an accepted bill except the pass rule and a named person's confirmation, and no result hides that a layout is draft or a bill is unaudited (`profile.status`, `audit_status`).
1. **Passed means verified** (from Stage 1). `passed` is true only under the pass rule of section 5.2, and `decide` in `billx/validate/proof.py` is the only code that assigns a verification.
2. **Skip is never pass** (always). A check whose inputs are missing reports `skip`.
3. **The model transcribes** (always). Every value in `data` is printed on the bill.
4. **Exact decimals** (from Stage 1).
5. **esgOS contracts 1.0 and 1.1 keep working** (from Stage 2). Their calls, fields, enums and error codes behave exactly as written; 1.1 adds optional fields only and `passed` keeps 1.0's meaning (section 6.5).
6. **Repeatable** (from Stage 1). The same file, engine version, profile version and model ids give the same result; temperature 0 where the model accepts it.
7. **Utility knowledge is versioned data** (always). Profiles and formulas are YAML; final versions are frozen; every tariff parameter cites its order.
8. **Insights never change a value** (from Stage 6). Insights read verified values; they never feed back into reading or checks, and never appear on a bill that didn't pass.
9. **The caller decides model use** (from Stage 2). With `allow_cloud_model` false, no cloud call is made for that job by any service: readers, the document-type gate, LlamaParse, or embeddings. Spend never exceeds `max_cost_usd`; every call is in `usage`.
10. **No values in logs** (from Stage 2). Logs, metrics, traces and error messages carry ids, hashes, timings and check ids only.
11. **Permanent and append-only** (from Stage 3, `permanent` storage). Bill records are never overwritten or deleted, except by `billx erase` (section 9A.5), which is logged.
12. **No storage without accepted terms** (from Stage 3, `permanent` storage). A bill is stored only for a tenant whose users accepted the terms at sign-up.
13. **Comparison readers never verify** (from Stage 1). See rule 15.
14. **Assistant numbers come from tools** (from Stage 8). See rule 16.

## 5. Verification design

This section is the heart of the build. Every other surface only carries what it produces. The word used everywhere is *verified*: a value met the acceptance rule in 5.2. Nothing in the product, its documents or its sales material says "proven", "guaranteed" or "zero-error"; the zero is a target measured on held-out bills (section 2), and the measurement is what is shown.

### 5.0 Intake: any bill, in any form

**Formats**

| Input | Handling |
| --- | --- |
| PDF, digital | Text layer with character boxes, plus rendered pages |
| PDF, scanned or mixed | Rendered pages; a hidden OCR layer is never treated as a genuine text layer (5.1) |
| PDF, password-protected (common for Indian e-bills) | Opened with `pdf_password` given with the upload (used once, never stored or logged), or with a password the user saved in the web app's settings (stored under a key from configuration, never logged or returned). Without one, the bill is `needs_review` with `password_required` |
| JPG, PNG, HEIC, WebP, TIFF (multi-page too), BMP | Photo preparation and the quality gate (Stage 4) |
| HTML e-bills and portal pages saved by the user | Rendered to pages with network access off (no remote fetches); their text is a genuine text layer (5.1) |
| Spreadsheet exports from discom portals (XLSX, CSV) | Stored as received; `needs_review` with `unsupported_format_profile` until a per-format profile maps cells to fields. Then the mapped cell is reading 1 and the label rule of 5.3 applied over the cells (the value cell right of or below the label cell) is reading 2; a cell value alone is `single` |
| ZIP of any of these | Unpacked one level deep, at most 100 files and 200 MB uncompressed (configurable); each file is its own intake. An encrypted ZIP is `password_required`; one beyond the limits is refused with its reason |
| One file holding several bills, or pages that aren't bills | Sorted into bills; other pages kept with the file and marked |

**Document-type gate.** Before any reading, every file (and every page group within it) is classified as `electricity_bill`, `gas_bill`, `water_bill`, `telecom_bill`, `other_invoice` or `not_a_bill` (receipts, letters, ID cards, photos of other things):
- **Local signals first,** from the text layer (and from local OCR once it exists, Stage 4): units (kWh, kVAh, kVA, SCM, MMBtu, kilolitres), discom and supplier names from the profiles' `match` patterns, meter-reading tables, words such as "tariff", "contract demand", "unit consumed". A vision model confirms only when the local signals are unclear and the caller allows cloud use.
- **Before Stage 4, a scanned or photo page with no text layer** is classified by Model A when the job allows cloud use; otherwise the result is `model_not_allowed`, never `not_a_bill`.
- **Anything other than an electricity bill is never read as one.** The user gets a plain message naming what the file appears to be, for example: "This looks like a water bill from <supplier as printed>. billx reads electricity bills and gas bills." Gas bills go to the gas reader once it exists (Stage 2b, in the first sprint week); before then the message says gas reading is not available yet.
- **Status:** `wrong_document_type` with `document_type` in `full` mode; in `esgos-1.0` mode as the table in 6.1a says (`not_a_bill`, except a gas bill before the gas reader).
- **What is kept** (`permanent` storage): gas, water and telecom bills are kept under the accepted terms, with their classification, so a later version can read them. A file classed `other_invoice` or `not_a_bill` keeps its hash, classification and page count permanently, but the file itself is deleted after `NON_BILL_RETENTION_DAYS` (default 30, so a person can correct a misclassification), and the deletion is logged.
- A file of mixed documents (an electricity bill and a payment receipt, for example) keeps the bill and reports the rest by type.

**Channels:** web app upload, API (`POST /v1/jobs`, `POST /v1/batches`), MCP (`read_bill`), and email (from Stage 7, when users exist): each tenant gets an inbound address, and attachments whose sender address belongs to a registered user of that tenant are taken in. Mail from anyone else gets a reply saying to sign up first, and nothing is stored. A password-protected PDF by email uses the user's saved password, or gets a reply asking them to save one or upload in the web app. WhatsApp is deferred (O19).

**The same bill twice** (within one tenant only; the same file from another tenant creates a separate record). The same file (by sha256) links to the existing record. A different file of the same bill (a photo and the PDF, for example, matched on utility, account, bill month and bill number) joins the same bill record as another source. Its readings are compared with the record's; any verified value that disagrees puts the record in `needs_review` with `source_conflict`.

### 5.1 Readers and proof levels

A **reader** produces a value for a field from the bill image or file. Two readers are **independent** when they differ in method (text layer, local OCR, vision model) or in model family (OpenAI, Anthropic), and neither is given the other's answer, the caller's `hints`, or a region found by the other. Regions given to a reader come only from the layout's anchors or from fixed page bands. `hints` are used only after reading, as a check: a mismatch adds a note, never a value.

| Reader | Method | Reads | Available from |
| --- | --- | --- | --- |
| `text_layer` | Words of a digital PDF, with character boxes (pypdfium2) | Anchored fields (Stage 4); label-rule values before that (5.3); table rows as line items (Stage 5) | Stage 1 |
| `local_ocr` | PaddleOCR words with boxes, read through the layout's anchors | Anchored fields; table rows as line items (Stage 5) | Stage 4 |
| `model_a` | Vision model, family A (default OpenAI), full bill into the core schema | Everything: guaranteed fields and every printed line | Stage 1 |
| `model_b` | Vision model, family B (default Anthropic), from an anchor crop or the page and its bands | Guaranteed fields; from Stage 5 also any printed line with an amount, when asked | Stage 1 |

**A text layer counts as a reader only when it is genuine.** A PDF whose text is invisible (render mode 3) or sits under a full-page image is a scan with an OCR layer; its text is then treated as `local_ocr`-grade input, never as `text_layer`.

Each guaranteed field carries its **evidence** (every reading, and the proof levels below) and one **verification** decided from it by the single rule in 5.2 (`unverified`, `verified`, `disputed`, `confirmed`). Proof levels are evidence, never a verdict:

| Proof level | Meaning |
| --- | --- |
| `exact` | Read from a genuine text layer inside the field's anchored region (from Stage 4, when anchors exist) |
| `consensus` | Two independent readers return the same normalised value (table below) |
| `arithmetic` | The field is an input or result of at least one passing **equality** check (G02–G09, G15, G17, the gas equality checks, and profile `rules` of severity error) whose declared `detects:` value can catch a one-digit change in the field's two leading significant digits. Each such check lists the paths it proves in `proves:`. Presence, range and date checks (G01, G10–G13, G18, G19) never give `arithmetic`. Extra assurance only: it never proves a field on its own |
| `confirmed` | Entered or confirmed from the page image by a named person: a Joulewise team member in the studio's review queue (Stage 3.10) or a user of the tenant on the web app's review page (Stage 7). Shown as "confirmed by <user>"; never counted as engine-verified in accuracy metrics |
| `single` | One reading only |

**Normalisation before comparing:**

| Field type | Normalised by | Not normalised (must match exactly) |
| --- | --- | --- |
| Number | removing digit grouping (Indian or Western), converting Devanagari numerals, removing trailing zeros after the decimal point | the digits, the sign, the decimal position |
| Date or month | parsing to ISO (`YYYY-MM-DD`, `YYYY-MM`), day first | the date itself |
| Identifier (account, meter, bill number) | removing spaces, hyphens and slashes; upper case | leading zeros and every other character |
| Text (names, categories) | collapsing spaces, upper case | the words |

**Arrays** (`readings[]`, `energy.tod[]`, `charges.by_code[]`, `elements[]`) are matched item by item on their key (register, slot, code, or label-as-printed plus position for elements), then compared field by field. An item one reader has and the other lacks is unverified.

### 5.2 The verification rule and the pass rule

**One function decides.** `billx/validate/proof.py` holds `decide(evidence) -> Verification`, the only implementation of the rule below. X01, the pass rule, exports, the studio, `billx eval`, the live view and the assistant all call it; no other code assigns a verification. The rule carries a version (`proof_rule_version` in every result) and changes only by a new version with a planted-misread test.

A field's **evidence** is its readings (reader, raw text, normalised value, page, region) and the proof levels they earned (`exact`, `consensus`, `arithmetic`, `confirmed`; 5.1). Its **verification** is what `decide` returns from that evidence:

| Evidence available | Verification |
| --- | --- |
| One reading only, from any reader | `unverified` |
| Two independent readers agree on the normalised value (`consensus`) | `verified` |
| A genuine text-layer reading inside the field's anchored region (`exact`), and for a number also an applicable passing equality check (`arithmetic`); for a non-number `exact` alone | `verified` |
| Readings exist but no two independent readings agree | `disputed` |
| A named person confirmed or typed the value from the page image (`confirmed`) | `confirmed` |
| The tariff engine's amount differs from the printed amount | no change: a billing-discrepancy warning (T01–T06) and insight I07; the transcribed amount is never altered |

**What `verified` means.** The acceptance rule above was met. It is not a guarantee: two models can share a misreading, and a genuine text layer can carry the discom's own typo. The rule makes a shared misreading unlikely by demanding different model families, no shared hints or regions, and (for numbers from a text layer) arithmetic that ties the value to others on the bill; how often it still happens is measured, never assumed, on held-out bills in Stage 11 and in production from day 14 (12.3). Users and callers see "verified", never "guaranteed" or "proven".

**X01 is this rule.** X01 holds for a bill when `decide` returns `verified` or `confirmed` for every required guaranteed field. It has no test of its own; an outvoted third reading is kept in `readers`, never a failure. For optional fields a `disputed` or `unverified` verification only affects that field.

**Every required number must sit in an equality check.** Otherwise an `exact` reading can never verify it and a digital PDF can never pass without a model call. Stage 4 lists every required number in contract 1.0's and 6.4's lists against the equality checks that cover it; any required number no check covers gets a check in that stage or, failing that, is listed in `pending-for-user.md` for a contract 1.2.

A bill **passes** only when all of these hold:
1. No check fails, except a check marked `printed_inconsistency` (below), and X01 holds.
2. Every required guaranteed field (section 6.4) is present and `verified`.
3. **Arithmetic covers the money and the energy:** `totals.net_payable` and the bill's energy field (`energy.kwh`, or `energy.kvah` under contract 1.1, 6.5) each take part in at least one passing check. Otherwise the reason is `insufficient_arithmetic`.
4. **No check skipped because of an unverified value.** Checks run on the fullest reading available (Model A's, or the template's when no model runs) with every verified value substituted in. If a check fails or skips because one of its inputs is not verified, the bill is `needs_review` with `unverified:<path>` or `disputed:<path>`.
5. Every other guaranteed field that carries a value is `verified`, or is handled as below.

**Printed inconsistency.** When a check fails and every value it uses is `verified`, the reading is accepted and the bill itself is wrong. The bill **passes**, with `printed_inconsistency:<id>` in `flags[]` (never in `review_reasons`), the check reported as failed in its checks list, and the finding raised as a billing-error insight (I07). In `esgos-1.0` mode the bill follows contract 1.0's own pass definition and carries the note `printed_inconsistency:<id>`; in `esgos-1.1` and `full` modes it carries the flag.

**Unverified or disputed optional fields** (rule 5):
- **`full` mode:** drop, don't guess. The value is returned as `null` with its evidence and verification intact and a reason `unverified:<path>` or `disputed:<path>`, and the bill may still pass on its required fields.
- **`esgos-1.0` mode:** contract 1.0 uses `null` to mean "not printed", so the engine never nulls a printed value there. Any guaranteed field that is not verified makes the bill `passed: false`, with `unverified: <path>` or `disputed: <path>` in `notes`.

**Confirmed values and acceptance** (hosted service only). On the web app's review page (Stage 7) a named user of the tenant, or in the studio's review queue (Stage 3.10) a named Joulewise team member, enters or confirms a value from the page image. It becomes a new record version with proof `confirmed` and verification `confirmed`. A bill whose required fields are all `verified` or `confirmed`, with at least one `confirmed`, gets status **`confirmed`**, never `passed`: `passed` is the engine's own verdict and keeps its contract meaning everywhere. Whether a caller may *use* the bill is a separate field: in `esgos-1.1` and `full` modes every bill carries **`accepted`** (true for `passed`; true for `confirmed` when the product's `accept_confirmed` is true, 6.6; false otherwise) and **`accepted_by`** (`engine` or `human`). esgOS adds a bill when `accepted` is true (6.5). Confirmed values are used in the tenant's own analytics, labelled, and never in accuracy metrics, benchmarks or leads.

**Bills that don't pass** still return every field as read, with its evidence and verification (`unverified` or `disputed`), so a person or product can review them.

Everything that doesn't pass is `needs_review` with machine-readable reasons (section 6.2).

### 5.3 The reading ladder

Per bill, cheapest and most private first. **Stage 4 onwards:**

1. **Text layer** (genuine only, 5.1). Anchored fields read from it are `exact`.
2. **Local OCR.** Anchors give reading 1 for each guaranteed field the text layer didn't give; from Stage 5, table extraction gives reading 1 for every printed line with an amount.
3. **Model A** reads the whole bill into `data` (all line items, meters, totals). Its guaranteed values, and from Stage 5 its line items, are reading 2.
4. **Compare** readings 1 and 2 per field and per line. Same normalised value: `consensus`.
5. **Disagreement, or no reading 1:** Model B reads the field (or the line) from its anchor crop, or from the band that holds it. If it matches either earlier reading, it is `consensus` with that value. If all readings differ, it is unverified.
6. **A failing check:** the lines it uses are re-read by Model B from their crops or bands, and go through step 5 again. Values change only through agreement, never by choosing the value that makes the arithmetic work.
7. **Budget.** Before each call, its worst-case cost is compared with what is left of `max_cost_usd`. If a needed reading can't be afforded, the bill ends `budget_exceeded`. It never passes on a single reading.

**Stages 1 to 3** (no anchors, no local OCR, so nothing can be `exact`):

1. **Model A** reads the whole bill.
2. **Text layer** (genuine digital PDFs and HTML only): a second reading by a fixed rule applied without any model value: the value token immediately right of, or below, the field's printed label, with label synonyms from the profile. Finding Model A's value among the words gives at most its page region, never a reading.
3. **Model B** reads a guaranteed field from the full page and its bands, independently, only where there is no text-layer reading (scans, photos) or where the text layer and Model A disagree.
4. A field is `consensus` when any two of these agree. When Model A and Model B disagree and the text layer doesn't settle it, the field is unverified. There is no further tie-break.

A scan or photo in Stages 1 to 3 therefore costs two model families; a genuine digital PDF usually costs one. esgOS has accepted OpenAI and Anthropic as configured providers (O17), so scans and photos pass from Stage 2 when Model A and Model B agree, and every call is in `usage` with its provider. A deployment with only one family configured passes digital PDFs and returns `model_not_allowed` for scans until Stage 4 (O20).

### 5.4 Checks

The three billx layers carry over: generic checks G01 to G14, per-discom rules, layout conformance S01 to S06. Every check declares `detects:` (rule 4). New and corrected:

| Id | Check | Tolerance | Applies when |
| --- | --- | --- | --- |
| G15 | TOD slot units add up to the total register of the **same quantity** (kWh with kWh, kVAh with kVAh) | max(1, 0.006 × MF × number of slots) | the profile marks the slots as covering the whole day (`tod_complete: true`) |
| G16 | gross kVAh ≥ gross kWh | max(1, 0.006 × MF) | both printed, and no export or net metering on the bill |
| G17 | import − export = net units billed | max(1, 0.006 × MF) | net metering is printed |
| G18 | bill month lies in the reading period, or within the profile's `bill_month_offset` months after it (default 0 to 1) | — | always |
| G19 | period start is before period end | — | always |
| G20 | a negative amount or quantity is printed with a minus or credit marker, or sits on a line the layout marks `signed: true` (net units after open-access banking, rebates, credits) | — | always |
| X01 | `decide` (5.2) returns `verified` or `confirmed` for every **required** guaranteed field: two independent readings agree, or a genuine anchored text-layer reading with (for a number) an applicable equality check. No separate logic; an outvoted third reading is recorded in `readers`, not a failure. For other fields a disagreement only makes that field `disputed` | the rule in 5.2 | always |
| X02 | every guaranteed field on a passed bill has a page region | — | from Stage 4; warning |
| T01–T05 | printed rates, demand charge, duty and cess, PF incentive or penalty, minimum charge equal the tariff order's | per formula | verified inputs only, else `skip`; **warnings**, never failures |
| T06 | every other element the tariff engine computes (FPPCA, open-access charges, rebates, surcharges) equals the amount billed | `TARIFF_DIFF_MIN_INR` | verified billed amount only, else `skip`; **warning** |

**Wrong as printed** is handled by the printed-inconsistency rule in 5.2: verified inputs, failed equation, bill passes with a flag and an I07 insight.

### 5.5 The formula recheck and the tariff engine

Every bill goes through two independent rechecks, both done by code, after validation:

1. **Formula recheck (the bill against itself).** Every element that prints a quantity and a rate is recomputed (G05 and the discom rules): energy per TOD slot, demand, duty on its printed base, rebates and surcharges at their printed percentages.
2. **Tariff-order recheck (the bill against the regulator).** The **tariff engine** computes every element again from the tariff order alone, using only the bill's verified quantities (units per slot, recorded and contract demand, PF, load factor, days, voltage) and the order's parameters for that state, category and month. It then compares each computed element with what was billed.

**What the tariff engine knows**, encoded as cited data:
- **Components:** energy charge (flat, slab or TOD), demand or fixed charge (billing-demand rules such as max(recorded MD, x% of CD), rounding), excess-demand penalty, minimum charges, PF incentive and penalty bands, load-factor and voltage rebates, TOD rebate and surcharge, fuel and power-purchase cost adjustment (FPPCA, FPPA, FAC, FSA, VCA), electricity duty on its state-specific base, cess, open-access charges (cross-subsidy and additional surcharge, wheeling, transmission, banking), net-metering credit, prompt-payment rebate, and the order's rounding rules.
- **Sources with dates:** the tariff order, and the notices that change between orders, such as the monthly or quarterly FPPCA rate and duty notifications. Each parameter cites its source (regulator or discom, number, date, page or table) and carries `effective_from` and `effective_to`.
- **Categories:** each version maps the printed tariff code to the order's category. HT and LT commercial and industrial first; domestic and agricultural on request.
- **State level:** one order covers all of a state's discoms, so it lives in `profiles/_states/<state>/`, and discom versions `extend` it.

**What it records, per element:** the amount computed from the order, the amount billed, the difference, a status (`match`, `differs`, `not_computable` with a reason such as `missing_notice` or `unknown_category`), and the citations used. All of it is stored in the bill record.

**Only against verified values.** A comparison runs only when the element's billed amount is verified (5.7); otherwise its status is `not_computable` with reason `unverified_billed`. The quantities it uses must be verified too, or the status is `not_computable` with `unverified_quantity`.

**How it affects the bill:** differences are tariff warnings (T01–T06): they never fail a bill, because a bill can be read perfectly and still be billed wrongly. A difference above `TARIFF_DIFF_MIN_INR` (default ₹1) becomes a billing-error insight (I07). A missing notice is listed in `pending-for-user.md` so the team can add it.

**Coverage:** per layout, the share of non-zero current-charge elements the tariff engine can compute, reported in `billx eval`. Elements it can't compute are listed in the version as `unformulated`.

### 5.6 Refusals

The engine refuses rather than guesses:
- **`unreadable`:** a page fails the quality gate (Stage 4): blur, glare over text, character height, cut-off edges. The note says what to retake.
- **`not_a_bill`:** no page classified as a bill.
- **Required field not printed:** for example a bill priced only in kVAh that prints no kWh. The reason is `required_field_not_printed`; under contract 1.1 (6.5) such a bill passes on `energy.kvah`.

### 5.7 Every element captured

- **One catalogue of codes** in `profiles/_common.yaml`, versioned: `energy_charge` (per TOD slot), `demand_charge`, `fixed_charge`, `excess_demand_penalty`, `minimum_charge_difference`, `fppca` (also FPPA, FAC, FSA, VCA), `electricity_duty`, `cess`, `tod_rebate`, `tod_surcharge`, `pf_incentive`, `pf_penalty`, `load_factor_rebate`, `voltage_rebate`, `prompt_payment_rebate`, `digital_payment_rebate`, `other_rebate`, `subsidy`, `regulatory_surcharge`, `cross_subsidy_surcharge`, `additional_surcharge`, `wheeling_charge`, `transmission_charge`, `open_access_banking`, `green_tariff_premium`, `net_metering_credit`, `meter_rent`, `transformer_rent`, `late_payment_surcharge`, `arrears`, `security_deposit_interest`, `tds`, `tcs`, `rounding`, `other`.
- **Every printed line with an amount** becomes a charge element: label as printed, group, kind, stage, quantity, rate, unit, amount, TOD slot and times where printed, common code, proof, formula-recheck result and tariff-recheck result.
- **Nothing printed is missed.** The section and bill totals (G06, G07, G09) must reconcile, so a bill whose captured elements don't add up to what it prints can't pass. On a finalised layout, a line coded `other` or outside the template (S03) opens a profile task.
- **An element is verified** only when two independent readers agree on its amount (`consensus`: the local table row or text-layer row against Model A, with Model B on disagreement, 5.3), or it is `exact` and also `arithmetic`. A passing formula recheck or section reconciliation adds `arithmetic`; it never proves an element on its own, because a model that writes a consistent but wrong quantity, rate and amount would pass it. Unverified elements are stored, marked `single`, and left out of analytics, insights and the assistant unless the user includes them, labelled.

## 6. The API

### 6.1 One codebase, three API modes, two storage modes

The engine owns its API from now on; esgOS is its first consumer. Two independent settings:

- **`BILLX_API_MODE=esgos-1.0`**: exactly contract 1.0. No additions appear in responses and no extra calls answer. A request option outside 1.0 is refused with 400 `bad_request` (contract section 8, malformed options), so a product never believes an addition took effect. No insights, leads, audits, comparisons or assistant run in this mode. Section 6.1a fixes its intake behaviour.
- **`BILLX_API_MODE=esgos-1.1`**: contract 1.0 plus contract 1.1 (section 6.5), which esgOS has accepted: optional fields only, `passed` keeps 1.0's meaning, every 1.0 call and shape unchanged. The embedded image ships in this mode by default (`esgos-1.0` by configuration), and the `esgos` product key gets it on the hosted service. Insights run when the key's defaults say so; contact leads per 6.6; no savings leads for esgOS.
- **`BILLX_API_MODE=full`** (the hosted Public Bill API, the web app, the MCP connector, other Joulewise products): the engine's own API under `/v1`, with 1.0's calls and shapes plus 6.2 and 6.3. It is **not** a 1.x-compatible version: it requires a tenant that accepted the terms, changes what `DELETE` does, and nulls unverified optional fields.
- **`BILLX_STORAGE=ephemeral`** (24-hour deletion, no bill database) or **`permanent`** (section 9A). The embedded image is always `ephemeral`; the hosted service runs `permanent` and serves **all three API modes, chosen per product key** (section 6.6), so an application that speaks contract 1.0 or 1.1 can call the hosted service unchanged. No other combination ships.

Contract 1.1 is written in `contract/esgos-1.1/` in Stage 2 and served from the start; there is no proposal step.

### 6.1a Intake in `esgos-1.0` and `esgos-1.1` modes

| Input | Result |
| --- | --- |
| A media type outside contract 4.2 (HTML, XLSX, CSV, ZIP, BMP) | 415 `unsupported_type` |
| A password-protected PDF (1.0 has no password option) | `passed: false`, `route: "none"`, `unread_reason: "unreadable"`, note `password_required` |
| A gas bill before the gas reader exists (Stage 2b) | `unread_reason: "unreadable"`, note `gas_not_yet_supported`; never `not_a_bill`. From Stage 2b, read as gas under the contract |
| Water, telecom, other invoices, non-bills | `not_a_bill` |
| A file mixing bills and other pages | the bills in `bills[]`; the other pages omitted, their page numbers in the first bill's `notes` |
| `kind: "text"` | the document-type gate doesn't run; pages, text and words as contract section 5.3 (built in Stage 2.1, with a contract example) |
| `allow_cloud_model: false` and a guaranteed field that only a model could prove | `passed: false`, `route: "none"`, `unread_reason: "model_not_allowed"`, as contract section 7 says |
| A printed inconsistency (5.2) | contract 1.0's own pass definition; note `printed_inconsistency:<id>` in 1.0, the flag in 1.1 |
| Any layout, verified or not | passes when the 5.2 rules hold (`accept_unverified_layouts` is true for esgOS); `profile.status` says the layout's state |
| Email, batches, events, any `full`-mode call | not served |

### 6.2 Additions to existing calls

**`POST /v1/jobs` options** (all optional):

| Field | Type | Meaning |
| --- | --- | --- |
| `callback_url` | https URL | POSTed the job result (or a link to it) when the job ends |
| `outputs` | list of `json`, `csv`, `pdf` | Clean copies to prepare (section 8); default `["json"]` |
| `insights` | boolean, default false | Run the savings and billing-error scan (section 9) |
| `share_insights_with_joulewise` | boolean, default false | The user's consent for Joulewise to contact them about savings findings. Without it no savings lead is created; the contact lead (9.3) does not depend on it |
| `contact` | object: `name`, `email`, `phone`, `company` | The uploading user. Stored with the job and shared with Joulewise as a contact lead (9.3). A product with `contact_leads: true` sends it on every job; the web app fills it from the signed-in user |
| `account_ref` | string | The user's own label for the account or site, stored with the record |
| `pdf_password` | string | For password-protected e-bills; used once, never stored or logged |

In `full` mode a job from a tenant that has not accepted the terms (9A.1) is refused with 422 `terms_not_accepted`.

**Each bill** gains:

| Field | Meaning |
| --- | --- |
| `status` | `passed`, `confirmed` (passed only after a person confirmed its remaining fields in the studio's review queue or the web app's review page, 5.2), `needs_review`, `unreadable`, `not_a_bill`, `wrong_document_type`, `model_not_allowed` or `budget_exceeded`; consistent with 1.0's `passed` and `unread_reason` |
| `review_reasons[]` | codes: `check_failed:<id>`, `unverified:<path>`, `disputed:<path>`, `insufficient_arithmetic`, `required_field_not_printed:<path>`, `layout_drift`, `unknown_utility`, `unverified_layout`, `out_of_range_version`, `password_required`, `unsupported_format_profile`, `source_conflict` |
| `flags[]` | codes on a passed bill that don't stop it passing: `printed_inconsistency:<id>` (5.2) |
| `accepted`, `accepted_by` | whether the caller may use the bill, and by whose verdict: `engine` (passed) or `human` (confirmed, where the product accepts it; 5.2, 6.6) |
| `proof_rule_version` | the version of the verification rule that decided this result (5.2) |
| `routes_used[]` | every route that produced a returned value |
| `insights[]` | when requested (section 9) |
| `clean` | links to the clean copies (section 8) |
| `document_type` | from the document-type gate (5.0) |
| `profile` | `id`, `version` and `status`: `verified`, `draft` or `none` (section 2). Present in `esgos-1.1` and `full` modes |
| `audit_status` | `not_audited` (no tariff audit: before Stage 5b, or no order for this state, category or month), `audited` (every computable element compared), `partially_audited` (some elements `not_computable`); with `audit_version` and the order citations used. A downstream financial or ESG report labels its figures with this and with `profile.status` |
| `bill_record_id` | the permanent record this bill was stored as (section 9A) |
| `elements[]` | every charge element with its code, proof, formula recheck and tariff recheck (5.5, 5.7) |
| `tariff_recheck` | per-element order-computed amount, billed amount, difference, status and citations (5.5) |

**Each field object** gains `verification` (the decision, 5.2), `proof` (the proof levels it earned, 5.1), `readers` (which readers agreed, for example `["text_layer", "model_a"]`) and, when asked with `include_evidence`, every reading with its page and region. Values themselves never appear in the reasons or notes.

**Resolved ambiguities in 1.0** (apply in both modes):
- **`route`** is the most expensive route that produced a returned value: `cloud_model` over `local_model` over `template`. It is always `none` for `model_not_allowed`, `budget_exceeded`, `unreadable` and `not_a_bill` (contract 1.0, section 7).
- **`source`**: a value read through the layout's anchors, from the text layer or local OCR, is `template`; local OCR or text-layer words without anchors are `ocr`; a model reading is `model`. When several readers agree, `source` is the first of `template`, `ocr`, `model` among them. The exact readers are in `readers`.
- **`schema_version`** reports the engine's real core schema version (2.0 after Stage 1). Contract 1.0's example shows "1.0"; this is listed for esgOS in `pending-for-user.md`.
- **Retention.** `esgos-1.0` mode: files and results are deleted within 24 hours, exactly as contract 1.0 requires; esgOS keeps its own copy. `full` mode: every file and result becomes a permanent bill record (section 9A); resubmitting the same file within the same tenant returns the existing record.
- **`DELETE /v1/jobs/{job_id}` in `full` mode** removes the job's queue entry and working files only. The bill record stays, as the accepted terms say. Erasure of a record is a separate, logged command (9A.5).

### 6.3 New calls (`full` mode only)

| Call | Purpose |
| --- | --- |
| `POST /v1/batches` | Many files, or one zip, in one request; returns a batch id and one job per file |
| `GET /v1/batches/{batch_id}` | Batch progress and its job ids |
| `GET /v1/jobs/{job_id}/bills/{index}/clean.{json,csv,pdf}` | Clean copies for MIS (section 8) |
| `GET /v1/utilities` | Supported discoms and states, their versions, status, and accuracy: `unmeasured` until Stage 11, then held-out silent-error figures with sample sizes |
| `GET /v1/usage` | The tenant's bills, pages and model cost for a date range (cost recording only; there is no quota) |
| `POST /v1/consent/withdraw` | Withdraws a consent for a contact within the calling tenant: savings leads deleted, contact lead marked `do_not_contact` (9.3); withdrawing the storage consent queues erasure (9A.5) |
| `GET /v1/jobs/{job_id}/events` | Server-sent events of the reading as it happens: every stage, reading, region, check, recheck and element (section 9D.2). Replayable after the job ends |
| `GET /v1/bills`, `GET /v1/bills/{bill_record_id}` | The tenant's permanent bill records, filtered by account, utility, period, status |
| `GET /v1/bills/{bill_record_id}/versions` | Every version of a record, with what changed and why |
| `GET /v1/accounts`, `GET /v1/accounts/{account_id}/series` | Accounts and their monthly series of any element or metric (section 9A.3) |
| `POST /v1/exports` | JSON, CSV, Excel or Parquet for any selection of bills, accounts, periods and elements (section 9A.3) |
| `POST /v1/assistant/ask` | A question about the tenant's bills; the answer with its citations and tool trace (section 9C) |

### 6.4 Guaranteed fields

Contract 1.0's electricity and gas lists are the floor and keep their required flags in every mode, except that from contract 1.1 `energy.kwh` **or** `energy.kvah` is required rather than `energy.kwh` alone. In `full` and `esgos-1.1` modes these are added as optional fields, each verified like any other guaranteed field:

| Path | Unit |
| --- | --- |
| `consumer.name` | |
| `period.due_date` | date |
| `totals.current_charges`, `totals.arrears` | INR |
| `charges.by_code[]`: `code`, `amount` | INR |
| `tariff.category` (the order's category, mapped from the printed code) | |
| `open_access.re_kwh`, `open_access.non_re_kwh`, `open_access.banked_kwh` (units printed for the period, for esgOS's BRSR renewable split) | kWh |
| `green_tariff.kwh` (units billed under a green tariff for the period) | kWh |

### 6.5 Contract 1.1, accepted by esgOS

Contract 1.1 is written in `contract/esgos-1.1/` (contract text, OpenAPI, examples) in Stage 2 and served on the `esgos` key from Stage 3 and in the embedded image as `BILLX_API_MODE=esgos-1.1`. It contains exactly:

1. The additions of 6.2 that keep 1.0's behaviour, as optional fields: `verification`, `proof`, `readers`, `status`, `review_reasons`, `flags` (with `printed_inconsistency`), `routes_used`, `document_type`, `profile`, `audit_status`, `elements[]`, `tariff_recheck` (every element `not_computable: tariff_engine_pending` until Stage 5b), `bill_record_id`, `proof_rule_version`, `accepted`, `accepted_by`, and `insights[]` when asked.
2. The added guaranteed fields of 6.4, as optional: `consumer.name`, `period.due_date`, `totals.current_charges`, `totals.arrears`, `charges.by_code[]`, `tariff.category`, `open_access.re_kwh`, `open_access.non_re_kwh`, `open_access.banked_kwh`, `green_tariff.kwh`.
3. `energy.kwh` **or** `energy.kvah` required, so bills priced only in kVAh can pass.
4. The resolved ambiguities of 6.2.
5. Optional request options on `POST /v1/jobs`: `contact` (name, email, company, phone: the uploading user, which becomes a contact lead, 9.3), `account_ref`, `insights`, `pdf_password` and `wait`. A 1.0 request without them behaves exactly as before.
6. **`passed` keeps 1.0's meaning.** It is the engine's own verdict and is never set by a person.
7. **`accepted` is what esgOS consumes.** esgOS adds a bill when `accepted` is true: every `passed` bill (with or without flags), and every `confirmed` bill, since the `esgos` product has `accept_confirmed: true`. This is the one follow-up to the esgOS change list of 11 Oct 2026, whose item 6 said "status is passed": without it a bill a Joulewise reviewer corrects in the studio (3.10) would never reach esgOS. It is listed in `pending-for-user.md` for esgOS's build agent; until esgOS reads `accepted`, confirmed bills reach it only when it re-fetches them and its own rule allows.

Not in 1.1, because they change 1.0's behaviour and belong to the `full` API only: terms acceptance, permanent storage, the `full`-mode `DELETE`, and nulling unverified fields. Two providers (O17) and the data-residency option (`model_region`) are deployment matters, recorded in `docs/contract-1.1.md`, not contract fields.

### 6.6 Serving other applications

billx is a serving application: any application that holds bills its users uploaded sends them to billx and gets back the values it needs. esgOS is the first; every later Joulewise product, and any partner application, is onboarded the same way. The application never runs billx's code; it calls the hosted service with one key.

**The product registry**, `config/products.yaml`, one entry per calling application:

| Field | Meaning |
| --- | --- |
| `product` | id, for example `esgos` |
| `tenant` | the tenant its calls run under (its users are that tenant's users; the tenant accepted the terms, 9A.1) |
| `contract` | `esgos-1.0`, `esgos-1.1` or `full`: the API mode this key gets on the hosted service. The mode is a property of the key, not of the server |
| `fields` | a named field set: the paths this product needs, each with `required: true/false`. `esgos` is contract 1.0's guaranteed list; a product may name any guaranteed field or element code in 6.4 and 5.7 |
| `store` | `permanent` (default: the product's users agreed to storage) or `ephemeral` (the 24-hour rule, for a product that keeps its own copy and wants nothing kept) |
| `defaults` | `allow_cloud_model`, `max_cost_usd`, `insights`, `callback_url` |
| `accept_unverified_layouts` | whether a bill from a layout that hasn't met its launch gate can pass (12.4); true for `esgos` |
| `accept_confirmed` | whether a human-confirmed bill (status `confirmed`) is returned with `accepted: true` (5.2); default true, including `esgos` |
| `contact_leads` | every sign-up and upload becomes a contact lead for Joulewise (9.3); default true, including `esgos` |
| `savings_leads` | billx creates insight-based savings leads for this product (9.3); false for `esgos`, whose own lead engine reads the insights from the result |

**The call.** `POST /v1/jobs` (or `POST /v1/read`, a synchronous alias) with the file and, optionally, `wait: true` (the response holds the bill when it finishes within 50 seconds, otherwise the `job_id`) and `fields: [...]` to narrow the response to a subset of the product's field set. The response is the bill object of section 6 in the product's contract mode, filtered to its field set: every value with its unit, `proof` and `readers`, plus `status`, `review_reasons` and `flags`. A product's `required: true` field that isn't verified makes the bill `needs_review` with `unverified:<path>` or `disputed:<path>`, so the calling application never has to judge a value itself; it reads `accepted`. Everything else (insights, elements, the tariff recheck, the stored record) is available to the product on the same key when it asks.

**Clients.** `clients/python/billx_client` and `clients/typescript/billx-client`, generated from `contract/openapi.json` with a thin hand-written layer: `read_bill(file, fields=..., wait=True)`, `get_bill(job_id)`, `explain(job_id, index)`, `insights(job_id, index)`. Published to the private package registry on every release tag.

**esgOS.** The agent is given read access to `git@github.com:Ergplan/esgOS.git` on day 1 to read how esgOS submits bills and which values it consumes, so the `esgos` field set is exact and nothing esgOS reads is missing. Its registry entry: `contract: esgos-1.1`, `store: permanent`, `insights: true`, `accept_unverified_layouts: true`, `accept_confirmed: true`, `contact_leads: true`, `savings_leads: false`; esgOS sends `contact` (name, email, company) with every job; its tenant accepted the terms at key issue, which covers its users (9A.1). Until the hosted service is live, esgOS runs the embedded image from its own registry; the switch is a URL and token change made by esgOS's own build agent. **billx never creates branches in `Ergplan/esgOS`.** esgOS keeps every bill file and resubmits them all once to the hosted service, so resubmission must de-duplicate (5.0) and the first hosted release is tested with a resubmission run.

**Any later application** is onboarded by adding a registry entry and a field set; no engine change. The web app's upload, the MCP `read_bill` tool and email-in are themselves products in the registry, so every channel is served the same way.

## 7. The MCP connector

A remote MCP server so Joulewise clients can use the engine from Claude, ChatGPT and other LLM apps. It is a thin adapter over the `full` API: same tenants, keys, proofs and limits. **The LLM never computes anything about a bill:** every number, explanation and saving comes from the engine's code.

- **Where:** `billx/mcp/`, built on the official MCP Python SDK, served over Streamable HTTP at `/mcp` beside the API. It targets the MCP specification current at build time; the agent records the version in `decisions.md`.
- **Auth:** the tenant's API key in the `Authorization` header. The tenant's terms acceptance (9A.1) covers every user of the connection. OAuth 2.1 as the MCP authorization specification describes comes before listing in public connector directories (Stage 12).

**Tools**

| Tool | Input | Output |
| --- | --- | --- |
| `read_bill` | `file` (base64 and file name) or `file_url` (https); `contact` (the user's name, email, company, for the contact lead), `insights`, `allow_cloud_model`, `max_cost_usd`, `account_ref`, `pdf_password` | Waits up to 50 seconds with progress notifications. Returns the bill's `status`, utility, period, guaranteed fields with unit and proof, `review_reasons` and `flags`; or the `job_id` if still running |
| `get_bill_result` | `job_id`, optional `include_data` | Same as above; `data` (every printed line) only when asked |
| `explain_bill` | `job_id`, `bill_index` | Each charge with its common code, the formula and parameters behind it and the tariff order cited. Generated from the formula library, never by a model |
| `find_savings` | `job_id`, `bill_index` | The insights (section 9) with estimate ranges and assumptions, and an offer of a Joulewise consultation |
| `request_contact` | `job_id`, `contact`, `consent: true` | Creates a savings lead (section 9.3); only with explicit consent |
| `compare_bills` | `job_ids[]` of one account | Month-on-month units, demand, PF, cost per kWh and changed charges, from verified values only |
| `list_supported_utilities` | optional `state` | Discoms, versions and accuracy (`unmeasured`, or held-out figures with sample sizes) |
| `ask_my_bills` | a question, optional account or period | The assistant's answer with citations (section 9C) |
| `get_series` | account, element or metric, period | A monthly series from the database, as JSON |
| `export_bills` | a selection and a format | A download link for JSON, CSV, Excel or Parquet |

**Resources:** `billx://utilities`, `billx://insights/catalogue`, `billx://data-dictionary`. **Prompts:** "Explain my electricity bill", "Audit my bill for savings".

**Tool descriptions must tell the calling model:** values are transcribed from the bill and marked `verified` under a documented rule (two independent readings agree, or PDF text tied to the bill's arithmetic), which is an acceptance rule, not a guarantee; present them as returned; never recompute; when `accepted` is false, show the reasons and do not present unverified or disputed values; when `flags` names a printed inconsistency, say the bill itself is inconsistent. Tool results stay compact; full `data` only on request.

## 8. Clean copies for MIS

Clients keep a clean, identical-shape copy of every bill in their own systems.

- **JSON:** the bill result (section 6) with every charge element, and JSON built on demand from the database for any selection of accounts, periods and elements (section 9A.3).
- **CSV:** `bills.csv`, one row per bill with a fixed column set (identity, period, guaranteed fields, amounts by common code, status, flags, proof summary), and `line_items.csv`, one row per printed line (`bill_key`, index, group, label as printed, common code, kind, stage, quantity, rate, unit, amount). **The same columns for every discom**, with empty cells where a bill doesn't print a value. Column sets carry `csv_schema_version` and are documented in `docs/data-dictionary.md`.
- **PDF bill card:** one A4 page per bill: utility, consumer, account, period, key figures marked as verified, charges by common code, checks summary, flags, and insights when requested. Generated by code. Its footer says it was prepared from the original bill, which prevails.
- **Keys for de-duplication:** `bill_key` = file sha256 + bill index; `natural_key` = utility id + account + bill month + bill number. An MIS can upsert on either.
- **Delivery:** download links (in `esgos-1.0` mode only until its 24-hour deletion; in `full` mode at any time, built from the permanent record), the `callback_url` webhook, and batch export as one zip with all CSV rows combined.
- **Only passed bills** produce CSV and PDF copies by default. `include_unverified: true` adds others, each row and page marked "not verified" with its reasons.

## 9. Insights and leads

### 9.1 Rules

- Insights are computed by code from **verified values** and **cited tariff parameters** only, after validation. They never appear on a bill that didn't pass (a bill flagged `printed_inconsistency` has passed, so I07 may appear on it), and never change a value (invariant 8).
- Every insight gives an **annual estimate as a range** (low, high) in INR with its assumptions listed, a confidence (`high`, `medium`, `low`), the evidence paths it used, and the number of bills it is based on.
- Estimates are labelled as estimates, not advice. Assumptions such as the shiftable share of peak load are configuration values with stated defaults.
- The printed 12-month history on many bills (AVVNL prints it) is used only where each history value the insight uses is verified by two readers; otherwise the insight uses the account's stored verified bills, or says it is based on one bill.

### 9.2 Catalogue (first version)

| Id | Finding | Triggered when | Estimate | Leads to |
| --- | --- | --- | --- | --- |
| I01 | Power-factor penalty, or incentive below the maximum | PF line or PF band from the formula library | penalty paid + incentive forgone, per month × 12 | Capacitor or APFC panel |
| I02 | Contract demand set too high | Billing demand set by the minimum-billable floor because recorded MD is lower | (billing demand − recorded MD) × demand rate × 12 | CD reduction application |
| I03 | Excess-demand penalty | Recorded MD above CD, penalty line present | penalty × months it recurs | CD revision or peak shaving |
| I04 | Peak-hour share high | TOD slots priced above off-peak carry more than the configured share of units | shiftable units × (peak − off-peak rate) | Load shifting, storage |
| I05 | Load-factor rebate missed or near its threshold | Formula library has LF bands | rebate forgone | Operations change |
| I06 | Late-payment surcharge or interest paid | LPS line non-zero | amount × frequency | Payment process |
| I07 | Billing error | A tariff check (T01–T06) difference on verified values, or a `printed_inconsistency` flag | the difference, per bill | Billing dispute support |
| I08 | High landed cost per unit | Net payable ÷ units above the state benchmark for the category | annual spend × configured saving share | Open access, rooftop solar, captive |
| I09 | Security-deposit interest not credited | The order mandates annual interest and none appears in the expected month | interest due | Refund claim |
| I10 | Arrears or deferred amounts outstanding | Arrear or deferred lines non-zero | amount | Account reconciliation |

### 9.3 Leads

Two kinds, both delivered to Joulewise through the `leads` table, a POST to `LEADS_WEBHOOK_URL` (the CRM) and, until that webhook exists or when it fails, a daily email to `LEADS_EMAIL` listing the day's new and updated leads; the studio shows the leads table and exports it as CSV. No email or call goes to the user automatically.

**Contact leads: every sign-up, every upload.**
- A contact lead is created when a user signs up (web app) and when a bill is uploaded through any channel of any product (API, MCP, email, the web app), for every product with `contact_leads: true` (6.6), which is the default and includes `esgos`. The terms accepted at sign-up say so (9A.1).
- **It holds:** name, email, company, phone where given, product, tenant, channel, the account label and utility of the upload, the number of bills so far, the terms version, and the time. One lead per person per product; later uploads update it (bill count, utilities) rather than duplicating it.
- A product sends `contact` on every job; the web app fills it from the signed-in user. A job without a usable name and email still runs, and its lead is flagged `contact_missing` so the team can chase the product.
- No bill values travel with it beyond the utility and account label.

**Savings leads: a worthwhile finding, with consent.**
- Created on the hosted service for products with `savings_leads: true` when **the user consented** (`share_insights_with_joulewise: true`, or `request_contact` over MCP) **and** the insights' combined low estimate is at least `LEAD_MIN_SAVING_INR` (default ₹1,00,000 a year).
- The `esgos` product has `savings_leads: false`: esgOS's own lead engine owns savings leads (one per company) and reads `insights[]` from the result. Its contact leads still flow to Joulewise.
- **It holds:** the contact lead it extends, utility, state, tariff category, contract demand band, insight ids with estimate ranges, the job id, the consent text version and timestamp. It does not hold the bill file or values beyond those summaries.

**Withdrawal.** `POST /v1/consent/withdraw` with the contact's email, within the calling tenant, deletes their savings leads and marks their contact lead `do_not_contact` (an operational change, not a bill-record deletion); withdrawing the storage consent queues erasure (9A.5), which removes the contact lead too. Consent and terms text are versioned in `config/consent.yaml` and `config/terms/`. The team confirms the wording with counsel before launch (Stage 12).

### 9.4 Intelligence

All computed by code from verified values, per account and month, stored in the bill database and shown in the web app, the assistant and the monthly digest:

- **Anomalies:** units outside the account's seasonal band (same month last year and the trailing three-month median; thresholds in `config/intelligence.yaml`); PF falling below its band; recorded MD approaching or exceeding CD; a charge element appearing for the first time; a tariff or FPPCA rate change; arrears appearing; unusual billing days.
- **Forecasts:** units and cost for the next 3 to 12 months by a documented seasonal baseline method, priced by the tariff engine with the parameters known today (the last known FPPCA rate carried forward). Always shown as ranges and labelled as estimates.
- **Benchmarks:** cost per kWh, PF, load factor and TOD share against peers of the same state and category, only from tenants whose sign-up consent includes anonymised benchmarking (9A.1), and only when at least 10 accounts are in the group.
- **Digest:** a monthly summary per account (what changed, anomalies, insights, tariff-recheck differences) by email or webhook, as the user chooses.

## 9A. The bill database

### 9A.1 Terms and consent

- One terms text in `config/terms/`, versioned so the team can revise it; the current version is the one in force. It states that bills and every value read from them are stored permanently, what they are used for, that the user's name, email and company are shared with Joulewise as a lead on sign-up and on every upload (9.3), that Joulewise may use a stored bill to check and improve reading quality (the golden set and audits), that anonymised figures may appear in benchmarks, and which cloud providers process them (the two model providers, the assistant's chat model, and LlamaParse where the tenant allows it).
- **Acceptance is once, at sign-up.** A web-app user accepts when they create their account. For the API and MCP, the tenant accepts once when its key is issued, and attests that it covers its own users. Each acceptance records who, tenant, terms version, channel and time. A new terms version is shown to users at their next sign-in; it does not block storage.
- **One optional consent at job level:** contact by Joulewise about savings findings (savings leads, 9.3), given per job or through `request_contact`, withdrawable through `POST /v1/consent/withdraw`. Named use in Joulewise studies (9A.4) is asked for separately when it arises.
- Email senders who aren't registered users get a reply saying to sign up; nothing they sent is stored.

### 9A.2 Data model (Postgres, append-only)

| Table | Holds |
| --- | --- |
| `tenants`, `users`, `consents`, `leads` | who, what each person agreed to, and the contact and savings leads (9.3) |
| `accounts` | utility, account number, site label, category, contract demand |
| `files` | sha256, storage location, media type, pages, channel, received time, document type |
| `bill_records` | one per real-world bill: account, utility, bill month, bill number, the natural key, its source files |
| `record_versions` | every version of a record: reason (`initial`, `re_read`, `correction`, `profile_change`), engine, profile, schema and model versions, status, review reasons, flags |
| `field_values` | per version: path, value (exact `NUMERIC` or text), unit, proof, readers, page, region |
| `elements` | per version: every charge element (5.7), with formula recheck and tariff recheck |
| `meter_readings`, `checks`, `tariff_rechecks`, `insights`, `anomalies` | per version, as produced |
| `events` | the full event stream of every reading (9D.2), for replay and audit |
| `comparisons` | Docling and LlamaParse outputs and their match results (9B) |
| `corrections`, `feedback` | every correction, by whom, from what to what |
| `assistant_turns` | questions, answers, citations and tool traces (9C) |

- **Append-only by design:** the application only inserts into record tables; the current state of a bill is a view over its latest version. Enforcement by database grants, and the test that proves it, arrive in Stage 11.
- **Every query carries the tenant:** one data-access layer adds `tenant_id` to every read and write; no query reaches the database without it. Row-level security in the database is Stage 12 work.
- **Money and quantities are `NUMERIC`,** never floating point.
- **Files** live in object storage with versioning on and no lifecycle deletion.

### 9A.3 Getting data out for analysis

- **Views:** `current_bills`, `current_elements`, `account_monthly` (billing periods split into calendar months in proportion to days, labelled as derived), `tariff_parameters`, `tariff_differences` (the last two from Stage 5). Each bill view has a **verified-only** form (`verified_bills`, `verified_elements`, `verified_account_monthly`) holding only verified values; analytics, insights, intelligence and the assistant use these by default, and `confirmed` values only where labelled.
- **JSON on demand:** a bill, an account over any period, or a comparison across accounts and months, each with a published JSON Schema in `docs/data-model.md`, generated from the Pydantic models of the core schema (Stage 1.1), so analysts can build financial models and planning studies on a stable shape.
- **Exports:** JSON, CSV, Excel and Parquet through `POST /v1/exports`, the web app and MCP.
- **Series API:** any element or metric for an account by month.
- **BI access:** a read-only database role for the Joulewise team; per-tenant BI access is Stage 12 work.

### 9A.4 Joulewise's own analysis across tenants

- **The tariff database** (orders, notices, parameters by state and year) contains no client data and is freely usable for planning studies.
- **Across tenants:** anonymised aggregates only, with at least 10 accounts per group (the sign-up terms cover this); named data only with a named-use consent asked for at the time.

### 9A.5 Erasure: the only deletion of a bill record

Nothing in a bill record is deleted in normal operation. Deleting operational rows (leads when consent is withdrawn, job-queue entries, working files, non-bill files after 5.0's period) is not record deletion.

India's DPDP Act gives people the right to withdraw consent and to erasure, so one logged command exists: `billx erase` for a user, account or record, run by an authorised person with a reason.
- **Triggers:** an erasure request, or withdrawal of the storage consent, which stops new storage at once and queues erasure of that person's records.
- **What it removes,** for each affected record: the files and every noncurrent object version; its rows in `field_values`, `elements`, `meter_readings`, `checks`, `tariff_rechecks`, `insights`, `anomalies`, `events`, `comparisons`, `corrections`, `feedback` and `assistant_turns`; the pgvector embeddings of its pages; any golden-set copy; and personal fields in `accounts` and `users`.
- **What it keeps:** an anonymous tombstone (ids, utility, month) and aggregate statistics already computed, and the erasure itself in `erasure_log` (who, when, why, never the values).
- **Test (Stage 11):** erase a synthetic user, then search every table, store and index for their values and find none.

Counsel confirms the terms and this command before launch (Stage 12).

### 9A.6 Re-reading and re-auditing

- **Re-read** (Engine 1): when a reader or profile version improves reading for a discom, an authorised person can re-read its stored bills. Each re-read creates a new record version (`re_read`) beside the old one, with a report of what changed; nothing is re-read automatically, and nothing earlier is lost.
- **Re-audit** (Engine 2): when a tariff order, notice or formula changes, every stored bill of that state, category and period is audited again from its stored record, without touching the file or the readings. Each run creates a new version (`re_audit`) carrying only the new `tariff_recheck`, `audit_status` and `audit_version`; values and verifications are copied unchanged. Re-audit runs automatically on a tariff-data merge for the sample and golden sets, and on request for tenants' bills.

## 9B. The comparison lab: Docling and LlamaParse

- **Purpose:** compare what general document parsers get from the same bills with the engine's verified result, to choose tools on evidence and to show clients the difference. **They are never readers that prove a value** (rule 15). Built in Stage 9; off the verification path.
- **Readers:** Docling (version pinned, OCR on, table structure on) and LlamaParse (current API version, `do_not_cache` on, region and tier from configuration, cost per page recorded).
- **Where they run:** the comparison worker, its own image, never the engine image.
- **When:** Docling on every sample and golden-set bill in `billx eval`; LlamaParse on those the golden manifest marks `comparison_cloud_ok`. In production on a sample (default 10% of bills plus every bill that needs review). LlamaParse sends files to LlamaIndex's cloud, so it runs on a production bill only when the job allowed cloud models **and** the tenant's `allow_comparison_cloud` is true (default false). Docling runs locally and needs no such permission.
- **Measures, per reader, discom and input kind:**
  - **value recall:** the share of verified guaranteed fields and elements whose exact printed value appears in the reader's output;
  - **table fidelity:** the share of verified line items found as a row with label and amount together;
  - **cost and time** per page.
- **View:** a comparison screen for the team only, served under `/internal/` with a team key and never to tenants or through MCP, with the page image, Docling's output and LlamaParse's output side by side, verified values highlighted where found and flagged where missing or different.

## 9C. The assistant (built on Haystack)

Users ask about their bills in plain language: trends, comparisons, anomalies, why a charge rose, what a tariff change costs. **The model plans and writes; code computes.**

- **Framework:** Haystack 2.x, its `Agent` component with tools (version pinned and recorded in `decisions.md`); OpenAI as the default chat model, Claude as the alternative through Haystack's Anthropic integration; Postgres with pgvector as the document store for retrieval.
- **What leaves the service:** embeddings of bill pages are computed locally by a pinned open embedding model. The cloud chat model receives the question and tool results only, never files or page images, and runs only when the tenant's `allow_assistant_cloud` is true (default true; the terms name the provider). With it false, the assistant is off for that tenant.
- **Tools** (all code, read-only, scoped to the user's tenant by the data-access layer of 9A.2):

| Tool | Does |
| --- | --- |
| `query_bills` | a **structured query**, not free SQL: accounts, periods, elements or metrics, a grouping (month, account, element) and an aggregate (sum, average, min, max, count), run over the documented verified-only views (9A.3) with a row limit; unverified or confirmed values only with `include_unverified`, and then labelled in the answer; returns rows, each with its bill record and month, and the query as run |
| `get_series` | an element or metric for an account by month |
| `compare` | two periods, accounts or sites on chosen metrics |
| `explain_charge` | an element's formula, its tariff recheck and the order cited |
| `tariff_lookup` | the parameters in force for a state, category and month |
| `insights`, `anomalies`, `forecast` | from section 9 and 9.4 |
| `search_documents` | retrieval over tariff orders, notices and the user's bill pages, with page citations. Bill-page text helps find and quote context; a number from it is never cited as a bill value |
| `make_chart` | a chart specification the web app draws from a tool's rows |

- **Answer contract:** text, citations (bill records, months, tariff order pages), the tool trace, and optional table and chart.
- **Numbers are references, not typed text.** The agent writes each figure as a reference to a tool result (`{tool_call_id, row, column}`); code renders it in Indian format with the row's bill record and month beside it. Derived figures (a change, a share, an average) come from the `compare`, `get_series`, `query_bills` or `forecast` tools, never from the model's arithmetic. The verifier rejects any other digits in the prose except dates and counts a tool returned. A rejected answer is revised once; if it fails again, the figure is removed and the answer says so.
- **Verified data only** by default; when an answer depends on bills still in review, it says so.
- **Out of scope:** questions not about the user's bills, tariffs or energy get a short refusal.
- **Evaluation (Stage 11):** at least 100 golden questions on synthetic tenant data, with expected answers. Gates: every expected number correct, every number a tool reference cited to the right bill and month, correct refusals.
- **Where:** the web app's chat, `POST /v1/assistant/ask`, and the MCP tool `ask_my_bills`. Conversations are stored in `assistant_turns`, never in logs.

## 9D. The user web app

### 9D.1 Pages

Sign-up with name, email and company (which becomes a contact lead, 9.3); sign in; upload (drag and drop, phone camera capture, the tenant's email-in address); the live reading view; bill view; **review** (for a bill that needs review: the page image, each reader's value and the reasons; the user enters or confirms a value, which becomes a new record version with proof `confirmed`, 5.2); accounts and analytics; the assistant; exports; settings (saved PDF passwords, lead consent, digest). Indian number formatting (lakh, crore) and units throughout.

**Analytics** per account and across accounts: units and cost by month, cost per kWh, TOD share, PF, recorded MD against CD, the mix of charge elements over time, FPPCA and duty trends, tariff-recheck differences, anomalies, forecasts and benchmarks.

### 9D.2 The live reading view: watch the bill being read

The user sees their bill read, checked and rechecked as it happens, so they can trust the result.

- **Look:** futuristic, but precise rather than decorative. A dark, high-contrast instrument-panel style (a light theme too), the page image at the centre-left, and a ledger on the right that fills as values are verified.
- **What appears, in the order it really happens:**
  1. **Intake and document type:** the file's pages; the verdict of the document-type gate. If it isn't an electricity bill, the view ends here with a plain message saying what it appears to be.
  2. **Page preparation:** a photo straightens and crops on screen; the quality gate shows what it measured.
  3. **Utility and layout:** the discom's name highlighted where it was found on the page; the layout version chosen.
  4. **Reading:** progress moves only on real events (page started and finished, reader started and finished); while a model is reading, an indeterminate indicator, never a fake sweep. A field's region appears when it is known: as a local reader finds it through anchors, and for model readings on `region.aligned` after the reading (Stage 4; page bands before). Chips name the configured readers (text layer, local OCR, "Model A: <provider>", "Model B: <provider>") and light up as they report; a proof badge appears when two agree.
  5. **Formula cards:** every check shown as its equation with the bill's real numbers substituted, for example `4,042.40 × 6,666.67 = 2,69,49,346.81 kWh ✓ printed 2,69,49,346.81`. Failures are explained in plain words; a printed inconsistency is shown as "the bill's own numbers don't add up". An input that isn't verified yet is styled "unverified", and the ✓ means only that the equation holds.
  6. **Tariff recheck:** for each element, the amount computed from the order beside the amount billed, the difference, and a citation chip that opens the order's page.
  7. **Charge waterfall:** the elements building up to the net payable.
  8. **Verdict:** Passed (every key value verified; with its flags if any), Needs review (the reasons in plain words), or Not an electricity bill.
- **Truthfulness rules:**
  - Every animated step is driven by a real event from `GET /v1/jobs/{job_id}/events`. No invented progress, boxes or timings.
  - Before regions exist (Stages 1 to 3), the view highlights page bands, labelled as such, never fake boxes.
  - Every stored bill can be replayed from its events.
- **Event stream:** `stage.started` and `stage.finished` per stage, `page.started`, `page.finished`, `reader.started`, `reader.finished`, `document.type`, `region.found`, `region.aligned`, `reading`, `field.verified`, `check.result` (with the formula template and its inputs), `tariff.element`, `element.captured`, `verdict`. Events go only to the bill's owner, are stored in `events`, and never reach logs.
- **Accessibility:** a reduced-motion mode, a text "reading log" with the whole sequence, keyboard use, and phone layouts.

### 9D.3 Technology

React with TypeScript (Vite), an SVG overlay on the page image for regions, an animation library for the transitions, and a charting library for analytics; served by the API service and talking to it over the API and server-sent events. The development studio (section 9 of the earlier guide) stays a separate team tool. Playwright end-to-end tests on synthetic bills, in both themes and at phone width, including a test that every animated step maps to a stored event, are written in Stage 11.

## 10. Tenants and deployment

### 10.1 Tenants

- **Tenant:** id, name, API keys (stored hashed), allowed products, terms acceptance (9A.1), default `allow_cloud_model` and `max_cost_usd`, `accept_unverified_layouts` (default false, section 12.4), `allow_comparison_cloud` (default false, section 9B) and `allow_assistant_cloud` (default true, section 9C).
- **Users:** belong to a tenant; sign in to the web app; accept the terms at sign-up.
- **No plans, quotas or invoicing.** The product is free. Every job still records bills, pages, route, model calls and cost, so the team can see what each tenant costs; `GET /v1/usage` reports it. A `max_cost_usd` default per tenant is the only spending limit.
- Joulewise's own products that call the hosted API are tenants too. esgOS's embedded image is not a tenant and stores nothing beyond 24 hours.

### 10.2 Two deployment modes, one codebase

| | Embedded (inside esgOS) | Hosted (Public API and MCP) |
| --- | --- | --- |
| API mode | `esgos-1.1` (`esgos-1.0` by configuration) | per product key: `esgos-1.1` for esgOS, `full` for everyone else |
| Storage mode | `ephemeral` | `permanent` |
| Job store | SQLite under `/data` | Postgres |
| Files | local `/data`, deleted within 24 hours (contract 1.0) | MinIO in Docker, versioning on, never lifecycle-deleted, mirrored nightly; S3-compatible so a cloud bucket replaces it under O22 with no code change |
| Bill database | none: esgOS stores its own copy | Postgres, append-only (9A.2), with pgvector for the assistant |
| Queue | in-process, bounded | Postgres queue (`SELECT … FOR UPDATE SKIP LOCKED`), no extra broker |
| Services | one container, 4 jobs at once, under 2 GB of memory where possible (esgOS's machine has 8 GB shared with its app, database, ClamAV and Arelle); the figure stated in every release note | API, workers, Postgres, MinIO in the sprint; comparison worker, assistant service and web app added in Stage 9 |
| Where it runs | esgOS's own servers, pulling the image by digest from esgOS's registry | Docker on the Mac mini behind a Cloudflare Tunnel, staging and production as two compose projects; a cloud VM under O22 |

`JobStore`, `FileStore` and `Queue` are interfaces with these two implementations each; the tests run against both.

### 10.3 Models

- Model A defaults to OpenAI (`BILLX_MODEL_A=openai:<model id>`), Model B to Anthropic (`BILLX_MODEL_B=anthropic:<model id>`). Model ids, prices (`config/prices.yaml`) and regions are configuration; `doctor.sh` calls each once (3.1).
- Stage 1 chooses the pair by measurement: fewest silent errors on the tuning set, then coverage, then cost. The choice and its numbers go in `decisions.md`.

### 10.4 Folder layout

```text
billx/
  core/          the shared data contract: schema (Pydantic v2, Decimal, strict; version 2.0),
                 Value and Reading, migrations, units
  reader/        ENGINE 1
    ingest/      render and text layer, photo correction, quality gate, page sorting, tiles
    ocr/         paddle (local reader), tesseract (crop reader), tables (row extraction)
    identify/    utility detection, version selection, document-type gate
    read/        ladder, template (anchors), model readers, consensus, align (regions)
    providers/   openai, anthropic; the only code importing a model SDK; usage and cost
    prompts/     versioned prompt files
    validate/    generic (G-series), gas (GG-series), rules, conformance (S-series),
                 readings, proof.py (decide), formula recheck of the bill against itself
    normalize/   common codes, guaranteed fields, field maps
  auditor/       ENGINE 2: tariff engine (formulas), state orders and notices loader,
                 element comparison, citations, re_audit; imports core only, never reader
  intelligence/  ENGINE 3: insights, anomalies, forecasts, benchmarks, digest, leads,
                 assistant (Haystack agent, tools, document store, number verifier);
                 reads verified-only views; imports core only
  platform/      what serves the engines
    warehouse/   database schema and migrations, the tenant data-access layer, views,
                 JSON builders and schemas, exports, series
    api/         FastAPI app: /v1 calls, modes, products, keys, cost recording, webhooks
    mcp/         MCP server and tools
    store/       JobStore, FileStore, Queue: sqlite/local and postgres/object-storage
    channels/    email-in
    exports/     clean JSON, CSV, PDF bill card, data dictionary
    studio/      confirmation mode, review queue, spot check, leads view
    evals/       sample and golden-set runner, metrics, reports, production audit sampling
    synth/       synthetic bills, and synthetic non-electricity documents for the type gate
    compare/     Docling and LlamaParse runners and matching (comparison worker only)
  cli.py
web/           the user web app (React, TypeScript)
clients/       python/billx_client and typescript/billx-client, generated from openapi.json
profiles/      _common.yaml, _states/<state>/ (tariff formulas), _template/, one folder per discom
config/        prices.yaml, quality.yaml, insights.yaml, intelligence.yaml, consent.yaml, terms/
contract/      openapi.json (generated, checked), esgos-1.0/ (contract 1.0 word for word),
               esgos-1.1/ (contract text, openapi.json), examples/ (synthetic, per mode)
tests/         unit/ (the builder's, every stage); api/, mcp/, contract/, formulas/, e2e/,
               independent/stage-N/ (Stage 11); synthetic data only
tools/         review/ (reviewer, Stage 11), watch/ (watcher), mac/ (doctor, session, launchd job),
               identifiers.py (client-identifier search)
docker/        engine (all modes), comparison worker, assistant, web; compose.yaml,
               compose.hosted.yaml (API, workers, Postgres, MinIO, tunnel)
docs/          build-prompt.md, architecture.md, decisions.md, known-gaps.md, runbook.md,
               pending-for-user.md, api.md, mcp.md, insights.md, data-dictionary.md,
               data-model.md, assistant.md, comparison.md, web.md,
               contract-1.1.md, onboarding.md, esgos-changes-2026-10-11.md, week-3.md,
               accuracy/, stage-reports/, reviews/
```

No `utils/`, `misc/`, `helpers/`, `temp/` or `old/`. A new folder goes into `architecture.md` before it holds code.

An import-boundary test (Stage 0.3) fails if `reader/` imports `auditor/` or `intelligence/`, if `auditor/` imports `reader/` or `intelligence/`, or if `intelligence/` imports either; all three import `core/` only and are called by `platform/`. Paths elsewhere in this file (`billx/validate/proof.py`, `billx/providers/`, `billx/prompts/`, `billx/formulas`, `billx/mcp/`) are read under this layout: `billx/reader/validate/proof.py`, `billx/reader/providers/`, `billx/reader/prompts/`, `billx/auditor/formulas/`, `billx/platform/mcp/`.

## 11. Security: three items now, the rest before public launch

The product is free and users agree to permanent storage at sign-up, so security is not a priority for this build. Three things are kept because they are cheap and protect Joulewise's clients and lead business:

1. **No real bills in git, CI logs, the image, or any request to the reviewer** (Stage 0): the client-identifier search and gitleaks in the watcher and CI.
2. **Tenant filter on every query** (Stage 3): the data-access layer of 9A.2. A client must never see another client's bills.
3. **No bill values in logs, metrics, traces or errors** (Stage 2), and a logged `billx erase` command (Stage 3), because DPDP consent withdrawal is a legal right whatever the terms say.

Everything else is listed in `known-gaps.md` and built in **Stage 12**: row-level security and separate database roles (app, read-only, eraser), append-only enforced by grants, HMAC-signed webhooks, KMS-encrypted saved passwords, SPF/DKIM checks on email-in, OAuth 2.1 for MCP, rate limiting, WAF, container and dependency scanning gates, penetration test, audit logs, customer-managed encryption, SOC 2 or ISO 27001, data-processing agreement templates, per-tenant BI access.

API keys are stored hashed and compared in constant time because it is one line of code, not because it is a priority. FileVault stays on because the Mac holds the bills and, until O22, the production database.

## 12. Measurement and the golden set

### 12.1 The sample set during the build, the golden set in Stage 11

**During the build (Stages 0 to 10):** the team confirms **10 bills per layout** in the studio (the sample set): ideally 6 digital PDFs, 2 scans, 2 phone photos. All 10 are tuning data: the builder may open them, fix prompts and profiles against them, and run `billx eval` on them for information. Nothing is held out and no accuracy gate exists; the stage reports state the sample's numbers and label them `unmeasured`. A new discom in Stage 10 needs 10 confirmed bills to be served, and is served as soon as its profile reads them.

**In Stage 11:** the full golden set is built and the accuracy work is done, in this order.

1. Real bills go into `~/billx-data/golden/` on the Mac, mirrored to the external drive, never git: at least 30 per layout, so the held-out half has at least 15, including at least 3 phone photos and 3 scans in each half; 60 per layout where the team can manage it, which brings the bound to 10% (section 2). The sample set joins the tuning half.
2. **Pre-fill by two readers** (from Stage 1): Model A and Model B each read the bill, and the checks run on both readings. In Stage 0 the pre-fill is one model's reading.
3. **A person confirms every guaranteed field and every charge element's amount** in the studio. Where both readings agree and the arithmetic passes, it is one click; where they differ, the person types the value from the image. Pre-fill only speeds up confirmation; nothing enters the golden set unconfirmed.
4. The studio records seconds per bill, so the team can plan hand-checking from real numbers.
5. Each layout's bills are split by a fixed random seed into **tuning** and **held-out** halves. The builder may open tuning bills in the studio to fix errors; for held-out bills it sees only metrics and the paths of wrong fields, never images or values.
6. **The held-out set stays clean.** A held-out bill whose wrong-field paths drove a prompt, profile or formula change moves to the tuning half and is replaced by the next confirmed bill of that layout; the move is logged in the golden manifest. The held-out *n* in every report counts only bills never used this way.

### 12.2 What `billx eval` reports

Per discom, layout, input kind (digital PDF, scan, photo) and route, always with sample sizes:
- **silent errors**, with the rule-of-three upper bound;
- **coverage**, **correct refusals** and **false refusals**;
- **accuracy over attempted**, per guaranteed field;
- **formula coverage** (section 5.5);
- **cost per bill** and **time per bill**, median and 95th percentile.

During the build, `billx eval` is run by hand on the sample set at the end of Stages 1, 4, 5 and each Stage 10 state, and its aggregate report (no values or names) goes in the stage report, labelled `unmeasured` because the sample is tuning data. The nightly launchd job at 02:00 IST (mirror the golden set to the external drive, run `billx eval`, open a pull request adding `docs/accuracy/<date>.md`) starts in Stage 11. From then, any silent error marks the report red and is an incident (12.3).

### 12.3 Production monitoring (from day 14, the first hosted production)

In hosted mode only. Inside esgOS (embedded mode) bills never leave esgOS's stack and are deleted within 24 hours, so monitoring there relies on esgOS's `POST /v1/feedback` alone. This is the only accuracy loop that exists between the first production bill and Stage 11, so it starts with production, not with Stage 11.

- **Feedback** from products (`POST /v1/feedback`) and corrections made in the studio's review queue or on the web app's review page are counted per discom, version, field, route and model, from day 14.
- **Spot check, daily from day 14:** the studio's review queue has a second tab listing a random sample of *passed* bills (default 5 a day per discom, at least 5 in all); a person compares each against its page image in the same screen and marks it right or wrong per field. Five minutes a day; it is the only measurement of silent errors on real production bills until Stage 11, and its results are shown on the studio's front page beside the review-queue count.
- **Any silent error found is an incident:** the bill joins the sample set (and the golden set from Stage 11; the terms allow quality use, 9A.1; a bill since erased is replaced by a synthetic reproduction), a regression test is added, the profile or reader is fixed in the next session, every stored bill of that layout is re-read (9A.6), and the incident goes in `docs/accuracy/incidents.md`. The weekly rate per discom goes in `GET /v1/utilities` as `production_errors_found` beside `unmeasured`.

### 12.4 Gates

- **Launch gate per discom** (checked in Stage 11): 0 silent errors and 0 false refusals on its held-out set, at least 15 held-out bills per layout (O3 may raise it), and every guaranteed field's formula coverage reported.
- **Unmeasured layouts, during the build:** every layout is served, with `profile.status` `draft` or `none`, `accuracy: unmeasured` in `GET /v1/utilities` and `proof` on every value. Calling applications are told this in `docs/onboarding.md`.
- **Unverified layouts, from Stage 11:** a discom or layout that hasn't met its launch gate returns `needs_review` with `unverified_layout`, unless the tenant has `accept_unverified_layouts: true`; the flag is true for the `esgos` key and for the embedded image by configuration (esgOS change 4): a bill from any discom passes for esgOS when the 5.2 rules hold, and `profile.status` tells it the layout's state. It defaults to true for every other tenant registered before Stage 11 so nothing that worked stops working, and to false for new ones.

### 12.5 Comparisons, the assistant and document types (Stage 11)

- **Comparison readers** are reported beside the engine in every `billx eval` run: value recall, table fidelity, cost and time per page, per discom and input kind (9B).
- **The assistant** has its own golden questions on synthetic tenant data. Gates: every expected number correct, every number a tool reference cited to the right bill and month, correct refusals (9C).
- **Document types,** both ways: non-electricity documents refused (a synthetic set, and every real one the team adds), and **false refusals** of electricity bills over every golden-set bill, gated at 0 on the held-out set.

## 13. Stages

esgOS is the first customer and goes live within days, so the build has two parts. **Sprint 1** (13.1) is 14 days in three parallel builder sessions and ships only what a calling application needs: the 0.x embedded image in the first week, the hosted service with the `esgos` key in the second. **The roadmap** (13.3) is everything else, in the 4.1 order, after that. Stage numbers are kept from 4.1, with Stage 2b added, so the esgOS change list's references hold. Through Stage 10 the only tests are the builder's unit tests and the hand-run `billx eval` on the sample set; everything else is Stage 11.

### 13.1 Sprint 1: 14 days, three sessions

**What is delivered, and what counts as delivered.** The 14-day objective stands; what is tightened is the acceptance requirement for each period. A period is not done until its requirement holds, and the next period's work does not count as progress against it.

| Period | Deliverable | Acceptance requirement |
| --- | --- | --- |
| Days 1–4 | Engine 1's core: schema with Value and evidence, Model A reader, Model B verification, `decide`, the document-type gate, the three contract adapters | The builder's extraction tests on synthetic bills and the contract tests for all three modes pass; the import-boundary test passes |
| Days 5–7 | The embedded esgOS service (`billx:0.1`, then `0.2` with generic gas where ready): every file contract 4.2 allows, scans and photos on two-provider consensus, `profile.status` and `audit_status` on every bill, the image in esgOS's registry | Tested on the real, confirmed sample bills: every sample bill reads end to end, and every sample value a person marked critical (below) is `verified` or the bill is `needs_review` with the right reason |
| Days 8–10 | Hosted staging: Postgres, MinIO, the evidence stored per value, the review workflow (studio queue and spot check), leads, elements with codes, the `esgos` key | Tenant-isolation test (two tenants, every call), no-values-in-logs test, and a restore test (stop, restore the night's mirror into a fresh compose project, replay a stored bill) pass; a `needs_review` bill is confirmed from the queue and returns `accepted: true` |
| Days 11–13 | End-to-end esgOS integration against staging with real sample bills; resubmission de-duplication; accuracy evaluation | `billx eval` on the full sample set; a person reviews every critical field of every sample bill in the studio; **no known unresolved critical error**; the 1.1 field set checked against what esgOS reads |
| Day 14 | **Controlled esgOS production pilot**: the production compose project promoted, the `esgos` key issued, limited to the supported layouts | **Explicit sign-off**, recorded in `docs/stage-reports/sprint-1.md`: the supported layouts (AVVNL, PVVNL; every other layout served as `draft` or `none`), the operations runbook (start, stop, restore, review queue, spot check, who is on call), and the release notes' description of the service |

**Critical fields** (the acceptance bar for days 5–13): `utility`, `account`, `period`, `energy.kwh` or `energy.kvah`, `demand.recorded` and `demand.contract` where printed, `totals.current_charges`, `totals.net_payable`, and for gas `volume.scm` and `totals.amount`. A critical error is a critical field `verified` with the wrong value, or a bill `passed` with a critical field missing.

**What the day-14 release says about itself**, in its release notes, `docs/onboarding.md` and `GET /v1/utilities`: a bill-reading and basic-insights service; verification is an acceptance rule, not a guarantee; accuracy is `unmeasured` until Stage 11 with the daily spot-check figure shown; the tariff-order audit is not yet available (`audit_status: not_audited` on every bill until Stage 5b); layouts other than the supported ones are `draft` or `none` and a downstream financial or ESG report must label figures from them as from an unverified layout.

**Sprint scope by stage**

| Stage | In Sprint 1 | After the sprint |
| --- | --- | --- |
| 0 | all | — |
| 1 | 1.1 to 1.6 (code); 1.7 and 1.8 as the sample bills arrive | — |
| 2 | all, including contract 1.1 served and the 0.x releases | — |
| 2b | generic gas reading | supplier profiles and sample sets (10.4) |
| 3 | 3.1 to 3.6, 3.8, 3.9 (early hosting) and 3.10 (the studio's review queue for hosted `needs_review` bills); 3.7 limited to clean JSON, `bills.csv`, `line_items.csv`, the views and the webhook | Excel and Parquet exports, the PDF bill card, the series API, JSON Schemas |
| 4 | — | all; meanwhile scans and photos cost two cloud calls and nothing is `exact` |
| 5 | 5a: 5.1, 5.2, 5.3 and 5.7 (every element captured and coded, formula recheck) | 5b: 5.4 to 5.6, the tariff engine; until then `tariff_recheck` reports every element `not_computable` with reason `tariff_engine_pending` |
| 6 | 6a: I01, I02, I03, I04, I06, I10; contact leads for every upload through the API (esgOS from day 14) with the daily lead email; savings leads for products with `savings_leads: true` | 6b: I05, I07, I08, I09; intelligence (9.4). Web sign-up leads arrive with the web app (Stage 7) |
| 7, 8, 9 | — | all (9.4 is the onboarding document, not a branch in esgOS) |
| 10 | — | all |
| 11, 12 | — | all |

**Day plan**

| Days | Session A: engine | Session B: platform | Session C: product |
| --- | --- | --- | --- |
| 1 | Stage 0.0 to 0.3: Mac tools, repo safety, build loop | Stage 0.4 synthetic bills; then 2.1, the API skeleton in all three modes | Reads `Ergplan/esgOS`; writes the `esgos` registry entry and field set; drafts `contract/esgos-1.1/` from 6.5 |
| 2 to 4 | Stage 1.1 to 1.6 | Stage 2.2 to 2.4: embedded store, intake, metrics, logs | Stage 2.6 contract 1.1 and examples; 0.5 studio confirmation mode; 3.8 clients |
| 5 | Stage 1.7 `billx eval`; **2.5 and 2.7: `billx:0.1` released** | Stage 3.1 to 3.3: full mode, database, terms, erase | Stage 2b: gas |
| 6 to 7 | Stage 1.8 on the 10 + 10 sample bills as they arrive; the days 5–7 acceptance check | Stage 3.4 to 3.6: the rest of intake, events, elements in results | Stage 2b done; **`billx:0.2` released** |
| 8 to 9 | Stage 5a: table rows, element catalogue, formula recheck | Stage 3.7 (sprint subset) and **3.9: hosting on staging** | Stage 3.10 review queue in the studio; then Stage 6a: insights, `esgos` defaults, leads |
| 10 | 5a done; `billx eval` on the sample set | **Staging live with the `esgos` key**; the days 8–10 acceptance tests (isolation, logs, restore) | 6a done; `docs/onboarding.md` |
| 11 to 13 | **Freeze.** All three sessions: esgOS end to end against staging with real sample bills; resubmission de-duplication; the 1.1 field set checked against what esgOS reads; `billx eval` on the sample set and a person's review of every critical field; bugs only, critical errors first. Anything that isn't a bug goes to `docs/week-3.md` | | |
| 14 | **Controlled production pilot** after sign-off: production promoted for the supported layouts, the `esgos` key issued, `GET /v1/utilities` reporting every layout's `profile.status` and `audit_status`; sprint report with pace lines; tag `1.0-reader` | | |

**Sprint rules**

- The freeze on days 11 to 13 is not optional. It is where the integration bugs go.
- Nothing is added mid-sprint. Ideas go to `docs/week-3.md`.
- A session that finishes its track early takes the next item on the critical path (0 → 1.1–1.6 → 2 → 3 → 3.9), never a roadmap item.
- Pull requests are merged the same day; autonomous mode from day 4 (O9).
- No `pending-for-user.md` item blocks: every open question has a default in section 15, and the sample bills are the only input work waits on, for at most a day.

### 13.2 Dependencies

A stage may start when these are merged (rule 1); stages with the same prerequisites run in parallel sessions.

| Stage | Needs | Can run beside |
| --- | --- | --- |
| 1 (code, 1.1–1.6) | 0 | 2.1 |
| 1 (live, 1.7–1.8) | 1 code, the sample bills | anything |
| 2 | 1.1–1.6, 2.1 | 3, 2b |
| 2b | 2 | 3, 4 |
| 3 | 1.1–1.6, 2.1 | 2, 2b, 4 |
| 3.9 (hosting) | 3.1–3.3 | 3.4–3.8 |
| 4 | 1 | 2, 3 |
| 5a | 3 | 6a (from 5.3) |
| 5b | 5a | 6b, 7 |
| 6a | 5a | 7 |
| 6b | 5b | 7, 8 |
| 7 | 3 | 5, 6, 8 |
| 8 | 3, 5a | 6, 7, 9 |
| 9 | 3, 7, 8 | 10 |
| 10 | 5a for profiles; 5b for tariff coverage | 6 to 9, and itself state by state |
| 11 | everything above | — |
| 12 | 11 | — |

Sprint critical path: 0 → 1.1–1.6 → 2 → 3 → 3.9 → freeze. Roadmap critical path: 4 → 5b → 10 → 11 → 12.

### 13.3 Stage definitions

#### Stage 0 — Safe repository, build loop, synthetic bills, confirmation tooling

```text
STAGE 0. Make the repository safe and set up the loop. Reading behaviour doesn't change.
0.0 The Mac (section 3.1): tools/mac/doctor.sh (including one call to each configured
    model id and a check that the external drive is mounted), tools/mac/session.sh N,
    the Claude Code allow-list, cloudflared installed with the tunnel token, the
    nightly mirror job (golden set and MinIO data to the external drive) written and
    active, the nightly evaluation job written but inactive until Stage 11, and the
    PaddleOCR check on all three platforms with the RapidOCR fallback if needed.
0.1 Move tests/samples, real fixtures, examples/ and docs screenshots to
    ~/billx-data/golden/ (never git). Replace screenshots with synthetic ones. Add the
    client-identifier search (identifiers held in a CI secret and in ~/billx-data,
    never in the repo) and gitleaks to CI.
0.2 Move modules into the section 10.4 layout without changing behaviour.
0.3 tools/watch writes .status/checks.json (ruff, pytest, the CLAUDE.md and AGENTS.md
    copy check, the identifier search, the engine import-boundary test of 10.4). CI runs the same on GitHub Actions, builds the
    linux/amd64 and linux/arm64 images and pushes them to ghcr.io; a release tag also
    pushes to esgOS's registry with ESGOS_REGISTRY_KEY. mypy strict is Stage 11 work.
0.4 billx synth: synthetic bills with known values for the AVVNL and PVVNL layouts, as
    digital PDFs, scans and photo-like variants (rotation, perspective, blur, glare, low
    resolution), plus synthetic gas, water and telecom bills, receipts and letters for
    the document-type gate. Rebuild every existing test on synthetic bills; all green.
0.5 Studio confirmation mode: pre-fill from today's extraction (one model), confirm or
    type each guaranteed field, seconds per bill recorded, references written to the
    golden manifest. The tuning/held-out split by seed exists but every bill is tuning
    until Stage 11. Two-reader pre-fill is added in Stage 1.2.
0.6 Save Part A of "billx Developer Guide: super billx" (version 2) as
    docs/developer-guide.md: normative for G01-G14, S01-S06, GG01-GG05, T01-T05, profile
    rules and param(), and the studio. Save Part C word for word as
    contract/esgos-1.0/contract.md.
0.7 docs/decisions.md opens with "esgOS changes (11 Oct 2026, from Joulewise)", one
    entry per item of the change list, each pointing at the section that carries it.
Done when: doctor.sh passes on the Mac; no real bill in the tree; the builder's tests
green natively and in CI; both images build and land on ghcr.io; PaddleOCR (or the
recorded fallback) reads a synthetic bill on all three platforms; the studio confirms a
synthetic bill end to end. STOP.
```

#### Stage 1 — The verification core

```text
STAGE 1. Make a passed bill mean every guaranteed value is verified under one rule. Items 1.1 to 1.6 are
code and gate Stage 2; 1.7 and 1.8 complete when the sample bills arrive.
1.1 Core schema 2.0 as Pydantic v2 models (billx/core/schema.py): Decimal fields for
    every amount, quantity and rate, strict mode (no float or string coercion into a
    Decimal), Literal enums for codes and statuses, frozen models for results; a
    migration from 1.x. Value and evidence are separate: every guaranteed field and
    element amount is a Value[T] holding value, unit, readings (each a Reading:
    reader, method, model id and prompt version or None, raw text, normalised value,
    page, region, cost), proof levels, the ids of the equality checks it took part
    in, page, region, verification and proof_rule_version. A Value's verification is
    set only by decide() (1.3); a model validator recomputes it from the evidence and
    rejects a mismatch, so no code path can mark a value verified by hand. The same
    models are the FastAPI request and response types, so contract/openapi.json, the
    JSON Schemas in docs/data-model.md and the generated clients all come from them
    and can never drift from the code. The one no-float test (rule 7) walks every
    model.
1.2 Readers (section 5.1): text_layer (pypdfium2 words with boxes, genuine layers only,
    reading by the fixed label rule of 5.3, never by looking up a model value), model_a
    (OpenAI, full bill), model_b (Anthropic, guaranteed fields from page and bands,
    never shown model_a's values or hints). Normalisation and array matching (5.1),
    consensus, proof levels on every field. Two-reader pre-fill in the studio.
1.3 decide() in billx/validate/proof.py, the only implementation of the verification
    rule (5.2), versioned; the pass rule on top of it: status, review_reasons
    (unverified:, disputed:), flags, insufficient_arithmetic, the printed-
    inconsistency pass with its flag, drop-don't-guess in full mode and passed:false
    in esgos-1.0 mode for fields that are not verified; accepted and accepted_by;
    profile.status on every bill (6.2). A test asserts that no module other than
    proof.py assigns a verification.
1.4 Checks G15 to G20 as in 5.4, X01 as a call to decide() for every required field,
    the proves: list on every equality check, and a detects: declaration on every
    check (rule 4).
1.5 The Stage 1-3 reading ladder (text layer second, Model B only where needed), two
    providers for scans and photos (O17), and the worst-case budget check (5.3).
1.6 The document-type gate (5.0) and page sorting: classify pages, split a file into
    bills, not_a_bill and wrong_document_type, on the synthetic non-electricity set.
    Scans and photos without a text layer are classified by Model A when cloud use is
    allowed, otherwise model_not_allowed. Gas bills route to the gas reader once Stage
    2b exists; before that, gas_not_yet_supported.
1.7 billx eval with every metric in 12.2 and the rule-of-three bound (the held-out
    hygiene rule of 12.1 takes effect in Stage 11).
1.8 Live: run the AVVNL and PVVNL sample sets (10 bills each, from the team); choose
    the model pair by silent errors on the sample, then coverage, then cost; fix only
    what the sample shows. No tuning beyond that; Stage 11 does the rest.
Done (code) when: 1.1 to 1.6 pass the builder's tests on synthetic bills; Stage 2 may
start. Done (live) when: the engine reads every sample bill end to end and billx eval
reports the sample's numbers (labelled unmeasured) with coverage, cost and time per
input kind; the document-type gate refuses no sample bill. STOP.
```

#### Stage 2 — The esgOS image: contracts 1.0 and 1.1, intake, the 0.x releases

```text
STAGE 2. The engine esgOS runs within days: contract 1.0 exactly, contract 1.1 on top,
taking in any bill contract 4.2 allows, released as 0.x and pushed to esgOS's registry.
2.1 FastAPI /v1 in esgos-1.0, esgos-1.1 and full modes: one bearer token (BILLX_TOKEN)
    in the embedded modes, the intake table of 6.1a, kind "text" (contract section
    5.3), the resolved ambiguities of 6.2, and BILLX_API_MODE / BILLX_STORAGE with the
    check that only the shipped combinations start.
2.2 The embedded store: SQLite job store under /data, local files, the 24-hour sweeper,
    the in-process bounded queue, 4 jobs at once.
2.3 Intake (5.0) for the media types contract 4.2 allows: digital, scanned and mixed
    PDFs, images, multi-page TIFF; the document-type gate on the API path; mixed files
    sorted into bills with the other pages reported in notes; accept_unverified_layouts
    true by configuration in the embedded image.
2.4 Health, Prometheus /metrics, JSON logs with request and trace ids; the no-values-
    in-logs rule (invariant 10) on every log line, metric, trace and error; every model
    call in usage with its provider.
2.5 Images for linux/amd64 and linux/arm64. Memory measured with 4 jobs at once on
    the amd64 image; target under 2 GB (esgOS's production machine has 8 GB shared with
    its app, database, ClamAV and Arelle). If 4 jobs need more, the image ships with
    BILLX_JOBS=2 as the default and the release notes state the figure for each.
2.6 contract/esgos-1.1/ written from 6.5 (contract.md, openapi.json generated from
    the Pydantic models, examples, including a request with contact and the contact
    lead it produces); the
    esgos-1.0 and esgos-1.1 examples under contract/examples/, at least one per route
    and one per failure, all synthetic; openapi.json generated and checked;
    docs/contract-1.1.md records what 1.1 adds and why.
2.7 Release 0.1: tag, digests for both platforms, release notes (contracts served,
    memory at 4 jobs, limits, what profile.status means, what is unmeasured), the push
    to esgOS's registry (project esgos-510707) by ESGOS_REGISTRY_KEY. pending-for-user:
    the registry access esgOS must grant if the key is missing. Every later sprint
    release (0.2 gas, 1.0-serving) follows the same steps.
Done when: every contract 1.0 example passes in esgos-1.0 mode and every 1.1 example in
esgos-1.1 mode on synthetic bills (template-route examples arrive in Stage 4;
local_model never occurs; both listed for esgOS); every 6.1a row behaves as written on
a synthetic input; both images build; billx:0.1 is in esgOS's registry with its release
notes; the builder's tests green. STOP.
```

#### Stage 2b — Generic gas reading

```text
STAGE 2b. Read gas bills with no supplier profile, right after Stage 2, beside 3 and 4.
2b.1 The gas section of the core schema; GG01 to GG05 from docs/developer-guide.md,
     each with detects: and proves:.
2b.2 Contract 1.0's guaranteed gas fields (customer id, period, readings, volume.scm,
     gas.gcv_kcal_per_scm, energy.mmbtu, totals.amount) read by Model A and Model B
     and verified by the same consensus and pass rules as electricity (5.2); the gas
     equality checks give arithmetic.
2b.3 The document-type gate sends gas bills to the gas reader; gas_not_yet_supported
     retired; the 6.1a gas row updated.
2b.4 Synthetic gas bills for two layouts in billx synth; the gas examples under
     contract/examples/; release 0.2.
Supplier profiles, anchors and sample sets stay in Stage 10.4.
Done when: every synthetic gas bill passes or is refused for a stated reason; a gas
bill never returns not_a_bill; billx:0.2 is in esgOS's registry; the builder's tests
green. STOP.
```

#### Stage 3 — Full mode, the permanent database, data out, early hosting

```text
STAGE 3. Store everything permanently, serve the engine's own API, and put it where
esgOS can call it.
3.1 full mode with 6.2 and 6.3: per-tenant API keys (stored hashed), the tenant data-
    access layer of 9A.2 on every query, 422 terms_not_accepted; the contract mode and
    field set chosen by the product key (6.6).
3.2 The permanent bill database (9A.2): Postgres, append-only by design, the current-
    state views, versioned object storage (MinIO in Docker, S3-compatible), the
    Postgres queue.
3.3 Terms and consents (9A.1): acceptance at sign-up and at key issue, consent records,
    POST /v1/consent/withdraw, billx erase (9A.5) with its log. The esgos tenant's
    acceptance at key issue covers its users (esgOS's sign-up terms include billx's).
3.4 Intake, the rest of 5.0: password-protected PDFs (pdf_password), zips with their
    limits, HTML rendered with network off, XLSX and CSV stored with
    unsupported_format_profile, the non-bill retention sweep, de-duplication by file
    and by natural key within a tenant (esgOS will resubmit every stored bill once),
    source_conflict.
3.5 The event stream (9D.2): every stage emits events, stored in events;
    GET /v1/jobs/{job_id}/events streams live and replays stored jobs.
3.6 Guaranteed fields through the field map, with units, including the 1.1 open-access
    and green-tariff fields where printed; every printed line returned in elements[]
    with label, amounts and proof (codes arrive in Stage 5a).
3.7 Data out (9A.3). In the sprint: clean JSON (section 8), bills.csv and
    line_items.csv, the callback_url webhook (unsigned until Stage 12), the views and
    their verified-only forms. After the sprint: Excel and Parquet exports, the PDF bill
    card, JSON Schemas, the series API.
3.8 Serving mode (6.6): config/products.yaml, the contract mode and field set per
    product key, wait: true and fields on POST /v1/jobs, POST /v1/read, the
    required-field rule, the Python and TypeScript clients generated from
    openapi.json. The esgos entry: contract esgos-1.1, store permanent, insights true,
    accept_unverified_layouts true, contact_leads true, savings_leads false; contact
    sent on every job. A synthetic "second product" entry
    with its own field set proves the registry is generic.
3.9 Early hosting (section 10.2, O22): docker/compose.hosted.yaml with API, workers,
    Postgres, MinIO and the tunnel; staging and production as two compose projects on
    the Mac behind two tunnel hostnames; the esgos key issued on staging first; a
    docs/runbook.md section on start, stop, backup (the nightly mirror) and restore;
    GET /v1/usage for cost recording.
3.10 Review queue in the studio: the hosted bills with status needs_review, per
    tenant, newest first; one opens in the confirmation screen of 0.5 (page image,
    each reader's value, the reasons in plain words); a named team member confirms
    or types each unverified value from the image, which writes a new record version
    with proof confirmed (5.2), status confirmed and accepted true where the product
    accepts confirmed bills, visible to the caller on its next GET of the bill. The queue reads the hosted database through the tenant
    data-access layer, runs on the Mac at 127.0.0.1 (Tailscale for the rest of the
    team), and shows the queue's age and count on the studio's front page. A second
    tab is the daily spot check of passed bills (12.3), same screen, right-or-wrong
    per field, feeding the incident flow and the sample set.
Done when: full mode refuses a job from a tenant that hasn't accepted the terms; a
synthetic bill is stored, versioned, replayed from its events and exported as JSON and
CSV; two synthetic tenants see only their own records on every call; every 5.0 row
behaves as written on a synthetic input; a call on the esgos key returns a contract 1.1
response and a call on the synthetic product's key returns only its field set, both
through the generated clients; resubmitting the same file returns the existing record;
staging answers at its tunnel hostname from outside the Mac's network; the night's
mirror restores into a fresh compose project and replays a stored bill; a synthetic
needs_review bill on staging is confirmed from the studio's review queue and the
caller's next GET returns status confirmed, accepted true and the confirmed values;
the builder's tests green. STOP.
```

#### Stage 4 — Local reading (roadmap)

```text
STAGE 4. Read locally first: fewer model calls, regions for every value.
4.1 Text layer words as the page's words for digital PDFs.
4.2 Photos: edges, perspective, deskew, crop; the quality gate (config/quality.yaml)
    refusing poor pages with a note on what to retake.
4.3 PaddleOCR (CPU) words with boxes and confidences, English and Hindi; Tesseract as
    the crop reader.
4.4 Anchors: proposed from where each guaranteed field sat on the sample bills, plus the
    inputs of the checks that cover net payable and energy (5.2 rule 3), so a digital
    PDF can pass with no model call; edited in the studio. Versions stay draft until
    Stage 11 finalises them on the golden set.
4.5 The required-number audit of 5.2: every required number in contracts 1.0 and 1.1
    and 6.4's list mapped to the equality checks that cover it; a check added for any
    that has none, or the field listed in pending-for-user.md.
4.6 Alignment: every model value matched to its words, giving its region; X02; region
    events for the live view.
4.7 The full ladder: text_layer or local_ocr is reading 1, model_a reading 2, model_b
    only on disagreement.
4.8 Bilingual labels in anchors and label maps.
Done when: digital PDFs in the sample pass with no model call; scans and photos in the
sample average at most one model call when readings agree; regions within 2% of
synthetic positions; poor photos refused; the sample's silent errors, coverage and cost
reported against Stage 1 (unmeasured); the required-number audit is in the stage
report. STOP.
```

#### Stage 5 — Every element (5a, sprint) and the tariff engine (5b, roadmap)

```text
STAGE 5a. Capture every charge element and recheck each against the bill itself.
5.1 Table-row extraction from the text layer (and from local OCR once Stage 4 exists)
    as reading 1 for every printed line with an amount; Model A's line items as reading
    2; Model B on a line's band only on disagreement (5.1, 5.3). Before Stage 4, a scan
    or photo gets reading 1 from Model B's band reading.
5.2 The element catalogue and capture (5.7): every printed line coded, TOD per slot,
    the element proof rule, completeness through G06, G07 and G09.
5.3 The formula recheck (5.5, part 1) for every element with a quantity and rate or a
    printed base, each with a detects: declaration.
5.7 Coded elements in every result; charges.by_code[] and tariff.category as
    guaranteed fields in full and esgos-1.1 modes; tariff_recheck present with every
    element not_computable: tariff_engine_pending; the by-code columns of bills.csv.
Done when: every element of every sample bill is captured and coded; no element is
verified on arithmetic alone; the builder's tests green. STOP.

STAGE 5b. The tariff engine: recheck every element against the regulator's order.
5.4 The tariff engine (5.5, part 2) in billx/formulas: state-level orders and dated
    notices (FPPCA, duty) in profiles/_states, each parameter cited; every element
    recomputed from the order with the bill's verified quantities; per-element results
    stored; T checks as warnings; I07 fed by differences; tariff_engine_pending
    retired; audit_status audited or partially_audited with audit_version and
    citations; re_audit on tariff-data merges (9A.6).
5.5 Rajasthan (RERC) and Uttar Pradesh (UPERC) commercial and industrial categories,
    with the FPPCA and duty notices for the sample bills' months; the agent collects
    public notices itself and lists them for a person to check in Stage 11, without
    waiting.
5.6 Tariff coverage per layout in billx eval; the tariff views; the by-code section of
    the PDF bill card (once 3.7's roadmap part exists).
Done when: a tariff difference never fails a bill; no tariff comparison runs on an
unverified billed amount; tariff coverage reported for AVVNL and PVVNL on the sample; the
builder's tests green. STOP.
```

#### Stage 6 — Insights (6a, sprint) and intelligence (6b, roadmap)

```text
STAGE 6a. Turn verified bills into findings for esgOS and every other caller.
6.1 Insights I01, I02, I03, I04, I06 and I10 (9.2): the ones that need no tariff
    order; estimates as ranges with assumptions from config/insights.yaml. The esgos
    key gets insights on every passed bill (defaults.insights true).
6.2 Leads (9.3): the leads table, LEADS_WEBHOOK_URL, the daily LEADS_EMAIL digest
    and the studio's leads view with CSV export; a contact lead on every sign-up and
    every upload from every product (one per person per product, updated
    on later uploads, contact_missing when a product sends no usable name and email);
    savings leads with consent and the threshold for products with savings_leads
    true; the withdraw call.
Done when: one synthetic bill triggers each of the six insights and one triggers none;
no insight appears on an unverified bill; an upload on the esgos key creates or updates
a contact lead, carries insights[] and creates no savings lead; an upload on a
synthetic product with consent and a large enough finding creates both; the
builder's tests green. STOP.

STAGE 6b. The rest of the catalogue and the intelligence layer.
6.3 I05, I07 (tariff differences and printed-inconsistency flags), I08 (state
    benchmarks), I09, once Stage 5b exists.
6.4 Intelligence (9.4): anomalies, forecasts priced by the tariff engine, benchmarks
    (at least 10 accounts per group), the monthly digest.
Done when: one synthetic account history triggers each anomaly and one triggers none;
every insight has a triggering synthetic bill; the builder's tests green. STOP.
```

#### Stage 7 — The web app and the live reading view (roadmap)

```text
STAGE 7. Let users watch their bills being read and explore them.
7.1 The web app (9D.1, 9D.3): sign-in (O14), upload with terms acceptance at sign-up,
    bill view, the review page with confirmed values, analytics, exports, settings
    (saved PDF passwords under a configuration key). The email-in channel matched to
    registered users (5.0).
7.2 The live reading view (9D.2), driven only by the event stream; replay of stored
    bills; band highlights before regions exist; reduced motion and the text reading
    log; light and dark themes; phone layout.
7.3 The not-an-electricity-bill experience end to end, on synthetic water, telecom,
    receipt and letter documents.
Done when: the web app and the live view work on synthetic bills in both themes and at
phone width, checked by a person on the team; every animated step is driven by a
stored event; the builder's tests green. STOP.
```

#### Stage 8 — The assistant (roadmap)

```text
STAGE 8. Let users ask questions about their bills.
8.1 The Haystack Agent with the tools of 9C over the verified-only views; query_bills as
    a structured query, never free SQL; the pgvector store holding tariff orders,
    notices and bill pages (local embeddings).
8.2 Numbers as tool references with the verifier; citations; chart specifications;
    stored conversations; allow_assistant_cloud.
8.3 The assistant in the web app's chat, POST /v1/assistant/ask and the MCP tool
    ask_my_bills (the MCP server itself arrives in Stage 9).
8.4 A first set of 20 golden questions on synthetic tenant data for the builder's own
    use; the full set of 100 and its gates are Stage 11 work.
Done when: the 20 questions answer with every number a tool reference cited to the
right bill and month, checked by a person; an off-topic question is refused; the
builder's tests green. STOP.
```

#### Stage 9 — The MCP connector, the comparison lab and the remaining hosted surfaces (roadmap)

```text
STAGE 9. Offer the platform to LLM apps and the team's own tools.
9.1 Hosted services completed: the web app, the comparison worker and the assistant
    service added to the hosted compose; each scaling separately when the service
    moves to a cloud VM (O22).
9.2 The MCP server (section 7): every tool including ask_my_bills, get_series and
    export_bills; resources; prompts.
9.3 The comparison lab (9B): Docling and LlamaParse in the comparison worker, their
    measures in billx eval, production sampling (LlamaParse only where the job allowed
    cloud models and allow_comparison_cloud is true), the team-only /internal/ view.
9.4 docs/onboarding.md kept current for every application that calls billx: how to
    register, the field sets, what profile.status and unmeasured mean, the clients.
    billx never creates branches in Ergplan/esgOS; esgOS's own build agent makes
    changes there. Reading that repository is fine.
9.5 docs/api.md, docs/mcp.md, docs/data-model.md, docs/assistant.md, docs/comparison.md
    current.
Done when: staging runs end to end on synthetic bills through the API, the web app and
an MCP client; the comparison report runs on the sample set; the builder's tests
green. STOP.
```

#### Stage 10 — Coverage, state by state, then gas suppliers (roadmap)

```text
STAGE 10. Repeat per state, in the order in section 15 (O4), until every discom is done.
10.1 The state's tariff order and its notices into profiles/_states/<state>/ with
     citations, and into the assistant's document store; the agent collects what is
     public and lists it for a person to check in Stage 11.
10.2 Each discom: match patterns (English and local script), extends for sister
     discoms, 10 sample bills confirmed, anchors, rules, draft versions served at once
     with profile.status draft (12.4).
10.3 Drift: S06 or a run of tariff differences opens a draft version for a person.
10.4 Gas suppliers, after the states in O4's first group: supplier profiles, anchors
     and 10 sample bills each if the team has supplied them; otherwise synthetic only,
     listed pending.
A discom is done, for this stage, when its profile reads all 10 sample bills end to
end, a hand-run billx eval reports the sample's numbers (unmeasured), and its tariff
coverage is reported. Its launch gate is Stage 11's. Report after each state. STOP
after each state.
```

#### Stage 11 — Accuracy, then product testing

```text
STAGE 11. Now the priorities flip: zero silent errors first, then test the whole
product once, before the public launch. No feature work in this stage; a fix is
allowed only where accuracy, a test or a review finding requires it. Accuracy (11.0)
comes before the test work (11.1 to 11.6), because tuning changes prompts, profiles
and checks and the tests must run on the tuned engine.
11.0 Accuracy. The full golden set per the Stage 11 part of 12.1: 30 to 60 bills per
     layout confirmed in the studio, the tuning/held-out split, the sample set in the
     tuning half, the held-out hygiene rule. A person checks every state's encoded
     tariff data and notices against the documents (deferred from 5.5 and 10.1).
     Tune prompts, profiles, anchors and checks on the tuning half; finalise profile
     versions; re-choose the model pair if the full set says so (10.3); re-read every
     stored bill of a layout whose profile changed (9A.6), so the records callers hold
     are the tuned engine's. Then the launch gate per discom (12.4): profile.status
     verified where it is met.
11.1 Independent review (section 3) of every stage's diff, in order, and independent
     black-box tests in tests/independent/stage-N/. At most two review-fix rounds per
     stage; findings below high go to docs/known-gaps.md with a reason.
11.2 Planted-misread tests for every check, formula and tariff component: a synthetic
     bill with one wrong digit at a position the declared detects: value can catch;
     the clean bill passes, the planted one fails. A check whose declared value is
     wrong is fixed here. Each equality check's proves: paths are each covered.
11.3 Product tests: contract tests for all three API modes on both image platforms,
     against contract/examples; MCP SDK client tests (a long job, a refused bill, a
     wrong document type, a not-passed bill, a printed inconsistency); Playwright on
     synthetic bills in both themes and at phone width, with the animated-step-to-
     event test; the assistant's 100 golden questions and their gates (9C); mypy
     strict on the codebase.
11.4 Invariant tests: no float anywhere in a result, export or MCP output; one
     verification rule (no module other than proof.py assigns a verification, and a
     Value whose verification doesn't follow from its evidence is rejected);
     repeatability (the same file twice gives the same result); privacy (no values in
     logs, metrics, traces or errors); tenant isolation (one tenant cannot read
     another's records through any call or tool); append-only (enforced by database
     grants from here on, 9A.2); erasure of a synthetic user leaves no value in any
     table, store or index; exports validate against their JSON Schemas; every 6.1a
     and 5.0 row.
11.5 The nightly evaluation job and docs/accuracy/ reports (12.2); the document-type
     gate both ways (12.5); the comparison readers' report beside the engine.
11.6 Load: 20 bills at once; a one-page bill under 60 s at the 95th percentile with a
     cloud model; the live view keeps pace. The weekly production audit starts (12.3).
Done when: every served discom meets its launch gate (0 silent errors and 0 false
refusals on its held-out set, n stated) or is marked draft; every independent test
passes; every planted misread is caught; every invariant test passes; the nightly job
has run clean for seven nights; mypy strict is clean. STOP.
```

#### Stage 12 — Public launch

```text
STAGE 12. Ready for public connector directories and for callers Joulewise doesn't
control.
12.1 The security items of section 11, OAuth 2.1 for MCP first, then row-level
     security and roles, append-only grants if not already done in 11.4, signed
     webhooks, KMS-encrypted passwords, SPF/DKIM on email-in, rate limiting, scanning
     gates, audit logs, per-tenant BI access.
12.2 Counsel's sign-off on the terms, the lead consent and billx erase (9A.5).
12.3 The hosted service moved to a cloud VM if O22's conditions have been met and it
     hasn't moved already; the Mac becomes a build machine only.
12.4 Release 1.0: image digests, release notes (memory, limits, per-discom accuracy
     with sample sizes), examples, OpenAPI, MCP and assistant documentation.
Done when those hold and the team signs off. STOP.
```

## 14. Plan and what people must supply

With three builder sessions running continuously on the Mac, code is rarely the constraint in the sprint; the sample bills, same-day merges and esgOS's registry access are.

**Sprint 1** (section 13.1): 14 days, each period with its acceptance requirement. Day 5 the 0.1 image in esgOS's registry; day 7 gas; day 10 staging with the `esgos` key; day 14 a controlled production pilot after explicit sign-off. If a period's requirement is not met, the pilot slips; the objective does not get redefined. The agent effort is roughly 36 session-days across the three sessions, which is the whole fortnight with little slack; the freeze absorbs what overruns.

**Roadmap** (after the sprint), with three sessions and the dependency table in 13.2:

| Stage | Agent effort (session-days) | Calendar |
| --- | --- | --- |
| 3.7 remainder, 4 | 6–9 | week 3 |
| 5b | 4–6 (the team's check of orders and notices waits for Stage 11) | week 3–4 |
| 6b | 2–3 | week 4 |
| 7 | 6–9 | week 3–4, beside 4 and 5b |
| 8 | 4–6 | week 5 |
| 9 | 3–5 | week 5–6 |
| 10 | about 1–2 per state and ½–1 per discom, plus 10 confirmed bills each | weeks 3–8, by state, beside everything |
| 11 | 12–18, plus the team confirming 30–60 bills per layout and checking every state's tariff data; expect the longest fix list of the build | weeks 8–11 |
| 12 | 3–5 | week 12 |

These rank effort; they are not promises. esgOS is served from day 5 (embedded) and day 14 (hosted pilot); Engine 2's tariff audit arrives with Stage 5b around week 4, when `audit_status` first becomes `audited`; the full product exists around week 6; accuracy is measured and tuned in weeks 8 to 11. The bottleneck from day 2 on is people: confirmed bills and merges.

**Before day 1:**
1. The Mac mini (section 3.1): Apple silicon M4 Pro; 48 GB or more of memory is comfortable with three sessions, Docker (Postgres, MinIO, API, workers) and OCR together (24 GB works but the sessions will contend); 1 TB disk or more; FileVault on; an admin account for Homebrew and Docker; wired network; **an external drive** for the nightly mirror; **a Cloudflare account with a domain** (or Tailscale) for the tunnel hostnames.
2. The repository: private, branch protection on `main`, the agents' access, GitHub Actions enabled, GitHub Container Registry enabled for the organisation.
3. Read access for the agent to `git@github.com:Ergplan/esgOS.git`.
4. **From esgOS:** a service-account key for its registry (project `esgos-510707`) so releases can be pushed there, or the registry path and the instruction to grant read access the other way; and confirmation that two model providers are accepted (O17, already given).
5. Keys, in the Mac's `.env`: OpenAI (Model A, evaluation and later the assistant), Anthropic API (Model B in the product; the Claude Max plan covers Claude Code, not the product's own calls), a Console API key so the builder never idles on a plan limit, `ESGOS_REGISTRY_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`, and a separate OpenAI key and project for the reviewer (Stage 11), each with a monthly budget. LlamaParse only from Stage 9.
6. The `CLIENT_IDENTIFIERS` CI secret, and the same list in `~/billx-data/`: consumer names, account numbers, GSTIN and PAN on the real bills in the repository today.
7. The file "billx Developer Guide: super billx" (version 2), saved in Stage 0.6, and the esgOS change list of 11 Oct 2026, saved as `docs/esgos-changes-2026-10-11.md`.

**By day 2:** the sample set, 10 confirmed AVVNL and 10 confirmed PVVNL bills (6 digital PDFs, 2 scans, 2 phone photos each; about an hour per layout in the studio), and the terms text (a paragraph is enough; counsel's version follows in Stage 12).

**By day 7:** the discoms of esgOS's first clients' plants, which sets the state order (O4); the CRM webhook for leads, so contact leads flow from the first hosted upload; and esgOS's agreement that it consumes `accepted` rather than `status == passed` (6.5 item 7), so bills corrected by a reviewer reach it.

**Before Stage 5b:** the tariff orders and the FPPCA and duty notices for the sample months, where the agent can't find them on regulator and discom websites itself.

**For Stage 10:** 10 confirmed bills per new discom, as each state is reached. **For Stage 11:** the full golden set, 30 to 60 bills per layout, and a person's check of every state's encoded tariff data; the team can start confirming whenever it has capacity.

**Before Stage 12:** the web app's domain and branding, the sign-in method, the email-in domain, and a decision on O22.

## 15. Defaults and open decisions

The agent uses the default in brackets if a question is left unanswered, and records it in `decisions.md`. Items marked *answered* came from the esgOS change list of 11 Oct 2026 and are not reopened.

- **O1. Cloud project.** [None. Code, CI and images on GitHub; bills, database and the hosted service on the Mac (O22). esgOS's registry is esgOS's project.]
- **O2. Model pair.** [A: OpenAI `gpt-6.1-sol`; B: Anthropic `claude-sonnet-5-5`; `doctor.sh` verifies both ids exist in Stage 0; Stage 1 may change either by measurement.]
- **O3. Bills per layout.** [10 during the build (6 digital, 2 scans, 2 photos), all tuning. In Stage 11: 30, so 15 are held out, with at least 3 phone photos and 3 scans in each half; 60 where the team can confirm them.]
- **O4. State order.** [The discoms of esgOS's first clients' plants, in the order the team lists them (by day 7, pending-for-user). Until the list arrives: Rajasthan, Uttar Pradesh, Maharashtra, Gujarat, Delhi, then Tamil Nadu, Karnataka, Telangana, Andhra Pradesh, Haryana, Punjab, Madhya Pradesh, West Bengal, then the rest. Gas suppliers after the first five states (Stage 10.4).]
- **O5. Tariff categories.** [HT and LT commercial and industrial. Domestic and agricultural only on request.]
- **O6. Plans and quotas.** [None. The product is free; cost is recorded per tenant and `max_cost_usd` is the only limit.]
- **O7. Savings-lead threshold.** [₹1,00,000 a year combined low estimate, for products with `savings_leads: true`. Contact leads have no threshold: every sign-up and upload.]
- **O8. Reviewer budget.** [Set by the team for Stage 11; the agent reports spend weekly and pauses the reviewer at the cap.]
- **O9. Run mode.** [Staged through day 4 of the sprint, then autonomous on the builder's own tests; the freeze days and Stage 7 stay staged so a person reviews; Stage 11 stays staged because it is where the accuracy claims are made.]
- **O10. Unverified layouts.** [`profile.status` on every bill. The `esgos` key and the embedded image pass any layout under the 5.2 rules (*answered*); the public API returns `needs_review` with `unverified_layout` from Stage 11 unless the tenant opts in.]
- **O11. Retention.** [`permanent` storage: permanent, append-only, erasure only by 9A.5. `ephemeral` (the embedded image): 24 hours, as contract 1.0 requires.]
- **O12. Comparison sampling.** [Docling on every sample and golden-set bill, LlamaParse on those marked `comparison_cloud_ok`; in production 10% of bills plus every bill needing review, LlamaParse only where the job allows cloud models and `allow_comparison_cloud` is true.]
- **O13. Assistant model.** [OpenAI's default chat model; Claude through Haystack's Anthropic integration as the alternative; chosen by the golden questions in Stage 11.]
- **O14. Web sign-in.** [Email magic link.]
- **O15. Benchmark group minimum.** [10 accounts.]
- **O16. Terms.** [One current version, accepted once at sign-up or key issue; a new version is shown at next sign-in and never blocks storage. esgOS's sign-up terms include billx's; the `esgos` tenant's acceptance at key issue covers its users (*answered*).]
- **O17. Model providers inside esgOS.** [*Answered:* esgOS accepts OpenAI and Anthropic as configured providers for bill reading. Scans and photos pass from Stage 2 when Model A and Model B agree; every call is in `usage` with its provider.]
- **O18. Non-bill files.** [Deleted after 30 days, keeping hash and classification; gas, water and telecom bills kept permanently.]
- **O19. WhatsApp intake.** [After Stage 9: a WhatsApp Business number with the same sign-up requirement as email.]
- **O20. Local OCR timing.** [Stage 4, as planned (*answered*). With two providers accepted, nothing in the sprint needs it.]
- **O21. How esgOS calls billx.** [*Answered:* the hosted service, on the `esgos` product key in `esgos-1.1` mode with `store: permanent`. Until hosting is live, esgOS runs the embedded image from its own registry; the switch is a URL and token change, and esgOS resubmits every stored bill once. billx creates no branches in `Ergplan/esgOS`.]
- **O22. Where the hosted service runs.** [On the Mac mini, in Docker behind a Cloudflare Tunnel (or Tailscale Funnel), staging and production as two compose projects on two hostnames, data mirrored nightly to the external drive. It moves to a cloud VM (any provider; asia-south1 if Google, to sit beside esgOS) when any of these holds: a caller Joulewise doesn't control, a 95th-percentile read above 90 s during builds, an uptime incident that cost a caller data, or Stage 12. Everything is Docker and S3-compatible, so the move is a day's work and no code change.]

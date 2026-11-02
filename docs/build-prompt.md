# billx build prompt, version 5.0: the verified bill parser, with formulas, built on this Mac and pushed to GitLab

12 Oct 2026 · Joulewise · version 5.0 rebuilds 4.2 on one instruction from the team, given on 12 Oct 2026 with the team away for 24 hours: *resolve every conflict, build a first-level bill parser with no errors and with formulas, and keep building without stopping.* The full 4.2 text stays in the repository as `docs/build-prompt-4.2.md` for everything this version defers (hosting, the permanent database, insights, leads, the web app, the assistant, MCP, the comparison lab, the tariff engine); nothing in it is lost, and section 14 says where each deferred piece lives. The esgOS change list of 11 Oct 2026, the Developer Guide Part A and esgOS contract 1.0 remain inputs; section 13 records how each conflict between them and 4.2 was settled, and those settlements are not reopened.

**What 5.0 changes, in one paragraph.** The goal is a **parser that reads an electricity or gas bill into exact values, proves each value by two independent readings, checks every value with the bill's own arithmetic, recomputes every charge from its printed quantity and rate (the formulas), and says honestly what it could not verify.** It serves esgOS contract 1.0 exactly and contract 1.1 on top, in one container. It is proven on synthetic bills and planted errors now, and on real bills as the team confirms them. Local OCR moves from Stage 4 to Stage 1, so a digital PDF verifies with no model key and a scan verifies with one; the model readers are built and tested with mocks and run live the moment a key is placed in `.env`. The repository moves to GitLab (`icac1/ocr-bill-extraction`) with GitLab CI and the GitLab container registry. The run is autonomous: the builder merges a stage to `main` when its tests are green and its "done when" holds, pushes, and starts the next.

**How to use this file.** It lives at `docs/build-prompt.md`; sections 1 to 5 are copied verbatim into `CLAUDE.md` (the builder) and `AGENTS.md` (the reviewer); `tools/check_copy.py` enforces the copy. A session starts with `Run Stage N of docs/build-prompt.md`, or `Continue docs/build-prompt.md` to pick up the first stage whose "done when" does not yet hold.

**Who does what.** Claude Code on this Mac is the builder, with subagents in git worktrees for independent items. An OpenAI model is the reviewer in Stage 11 (4.2 section 3) and nothing else. The Joulewise team supplies real bills, confirms them in the studio, puts keys in `.env`, and reads the stage reports.

---

## 1. Mission

**Every bill that arrives is read into exact values, each value verified by two independent readings or refused, the bill's own arithmetic checked, every charge recomputed from its printed quantity and rate, and the result returned under esgOS's contract, with nothing hidden.**

For every bill, in this order:
1. **Intake** of a PDF (digital or scanned), JPG, PNG, HEIC, WebP or TIFF, one or several bills per file. A file that is not an electricity or gas bill is identified and named, never read as one (5.0).
2. **Reading** by independent readers: the PDF's genuine text layer, local OCR, Model A, Model B. A value is `verified` only when the rule in 5.2 is met; otherwise it is `unverified` or `disputed` and the bill does not pass. The engine refuses or holds a bill rather than guess.
3. **Validation:** the bill's own arithmetic, G01 to G20 and the gas checks GG01 to GG05, each with a declared `detects:` and a planted-misread test (5.4).
4. **Formulas:** every charge element recomputed from its printed quantity and rate, section subtotals and the net payable reconciled, the discom's own rules from its profile (duty, cess, surcharge percentages) evaluated as expressions (5.5). The tariff-order recheck against the regulator is deferred (4.2 Stage 5b); every result says so in `audit_status: not_audited`.
5. **Element capture:** every printed line with an amount, coded to one catalogue (5.7).
6. **Response** under contract 1.0 exactly, or 1.1 on top, with `profile.status`, `audit_status`, `proof` and `readers` on every value so a downstream report can label what it is built on.

**Three engines, one data contract.** billx is three engines sharing the core schema (Stage 1.1) and nothing else: **Bill Reader** (`billx/reader/`, `billx/core/`: this build), **Bill Auditor** (`billx/auditor/`: the tariff engine, deferred) and **Bill Intelligence** (`billx/intelligence/`: insights and the assistant, deferred). The import-boundary test keeps them apart from Stage 0.

**The principle every engine keeps:** billx never silently converts a plausible AI extraction into a financially trusted value. A value is `unverified` until the rule in 5.2 is met; a bill from a draft or unknown layout says so on every result; a bill not audited against the tariff order says that too.

**Priorities, in order, for every trade-off:** no errors (a planted misread in any field or check is caught; a `verified` value with no evidence cannot exist); then every value a caller receives carrying its `proof`; then complete capture of every printed element; then coverage; then cost; then speed. Accuracy on real bills is **measured and labelled `unmeasured`** until the team's confirmed bills exist (section 10); it is never advertised.

**Surfaces in this build:** the HTTP API (contract 1.0 and 1.1, section 6), the command line (`billx extract`, `validate`, `eval`, `synth`, `studio`, `serve`), and the studio for confirming real bills. Everything else is deferred (section 14).

## 2. Definitions

| Term | Meaning |
| --- | --- |
| **Guaranteed field** | A field the API promises: contract 1.0's section 6 lists, plus the additions in 6.4. The paths are the contract's paths, exactly |
| **Required field** | A guaranteed field marked required in the contract; a bill cannot pass without it `verified` (or `confirmed`) |
| **Reader** | Something that produces a value for a field from the file: `text_layer`, `local_ocr`, `model_a`, `model_b` (5.1) |
| **Independent readers** | Two readers that differ in method (text layer, OCR, vision model) or in model family (OpenAI, Anthropic), neither given the other's answer, hints, or regions |
| **Verification** | The one decision per field made by `decide` (5.2): `unverified`, `verified`, `disputed` or `confirmed`. Evidence (readings and proof levels) is what it is decided from |
| **Passed bill** | A bill that meets the pass rule of 5.2. `passed` is the engine's own verdict and never changes meaning |
| **Accepted bill** | A bill a caller may use: `passed`, or `confirmed` by a named person where the product accepts that (6.5) |
| **Silent error** | A field marked `verified` on a passed bill that differs from what a person confirms from the page |
| **Planted misread** | A synthetic bill with one digit changed in one value, at a position the check's `detects:` declares it can catch; the clean bill passes, the planted one fails. Every check and formula has one from the stage it is written in |
| **Coverage** | Passed bills ÷ readable bills submitted |
| **Correct refusal** | A non-bill or unreadable file refused rather than read; never an error. **False refusal:** a bill refused as something else; always an error |
| **Sample set** | The team's real bills, confirmed in the studio (10 per layout is the target); all tuning data, none held out |
| **Layout** | One discom's bill design in one period; a profile version describes one. `profile.status` is `final` (met its launch gate, 4.2 section 12.4), `draft` (a profile exists, unmeasured) or `none` (no profile; read by the generic ladder). The contract's words are used everywhere; 4.2's `verified` for a layout means `final` |
| **Charge element** | One printed charge, rebate, surcharge, duty, cess, arrear or adjustment, coded to the catalogue (5.7) |
| **`detects:`** | The smallest error a check or formula can catch, declared in its definition; the planted-misread test proves it |

**What "no errors" means here.** Every check, formula and reader has a test; every check has its planted misread caught; the no-float, one-rule and no-values-in-logs tests pass; lint and tests are green on every commit on `main`. On real bills, the only honest statement before the team confirms a sample is `unmeasured`, with the engine's own `proof` on every value.

## 3. Operating rules for the agents

1. **Stages in dependency order, without stopping.** A stage starts when the stages it depends on are merged (section 11). Independent items inside a stage run as subagents on git worktrees, each on `stage-N-x`, merged into `stage-N` as they finish.
2. **A stage ends** when its "done when" holds on synthetic bills, lint and tests are green, and `docs/stage-reports/stage-N.md` records what changed, defaults chosen, pending items and model spend. **Autonomous mode (from 12 Oct 2026):** the builder then merges `stage-N` into `main`, pushes to GitLab, and starts the next stage. No independent review during the build; it runs once, in Stage 11.
3. **Branches.** Each stage starts from `main` on `stage-N`, tagged `stage-N-start`. `main` is pushed only by the builder's stage merge or by a person. A release is a tag on `main`.
4. **Tests come with the code.** Every check and formula declares `detects:` and gets its planted-misread test in the same commit. No coverage gate. Product-level tests beyond the contract examples are Stage 11 work.
5. **Never commit over red.** Never skip, delete, loosen or mark expected-failure a test. Never narrow a "done when" item. A correct refusal is never counted wrong; a false refusal always is.
6. **The model transcribes, never calculates.** Every number in `data` is printed on the bill. Formulas, totals and conversions live in code.
7. **Exact numbers.** `Decimal` from reading to response, in the Pydantic v2 models of the core schema in strict mode. One test walks every model and fails on any float.
8. **One implementation per check and formula.** The API, CLI, studio and evaluation call the same validation code.
9. **Model calls only in `billx/reader/providers/`.** Prompts are versioned files under `billx/reader/prompts/`, never edited in place. Every call has a timeout, bounded retries, a cost estimate before and a usage record after.
10. **No real bills in git, CI logs, the image, test fixtures, or any request to a reviewer.** Synthetic bills only in the repository. Reports describe bills by discom, layout and input kind, never by consumer or value. The builder never opens a real bill's values; people see bills in the studio.
11. **No questions during a stage.** Use the defaults in section 12, record each choice in `docs/decisions.md`, list what only a person can give in `docs/pending-for-user.md`, and continue with synthetic data.
12. **Nothing environment-specific in code.** Hosts, keys, model ids, prices, limits, retention and paths come from configuration.
13. **Living documents change in the same commit as the code:** `docs/architecture.md`, `docs/decisions.md`, `docs/known-gaps.md`, `docs/runbook.md`, `docs/pending-for-user.md`, `docs/api.md`, `docs/data-model.md`, `docs/accuracy/`.
14. **Rate limits.** On a provider 429, wait 60 seconds and retry with backoff. Record each stage's real spend per provider.
15. **Append, never overwrite.** A correction or re-read creates a new version beside the old one.
16. **Keys.** Real keys live only in `~/billx/.env` (git-ignored, mode 600), placed there by a person. The builder never reads that file, never asks for a key in chat, and never echoes one. `.env.example` lists the names.

### 3.1 The build machine and the repository

- **The Mac** (Apple silicon): the builder, tests, the studio, Docker (arm64 images), local OCR. Python 3.12 from `uv` in `.venv` (no Homebrew, no admin rights on this account); PaddleOCR runs natively here and in the `linux/arm64` image, RapidOCR in the `linux/amd64` image (recorded in Stage 0).
- **The repository** is `~/billx` (the team's folder `~/Documents/OCR Application/billx` is a link to it). The remote is `https://gitlab.com/icac1/ocr-bill-extraction.git`, branch `main`. CI is `.gitlab-ci.yml` on GitLab's shared runners; images go to `registry.gitlab.com/icac1/ocr-bill-extraction/billx` for `linux/amd64` and `linux/arm64`; a release tag also copies the image to esgOS's registry when `ESGOS_REGISTRY` and `ESGOS_REGISTRY_KEY` exist as CI variables.
- **Bills** live in `~/billx-data/` (never git): `golden/unconfirmed/<discom>/` as supplied, `golden/manifest.jsonl` once confirmed, `workspaces/` for the studio. The nightly mirror to an external drive, the tunnel and the hosted compose stack are deferred with hosting (section 14).
- **Keys** in `~/billx/.env`: `BILLX_OPENAI_API_KEY` (Model A), `BILLX_ANTHROPIC_API_KEY` (Model B), later `OPENAI_BUILD_REVIEW_KEY` (Stage 11). `tools/mac/doctor.sh` reports presence and makes one one-token call per configured model id; it never prints a value.
- **Pace.** Subagents in worktrees for independent items; `pytest -n auto`; image builds in the background. Every stage report states wall-clock time and the longest single wait.

## 4. Invariants

Each overrides anything else in this file. If a stage prompt conflicts with one, the invariant wins and the builder records it.

0. **No silent promotion.** No code path turns a reading into a verified value except `decide` (5.2); no code path turns a verified value into an accepted bill except the pass rule and a named person's confirmation; no result hides that a layout is draft or a bill is unaudited.
1. **Passed means verified.** `passed` is true only under the pass rule of 5.2, and `decide` in `billx/reader/validate/proof.py` is the only code that assigns a verification. A model validator recomputes every verification from its evidence and rejects a mismatch.
2. **Skip is never pass.** A check whose inputs are missing reports `skip`.
3. **The model transcribes.** Every value in `data` is printed on the bill.
4. **Exact decimals.** No float anywhere in a result.
5. **esgOS contracts 1.0 and 1.1 keep working.** Their calls, fields, enums and error codes behave exactly as written; 1.1 adds optional fields only and `passed` keeps 1.0's meaning.
6. **Repeatable.** The same file, engine version, profile version and model ids give the same result; temperature 0 where the model accepts it.
7. **Utility knowledge is versioned data.** Profiles and formulas are YAML; final versions are frozen; every tariff parameter cites its source.
8. **The caller decides model use.** With `allow_cloud_model` false, no cloud call is made for that job by any code path. Spend never exceeds `max_cost_usd`; every call is in `usage`.
9. **No values in logs.** Logs, metrics and error messages carry ids, hashes, timings and check ids only.
10. **Every check and formula declares what it detects**, and has the planted-misread test that proves it, in the same commit.

## 5. Verification design

The word used everywhere is *verified*: a value met the acceptance rule in 5.2. Nothing in the product or its documents says "proven", "guaranteed" or "zero-error".

### 5.0 Intake and the document-type gate

| Input | Handling |
| --- | --- |
| PDF, digital | Genuine text layer with word boxes (pypdfium2), plus rendered pages at 200 dpi |
| PDF, scanned or mixed | Rendered pages; a hidden OCR layer (invisible text, or text under a full-page image) is never a genuine text layer |
| PDF, password-protected | `passed: false`, `route: "none"`, `unread_reason: "unreadable"`, note `password_required` (contract 1.0 has no password option; `pdf_password` is a 1.1 option) |
| JPG, PNG, HEIC, WebP, TIFF (multi-page too) | Photo preparation: EXIF rotation, then pages. Edge detection, perspective correction and the quality gate are deferred (4.2 Stage 4.2); a page that OCR cannot read ends `unreadable` with a note |
| Anything else (HTML, XLSX, CSV, ZIP, BMP) | 415 `unsupported_type` in the esgOS modes |
| At most 25 MB and 30 pages | 413 `too_large` beyond either |

**Document-type gate.** Before any reading, every file and every page group within it is classified `electricity_bill`, `gas_bill`, `water_bill`, `telecom_bill`, `other_invoice` or `not_a_bill` from **local signals** (text layer or OCR words): units (kWh, kVAh, kVA, SCM, MMBtu, kilolitres), discom and supplier names from the profiles' `match` patterns, meter-reading tables, words such as tariff, contract demand, units consumed. Model A confirms only when the local signals are unclear **and** the caller allows cloud use; otherwise an unclear page is `not_a_bill` with a note `type_unclear`. Anything other than an electricity or gas bill is never read as one: the note names what it appears to be. A file mixing a bill with other pages keeps the bill and reports the other pages' numbers in `notes`.

**Page sorting.** Pages are grouped into bills by bill number and account where printed, else by page order; several bills in one file become several entries in `bills[]`.

### 5.1 Readers and proof levels

| Reader | Method | Reads | Available from |
| --- | --- | --- | --- |
| `text_layer` | Words of a genuine digital-PDF text layer, with boxes | Guaranteed fields by the label rule (5.3); table rows as elements | Stage 1 |
| `local_ocr` | PaddleOCR (RapidOCR on linux/amd64) words with boxes and confidences, on the rendered page | Guaranteed fields by the label rule; table rows as elements | Stage 1 |
| `model_a` | Vision model, family A (default OpenAI), the whole bill into the core schema | Everything: guaranteed fields and every printed line | Stage 1 (mocked in tests; live with a key) |
| `model_b` | Vision model, family B (default Anthropic), the guaranteed fields from the full page and three horizontal bands; never shown another reader's values | Guaranteed fields; any printed line when asked | Stage 1 (mocked in tests; live with a key) |

Two readers are **independent** when they could not share a mistake: they differ in how they *find* a field as well as how they read it, and neither is given the other's answer, the caller's `hints`, or a region found by the other. `text_layer` and `local_ocr` read characters independently (one decodes embedded text, the other reads pixels) but both find a field by the same label rule, so on a layout where that rule picks a neighbouring label they agree on the same wrong text. **Two local readers therefore never verify each other** (proof rule 2, from 23 Oct 2026, after real HPSEBL, MSEDCL and PVVNL bills showed it); a local reader and a model are independent, and two models are when their families differ. `hints` are used only after reading, as a check: a mismatch adds a note, never a value.

**A text layer counts only when it is genuine.** Text with render mode 3 (invisible), or under a full-page image, is treated as `local_ocr`-grade input, never as `text_layer`.

**Proof levels** are evidence, never a verdict:

| Proof level | Meaning |
| --- | --- |
| `consensus` | Two independent readers return the same normalised value |
| `arithmetic` | The field is an input or result of at least one passing **equality** check (G02 to G09, G15, G17, GG02 to GG05, and profile `rules` of severity error) whose `detects:` can catch a one-digit change in the field's two leading significant digits. Each such check lists the paths it proves in `proves:`. Extra assurance only; it never proves a field alone |
| `exact` | Read from a genuine text layer inside the field's anchored region. Anchors are deferred (4.2 Stage 4.4), so nothing earns `exact` in this build; the level exists in the schema |
| `confirmed` | Entered or confirmed from the page image by a named person in the studio |
| `single` | One reading only |

**Normalisation before comparing:**

| Field type | Normalised by | Must match exactly |
| --- | --- | --- |
| Number | removing digit grouping (Indian or Western) and currency marks, converting Devanagari numerals, removing trailing zeros after the point | the digits, the sign, the decimal position |
| Date or month | parsing to ISO (`YYYY-MM-DD`, `YYYY-MM`), day first; month names in English | the date itself |
| Identifier | removing spaces, hyphens and slashes; upper case | leading zeros and every other character |
| Text | collapsing spaces; upper case | the words |

**Arrays** (`readings[]`, `energy.tod[]`, `elements[]`) are matched item by item on their key (register and slot, or label-as-printed plus position), then compared field by field. An item one reader has and the other lacks is `unverified`.

### 5.2 The verification rule and the pass rule

**One function decides.** `billx/reader/validate/proof.py` holds `decide(evidence) -> Verification`, the only implementation of the rule below, versioned (`proof_rule_version` in every result). Every other place that needs a verification calls it; a test asserts no other module assigns one.

| Evidence | Verification |
| --- | --- |
| One reading only | `unverified` |
| Two independent readers agree on the normalised value (`consensus`) | `verified` |
| `exact`, and for a number also `arithmetic` (deferred with anchors; the rule is written and tested now) | `verified` |
| Readings exist but no two independent readings agree | `disputed` |
| A named person confirmed or typed the value from the page image | `confirmed` |

**What `verified` means.** The rule was met. It is not a guarantee: two readers can share a misreading. The rule makes that unlikely by demanding different methods or families and no shared hints or regions; how often it still happens is measured on confirmed real bills, never assumed.

**X01 is this rule.** X01 holds when `decide` returns `verified` or `confirmed` for every required guaranteed field. An outvoted third reading is kept in `readers`, never a failure.

A bill **passes** only when all of these hold:
1. No check fails, except a check marked `printed_inconsistency` (below), and X01 holds.
2. Every required guaranteed field is present and `verified` (or `confirmed`).
3. **Arithmetic covers the money and the energy:** `totals.net_payable` and the bill's energy field (`energy.kwh`, or `energy.kvah` under 1.1) each take part in at least one passing equality check; for gas `totals.amount` and `volume.scm` or `energy.mmbtu`. Otherwise the reason is `insufficient_arithmetic`.
4. **No check skipped because of an unverified value.** Checks run on the fullest reading available with every verified value substituted in; a check that fails or skips because an input is not verified makes the bill `needs_review` with `unverified:<path>` or `disputed:<path>`.
5. Every other guaranteed field that carries a value is `verified`, or is handled as below.

**Printed inconsistency.** When a check fails and every value it uses is `verified`, the reading is accepted and the bill itself is wrong. The bill **passes** with `printed_inconsistency:<id>` in `flags[]`, the check reported as failed. In `esgos-1.0` mode the bill follows contract 1.0's own pass definition (`passed: false`, the failing check listed) with the note `printed_inconsistency:<id>`; in `esgos-1.1` mode it passes with the flag.

**Unverified or disputed optional fields.** Contract 1.0 uses `null` to mean "not printed", so the engine never nulls a printed value in the esgOS modes. Any guaranteed field that carries a value but is not `verified` makes the bill `passed: false`, with `unverified:<path>` or `disputed:<path>` in `notes` (1.0) and `review_reasons` (1.1). Dropping unverified optional values belongs to `full` mode, deferred.

**Confirmed values.** A named person in the studio enters or confirms a value from the page image; it becomes a new result version with proof `confirmed`. A bill whose required fields are all `verified` or `confirmed`, with at least one `confirmed`, gets status `confirmed`, never `passed`. In 1.1, `accepted` is true for `passed`, and for `confirmed` when the product's `accept_confirmed` is true (default true, including `esgos`); `accepted_by` is `engine` or `human`.

**Bills that don't pass** still return every field as read, with its evidence and verification, so a person or product can review them.

### 5.3 The reading ladder

Per bill, cheapest and most private first:

1. **Text layer** (genuine digital PDFs only). The **label rule**: for each guaranteed field, the value token immediately right of, or below, the field's printed label, with label synonyms from the profile (`_common.yaml` for the generic ladder). Applied without any model value.
2. **Local OCR.** The same label rule over the OCR words of the rendered page. For a digital PDF this is the second, independent reading; for a scan or photo it is the first.
3. **Model A** reads the whole bill into `data` (guaranteed fields, meters, every line) when the caller allows cloud use and a key is configured. Its guaranteed values and lines are a further reading.
4. **Compare** readings per field and per line. Any two independent readers agreeing on the normalised value: `consensus`.
5. **Disagreement, or only one reading:** Model B reads the field from the full page and its bands, independently, when the caller allows cloud use and a key is configured. If it matches an earlier reading, `consensus`. If all readings differ, the field is `disputed`; if only one exists, `unverified`. There is no further tie-break.
6. **A failing check:** the lines it uses are re-read by Model B from their bands and go through step 5 again. Values change only through agreement, never by choosing the value that makes the arithmetic work.
7. **Budget.** Before each model call, its worst-case cost is compared with what is left of `max_cost_usd`. If a needed reading can't be afforded, the bill ends `budget_exceeded`; it never passes on a single reading.

So every bill needs at least one model reading to verify a field until a layout has anchors (4.2 Stage 4): a local reader and a model agreeing, or two model families agreeing. With no key configured, or with `allow_cloud_model` false, a bill returns `passed: false`, `route: "none"`, `unread_reason: "model_not_allowed"` (or `unreadable` with note `no_model_configured` when cloud use is allowed but no key exists), still carrying every field as read and every check that ran on the local transcription. Each model is told what every field means (`description` in `config/guaranteed_fields.yaml`; prompts `read_bill_v4`, `read_fields_v4`).

### 5.4 Checks

The Developer Guide (Part A, section 6) is normative for G01 to G14, GG01 to GG05, S01 to S06, T01 to T05, profile `rules` and `param()`. Every check declares `detects:` and `proves:` (equality checks) in its definition and has its planted-misread test. Tolerances are the guide's unless listed here.

| Id | Check | Tolerance | Result on mismatch |
| --- | --- | --- | --- |
| G01 | utility name, account number, bill month and net payable present | — | fail |
| G02 | present − past = difference, per meter row | 0.011 | fail |
| G03 | difference × MF = consumption | max(1, 0.006 × MF) | fail |
| G04 | consumption − open access = net units | 1 | fail |
| G05 | \|quantity × rate\| = \|amount\| (rate in % divided by 100) | ₹1, plus profile `qty_x_rate_rel` | fail |
| G06 | items of a section = its printed subtotal | max(₹1, ₹0.01 per item) | fail |
| G07 | current-stage items = `totals.current_charges` | same | fail |
| G08 | arrear-stage items = `totals.arrears` | same | fail |
| G09 | current + arrears + adjustments - due-date rebate = net payable (the net payable is the amount payable by the due date, after the rebate) | ₹1 | fail |
| G10 | billing demand ≥ minimum billable; = max(recorded MD, minimum) | 1% | warn |
| G11 | power factor ≈ kWh ÷ kVAh | 0.006 | warn |
| G12 | due date after bill date; billing days match the period | 1 day | warn |
| G13 | billed units within 0.33 to 3 times the history median | — | warn |
| G14 | the model wrote `extraction_notes` | — | warn |
| G15 | TOD slot units add up to the total register of the same quantity | max(1, 0.006 × MF × slots) | fail (when the profile marks `tod_complete`) |
| G16 | gross kVAh ≥ gross kWh | max(1, 0.006 × MF) | fail (both printed, no net metering) |
| G17 | import − export = net units billed | max(1, 0.006 × MF) | fail (net metering printed) |
| G18 | bill month in the reading period, or within `bill_month_offset` months after it (default 0 to 1) | — | fail |
| G19 | period start before period end | — | fail |
| G20 | a negative amount is printed with a minus or credit marker, or on a line the layout marks `signed` | — | fail |
| GG01–GG05 | gas: presence; (current − previous) × correction = volume; volume × GCV ÷ 251,995.76 = MMBtu; quantity × rate = amount; items + taxes = net amount | guide's | fail |
| X01 | the rule of 5.2 for every required field | — | the bill needs review |
| X02 | every guaranteed field on a passed bill has a page region | — | warn |
| R | the profile's `rules` (5.5) | per rule | per rule's severity |
| S01–S06 | layout conformance, when the version has a `template` | guide's | guide's |
| T01–T05 | printed rates, demand charge, duty and cess, PF band, fixed charge equal the profile's `params`, when the version has them | per formula | **warn**, never fail; verified inputs only, else skip |

### 5.5 Formulas: the recheck of the bill against itself

Every bill goes through the formula recheck after reading, all in code:

1. **Quantity × rate** for every element that prints both (G05), including per-TOD-slot energy lines, demand on billing demand, duty and cess per unit or per cent on their printed base, rebates and surcharges at their printed rate.
2. **Reconciliation:** section subtotals (G06), current charges (G07), arrears (G08), net payable (G09); for gas GG04 and GG05.
3. **Meter arithmetic:** G02, G03, G04, G15, G16, G17.
4. **The discom's rules** (`rules:` in its profile version), written as two arithmetic expressions compared within a tolerance, with the guide's helpers `field()`, `param()`, `item()`, `items_sum()`, `subtotal()`, `meter()`, `abs`, `min`, `max`, `round`. Expressions are parsed with `ast`; only arithmetic, constants and these names are allowed; every number is `Decimal`. A rule declares `detects:`.
5. **Tariff checks** T01 to T05 compare printed rates with the version's `params` where a version carries them (the synthetic layouts do; real discoms' orders are pending-for-user), as warnings.

Each element records its formula-recheck result: `match`, `differs` (with the difference), or `not_computable` with a reason. A passing recheck adds `arithmetic` to the element's amount; it never verifies an element alone. The **tariff-order recheck** (the regulator's order, 4.2 section 5.5 part 2) is deferred: `tariff_recheck` reports every element `not_computable` with reason `tariff_engine_pending`, and `audit_status` is `not_audited`.

### 5.6 Refusals

- `unreadable`: a page local OCR and the text layer cannot read, a password-protected PDF (note `password_required`), or a scan with no model configured when cloud use is allowed (note `no_model_configured`).
- `not_a_bill`: no page classified as an electricity or gas bill; the note names what the file appears to be.
- `model_not_allowed`: a scan or photo with `allow_cloud_model: false` whose fields cannot be verified locally.
- `budget_exceeded`: a needed model reading could not be afforded.
- Required field not printed: `review_reasons` `required_field_not_printed:<path>`; a bill priced only in kVAh passes on `energy.kvah` under 1.1.

### 5.7 Every element captured

- **One catalogue of codes** in `profiles/_common.yaml`, versioned: `energy_charge` (per TOD slot), `demand_charge`, `fixed_charge`, `excess_demand_penalty`, `minimum_charge_difference`, `fppca` (also FPPA, FAC, FSA, VCA), `electricity_duty`, `cess`, `tod_rebate`, `tod_surcharge`, `pf_incentive`, `pf_penalty`, `load_factor_rebate`, `voltage_rebate`, `prompt_payment_rebate`, `digital_payment_rebate`, `other_rebate`, `subsidy`, `regulatory_surcharge`, `cross_subsidy_surcharge`, `additional_surcharge`, `wheeling_charge`, `transmission_charge`, `open_access_banking`, `green_tariff_premium`, `net_metering_credit`, `meter_rent`, `transformer_rent`, `late_payment_surcharge`, `arrears`, `security_deposit_interest`, `tds`, `tcs`, `rounding`, `gas_charge`, `transport`, `vat`, `other`.
- **Every printed line with an amount** becomes a charge element: label as printed, group, kind (`item`, `subtotal`, `info`), stage (`current`, `arrear`, `adjustment`), quantity, rate, unit, amount, TOD slot where printed, code, proof, formula-recheck result.
- **Nothing printed is missed.** G06, G07 and G09 must reconcile, so a bill whose captured elements don't add up to what it prints can't pass.
- **An element is verified** only when two independent readers agree on its amount, with Model B on disagreement. A passing formula recheck adds `arithmetic`; it never proves an element alone.

## 6. The API

### 6.1 Modes

- **`BILLX_API_MODE=esgos-1.0`**: exactly contract 1.0 (`contract/esgos-1.0/contract.md`). No additions appear in responses; a request option outside 1.0 is refused with 400 `bad_request`.
- **`BILLX_API_MODE=esgos-1.1`** (the default): contract 1.0 plus contract 1.1 (6.5): optional fields only; `passed` keeps 1.0's meaning; every 1.0 call and shape unchanged.
- `full` mode and `BILLX_STORAGE=permanent` are deferred with hosting (section 14). Storage is `ephemeral`: files and results deleted within 24 hours.

### 6.1a Intake rows (both modes)

| Input | Result |
| --- | --- |
| A media type outside contract 4.2 | 415 `unsupported_type` |
| A password-protected PDF | `passed: false`, `route: "none"`, `unread_reason: "unreadable"`, note `password_required` |
| A gas bill before Stage 2b | `unread_reason: "unreadable"`, note `gas_not_yet_supported`; from Stage 2b read as gas |
| Water, telecom, other invoices, non-bills | `not_a_bill`, the note naming the type |
| A file mixing bills and other pages | the bills in `bills[]`; the other pages' numbers in the first bill's `notes` |
| `kind: "text"` | the gate doesn't run; pages, text and words as contract 5.3 |
| `allow_cloud_model: false` and a field only a model could prove | `passed: false`, `route: "none"`, `unread_reason: "model_not_allowed"` |
| A printed inconsistency | 1.0: contract's own pass definition, note `printed_inconsistency:<id>`; 1.1: passes with the flag |
| Any layout | passes when the 5.2 rules hold (`accept_unverified_layouts` is true in the embedded image); `profile.status` says the layout's state |

### 6.2 Resolved ambiguities in 1.0 (both modes)

- **`route`** is the most expensive route that produced a returned value: `cloud_model` over `local_model` over `template`. Contract 1.0's `template` is its local, no-model route, so a bill whose returned values came from the text layer or local OCR only reports `route: "template"` (each value's `source` says exactly how); any model call makes it `cloud_model`; `local_model` never occurs in this build; `none` for the refusal reasons.
- **`source`** per value: `template` for an anchored read (deferred), `ocr` for text-layer or local-OCR words without anchors, `model` for a model reading. When several readers agree, `source` is the first of `template`, `ocr`, `model` among them; the exact readers are in `readers` (1.1).
- **`profile`** (`id`, `version`, `status`) is on every bill in both modes, as contract 1.0 section 5.2 requires; `status` is `final`, `draft` or `none`.
- **`schema_version`** reports the engine's real core schema version, `2.0`; contract 1.0's example shows `1.0` (listed for esgOS in pending-for-user).
- **Retention:** files and results deleted within 24 hours; `DELETE` removes them at once.
- **`checks[]`** carries every check run, including skipped ones, with `expected`, `actual`, `tolerance` and `paths` as strings.
- **`data`** is the core schema's bill (section 5 of the Developer Guide, version 2.0).

### 6.3 Health, metrics, logs

`GET /v1/health` as contract 4.1 with `ocr: ready|unavailable` and `cloud_model: configured|not_configured`. `/metrics` (Prometheus counts and timings, same token). JSON logs with `request_id` and the `traceparent` trace id on every line; the no-values-in-logs test runs a synthetic bill with distinctive values and searches every log line, metric and error body for them.

### 6.4 Guaranteed fields

Contract 1.0's section 6 lists, with its paths and required flags, are the floor in every mode, except that from 1.1 `energy.kwh` **or** `energy.kvah` is required rather than `energy.kwh` alone. In `esgos-1.1` mode these are added as optional fields, each verified like any other:

| Path | Unit |
| --- | --- |
| `consumer.name` | |
| `period.due_date` | date |
| `totals.current_charges`, `totals.arrears` | INR |
| `totals.due_date_rebate` | INR: the rebate for paying by the due date that the net payable deducts, as a positive amount |
| `charges.by_code[]`: `code`, `amount` | INR |
| `tariff.category` (the printed tariff code until a mapping to the order's categories exists) | |
| `open_access.re_kwh`, `open_access.non_re_kwh`, `open_access.banked_kwh` | kWh, or kVAh where the bill prints kVAh: stored as printed, never converted; the field's `unit` says which |
| `energy.billed_units` | the units the discom bills (grid units) after open-access set-off, as printed; the field's `unit` says kVAh or kWh |
| `green_tariff.kwh` | kWh |

`config/guaranteed_fields.yaml` is generated from these lists and the contract, and a test checks it against `contract/esgos-1.0/contract.md` section 6 word for word.

### 6.5 Contract 1.1

Written in `contract/esgos-1.1/` (contract text, `openapi.json` generated from the Pydantic models, examples) in Stage 2. It contains exactly:

1. Optional additions per bill: `status` (`passed`, `confirmed`, `needs_review`, `unreadable`, `not_a_bill`, `wrong_document_type`, `model_not_allowed`, `budget_exceeded`; consistent with 1.0's `passed` and `unread_reason`), `review_reasons[]` (`check_failed:<id>`, `unverified:<path>`, `disputed:<path>`, `insufficient_arithmetic`, `required_field_not_printed:<path>`, `layout_drift`, `unknown_utility`, `unverified_layout`, `password_required`, `source_conflict`), `flags[]` (`printed_inconsistency:<id>`), `accepted`, `accepted_by`, `proof_rule_version`, `routes_used[]`, `document_type`, `audit_status` (`not_audited` in this build), `elements[]` (5.7), `tariff_recheck` (every element `not_computable: tariff_engine_pending`), `insights[]` (empty until 4.2 Stage 6a).
2. Per field object: `verification`, `proof` (the levels earned), `readers`.
3. The guaranteed fields of 6.4, as optional.
4. `energy.kwh` or `energy.kvah` required.
5. The resolved ambiguities of 6.2.
6. Optional request options: `contact` (stored with the job for the deferred lead flow; never logged), `account_ref`, `pdf_password` (used once, never stored or logged), `wait` (the response holds the result when the job finishes within 50 seconds). A 1.0 request without them behaves exactly as before.
7. `passed` keeps 1.0's meaning; `accepted` is what esgOS consumes (every `passed` bill and every `confirmed` bill, since `esgos` has `accept_confirmed: true`). This is the one follow-up to the change list's item 6 and is listed in pending-for-user for esgOS's build agent.

`docs/contract-1.1.md` records what 1.1 adds and why.

## 7. Profiles

Everything utility-specific is YAML under `profiles/`, as the Developer Guide section 7 describes: `_common.yaml` (label synonyms for the label rule, the element catalogue and label-to-code map, the default field map), `_template/`, and one folder per discom with `discom.yaml` (`id`, `name`, `state`, `bill_type`, `match` patterns in English and the local script, `extends`) and `versions/<effective-from>.yaml` (`status`, `prompt_hints`, `params` with `params_notes` and `tariff_order`, `label_map`, `field_map`, `rules`, `template`, `tod_complete`, `bill_month_offset`). A version's `status` is `draft` until Stage 11 finalises it; the synthetic layouts `avvnl-ht-synth-v1` and `pvvnl-hv2-synth-v1` get draft profiles in Stage 1 with the synthetic rates as `params`, so T01 to T05 and the rules run end to end. Real AVVNL and PVVNL versions are drafted from the team's confirmed bills as they arrive (Stage 3) and their tariff params are pending-for-user until an order is cited.

`select_version` takes the latest version whose `effective_from` is on or before the bill month; `final` beats `draft` on a tie; a bill older than every version gets the earliest, flagged `out_of_range_version`. The result reports `profile.id`, `profile.version` and `profile.status`.

## 8. The studio and the evaluation

- **Studio** (`billx studio`, 127.0.0.1 only): the confirmation screen of Stage 0.5 with **two-reader pre-fill** from Stage 1 (the engine's own reading: every reader's value, the verification, and the checks); a person confirms or types each guaranteed field and each element amount; seconds per bill recorded; entries go to `~/billx-data/golden/manifest.jsonl`. Every bill is `tuning` until Stage 11.
- **`billx eval`** runs the engine over a set with truth (the synthetic manifest, or the golden manifest) and reports per layout, input kind and route, always with sample sizes: silent errors with the rule-of-three bound, coverage, correct and false refusals, accuracy over attempted per field, formula coverage (the share of elements with a computable recheck), cost and time per bill (median, 95th percentile). On real bills the report is labelled `unmeasured` until a held-out set exists. The report goes in `docs/accuracy/<date>-<set>.md` with no values or names.

## 9. Folder layout

As 4.2 section 10.4, built as far as this build reaches:

```text
billx/
  core/          schema.py (Pydantic v2, Decimal, strict; version 2.0), Value, Reading, units, migrations, settings
  reader/        ENGINE 1
    ingest/      render, text layer, image preparation, page sorting
    ocr/         local OCR (PaddleOCR / RapidOCR), word boxes, row grouping
    identify/    utility detection, version selection, document-type gate
    read/        ladder, label rule, model readers, normalisation, consensus, align
    providers/   openai, anthropic; the only code importing a model SDK; usage and cost
    prompts/     versioned prompt files
    validate/    generic (G), gas (GG), rules (R), conformance (S), tariff (T), readings (X), proof.py (decide), formula recheck
    normalize/   codes, guaranteed fields, field maps
  auditor/       ENGINE 2 (deferred): imports core only
  intelligence/  ENGINE 3 (deferred): imports core only
  platform/
    api/         FastAPI /v1 in esgos-1.0 and esgos-1.1 modes
    store/       JobStore, FileStore, Queue: sqlite and local files
    studio/      confirmation mode with two-reader pre-fill
    evals/       the runner, metrics, reports
    synth/       synthetic bills and documents, planted misreads
  cli.py
profiles/        _common.yaml, _template/, avvnl/, pvvnl/, and the synthetic layouts
config/          guaranteed_fields.yaml (generated), providers.yaml, prices.yaml, studio.yaml, quality.yaml
contract/        esgos-1.0/ (word for word), esgos-1.1/, examples/ (synthetic, per mode), openapi.json
tests/unit/      the builder's, every stage; tests/contract/ the examples against the app
tools/           check_copy.py, identifiers.py, watch/, mac/
docker/          engine.Dockerfile, ocr-check.Dockerfile, compose.yaml
docs/            build-prompt.md, build-prompt-4.2.md, developer-guide.md, the living documents, stage-reports/, accuracy/
```

The import-boundary test (Stage 0.3) stays: `reader/`, `auditor/`, `intelligence/` import `core/` only and are called by `platform/`.

## 10. Measurement

- **Synthetic set** (`billx synth`): two bills per electricity layout per seed as digital PDF, scan and five photo variants; gas in two layouts; water, telecom, invoice, receipt, letter; and from Stage 1 **planted misreads**: for every check and every guaranteed field, one bill with one digit changed, with a truth file saying which check must catch it. `billx eval --synthetic` must report 0 silent errors and 0 false refusals on the clean set and every planted misread caught, on every commit on `main`.
- **Real bills:** the team's bills in `~/billx-data/golden/unconfirmed/`, confirmed in the studio into the manifest. `billx eval --golden` is run by a person (or the builder in an attended session) and its aggregate goes in the stage report, labelled `unmeasured`.
- **What "zero" can claim:** zero silent errors in *n* held-out bills bounds the true rate below about 3 ÷ *n* with 95% confidence; every report states *n*. No held-out set exists in this build, so no accuracy claim is made.

## 11. Stages for this build

Stage 0 is done (12 Oct 2026). The order is 1 → 2 → 2b → 3; each ends with its report, the merge to `main` and the push. After Stage 3 the builder writes `docs/stage-reports/run-2026-10-12.md` and stops; the deferred stages (section 14) wait for the team.

#### Stage 1 — The verification core, the readers and the formulas

```text
STAGE 1. Make a passed bill mean every guaranteed value is verified under one rule, and
every charge rechecked by formula. All items are code, tested on synthetic bills.
1.1 Core schema 2.0 (billx/core/schema.py): Pydantic v2, Decimal everywhere, strict mode,
    Literal enums, frozen results; Value[T] holding value, unit, printed, page, region,
    readings (reader, method, model id and prompt version or None, raw text, normalised
    value, page, region, cost), proof levels, the equality checks it took part in,
    verification and proof_rule_version; a model validator recomputes the verification
    from the evidence through decide() and rejects a mismatch. Bill (the Developer
    Guide's section 5, version 2.0: discom, consumer, connection, period, meters[],
    demand, energy, gas, line_items[], totals, payments, history[], extra[],
    extraction_notes[]) and the contract's field objects produced from it through the
    field map. The guaranteed-field list regenerated from contract 1.0 section 6 and
    6.4, with the test against the contract text. The no-float test walks every model.
    billx synth and the studio moved to the contract's paths.
1.2 Readers (5.1): ingest (pypdfium2 render at 200 dpi, genuine-text-layer detection,
    EXIF rotation, TIFF pages), text_layer and local_ocr words with boxes, the label
    rule with synonyms from profiles/_common.yaml, table-row grouping for elements and
    meter rows; model_a and model_b providers (OpenAI Responses API, Anthropic Messages
    API) with versioned prompts, a cost estimate before and a usage record after each
    call, tested with mocked HTTP; normalisation and array matching; consensus.
1.3 decide() in billx/reader/validate/proof.py and the pass rule: status, review_reasons,
    flags, insufficient_arithmetic, the printed-inconsistency pass, accepted and
    accepted_by, profile.status on every bill. The one-rule test.
1.4 Checks G01 to G20, GG01 to GG05 (the gas section of the schema arrives here so the
    checks exist; the gas reader is 2b), X01, X02, each with detects:, proves: and its
    planted-misread test; the rules engine (R) with the guide's helpers and the ast
    allow-list; S01 to S06 for versions with a template; T01 to T05 as warnings.
1.5 The formula recheck (5.5): quantity x rate per element, reconciliation, meter
    arithmetic, the rules; per-element results; tariff_recheck as tariff_engine_pending;
    the element catalogue and label-to-code map in profiles/_common.yaml; every printed
    line captured and coded.
1.6 The reading ladder (5.3) and the budget check; the document-type gate (5.0) and page
    sorting on the synthetic set; profiles for the two synthetic layouts (draft, with
    params and rules) and discom.yaml with match patterns for AVVNL and PVVNL.
1.7 billx extract PATH... (one result per bill, the same pipeline as the service),
    billx validate JSON..., billx eval --synthetic with every metric of section 8 and
    the planted-misread run; the two-reader pre-fill in the studio.
Done when: every clean synthetic electricity bill (digital PDF, scan, photo) is read end
to end; every digital PDF passes with no model call; every scan and photo passes with
mocked models and returns model_not_allowed or no_model_configured honestly without
them; every planted misread is caught by the check that declares it; billx eval
--synthetic reports 0 silent errors and 0 false refusals; the no-float, one-rule and
import-boundary tests pass; lint and tests green. Merge, push. CONTINUE.
```

#### Stage 2 — The API: contracts 1.0 and 1.1, the image, the 0.1 release

```text
STAGE 2. The engine esgOS runs: contract 1.0 exactly, 1.1 on top, in one container.
2.1 FastAPI /v1 in esgos-1.0 and esgos-1.1 modes: bearer token (BILLX_TOKEN, constant
    time), the five contract calls and nothing else under /v1, kind "text", the intake
    rows of 6.1a, the error table of contract section 8 from one handler, X-Request-Id
    echoed, traceparent logged, BILLX_API_MODE checked at start.
2.2 The embedded store: SQLite job store and a folder per job under BILLX_DATA_DIR, the
    24-hour sweeper every 10 minutes, the in-process bounded queue (BILLX_MAX_JOBS, at
    least 4; 429 with Retry-After beyond BILLX_QUEUE_LIMIT), idempotent request_id
    (same file: same job; different file: 409), jobs surviving a restart.
2.3 Health, /metrics, JSON logs with ids; the no-values-in-logs test.
2.4 contract/esgos-1.1/: contract.md, openapi.json generated from the models and checked
    in CI, examples; contract/examples/ for both modes, at least one per route and one
    per failure, all synthetic, run against the app by tests/contract/.
2.5 docker/engine.Dockerfile with local OCR built in (PaddleOCR on arm64, RapidOCR on
    amd64), non-root, /data volume; docker/compose.yaml; .gitlab-ci.yml: lint, tests,
    the copy check, the identifier search, gitleaks, both images to the GitLab
    registry, the identifier search over the amd64 image, and on a tag the copy to
    esgOS's registry when its variables exist. Memory measured with 4 jobs at once.
2.6 Release 0.1: tag, release notes (contracts served, memory, limits, what
    profile.status and audit_status mean, what is unmeasured), docs/api.md.
Done when: every 1.0 example passes in esgos-1.0 mode and every 1.1 example in
esgos-1.1 mode; every 6.1a row behaves as written on a synthetic input; a bill
submitted over HTTP returns the same result as billx extract; the image builds and
serves a synthetic bill end to end; CI is green on GitLab; lint and tests green.
Merge, push, tag 0.1. CONTINUE.
```

#### Stage 2b — Generic gas reading

```text
STAGE 2b. Read gas bills with no supplier profile.
2b.1 The gas guaranteed fields read by the label rule (text layer, OCR) and the models,
     verified by the same rule; GG01 to GG05 giving arithmetic.
2b.2 The document-type gate sends gas bills to the gas reader; gas_not_yet_supported
     retired; the 6.1a gas row updated.
2b.3 The synthetic gas bills' truth files on the contract's paths; planted misreads for
     the GG checks; the gas examples under contract/examples/; release 0.2.
Done when: every synthetic gas bill passes or is refused for a stated reason; a gas bill
never returns not_a_bill; every GG planted misread is caught; lint and tests green.
Merge, push, tag 0.2. CONTINUE.
```

#### Stage 3 — Real bills: the sample run and the first profiles

```text
STAGE 3. Prove the parser on the team's bills as far as the builder may without reading
them, and leave everything ready for the team.
3.1 billx eval --golden over the confirmed manifest (no bills are confirmed yet; the
    runner and its report are built and tested on the synthetic manifest, and the
    unconfirmed set is run for refusals and reading status only, with no values in the
    report: per discom and input kind, how many were read end to end, how many
    refused, how many needed review and for which reasons).
3.2 Draft discom.yaml for every discom in ~/billx-data/golden/unconfirmed/ (AVVNL,
    PVVNL, MVVNL, MSEDCL, GESCOM, APCPDCL, NPCL, PSPCL, TANGEDCO, DVVNL, TGSPDCL) with
    match patterns from public knowledge of their names (English and local script),
    extends for sister discoms, and no params (pending the orders).
3.3 The studio's review flow on the unconfirmed set: the two-reader pre-fill, each
    reader's value, the checks and the reasons, so a person confirms a bill in one
    pass; docs/runbook.md with the exact steps.
3.4 docs/stage-reports/run-2026-10-12.md: what was built, what is unmeasured, what the
    team must do next (keys, confirm 10 AVVNL and 10 PVVNL bills, the orders), in
    numbered steps.
Done when: the unconfirmed set runs end to end with no crash and a status for every
file; the report holds no value or name; the runbook's steps are exact; lint and tests
green. Merge, push. STOP: write the run report and wait for the team.
```

## 12. Defaults and decisions for this build

The builder uses these without asking and records any departure in `docs/decisions.md`.

- **D1. Repository and CI:** GitLab `icac1/ocr-bill-extraction`, `main`, GitLab CI, GitLab registry. The GitHub workflow is removed.
- **D2. Run mode:** autonomous from 12 Oct 2026; the builder merges and pushes `main`.
- **D3. Model pair:** A `openai:gpt-6.1-sol`, B `anthropic:claude-sonnet-5-5`, from `config/providers.yaml`; unverified until keys exist (`doctor.sh`). Any id a one-token call rejects is listed in pending-for-user and the provider stays mocked.
- **D4. Local OCR:** PaddleOCR 3.x natively and on linux/arm64, RapidOCR on linux/amd64; English models first, Hindi where the profile asks; one reader interface for both.
- **D5. Render:** 200 dpi for OCR, 144 dpi for the studio.
- **D6. `route` for locally verified bills:** `template` (6.2).
- **D7. `profile.status` words:** `final`, `draft`, `none` everywhere.
- **D8. Field paths:** the contract's. The provisional list is retired; the manifest's existing entries (none yet) would be mapped by the table in `docs/decisions.md`.
- **D9. Gas constant:** 251,995.76 kcal per MMBtu, 0.5% (the guide); the synthetic bills' 252,000 falls inside it.
- **D10. Second reader:** per the ladder (5.3), not Tesseract as the guide's section 4 says; Tesseract is not installed and not needed.
- **D11. Sample set:** the 65 files supplied on 12 Oct are unconfirmed; the four in `~/Documents/OCR Application/` were copied to `golden/unconfirmed/unsorted/` unread.
- **D12. Everything in 4.2 not named in section 11 is deferred,** not cancelled (section 14).

## 13. Conflicts resolved in 5.0

| Conflict | Settled as |
| --- | --- |
| `profile.status`: contract 1.0 `final/draft/none` on every bill; 4.2 `verified/draft/none` from 1.1 only | contract 1.0's words, on every bill, in every mode (D7) |
| GitHub, ghcr.io, GitHub Actions (4.2) vs the team's GitLab repository | GitLab everywhere (D1) |
| Provisional guaranteed-field paths (Stage 0) vs the contract's | the contract's (D8) |
| Local OCR in Stage 4 (4.2, O20) vs no keys on the Mac | local OCR in Stage 1; keys add the model readers when placed (D4) |
| Developer Guide section 4 (Tesseract as the second reader, model only on failure) vs 4.2's ladder | 4.2's ladder, extended with local OCR (D10); the guide stays normative for the checks, rules and profiles |
| Three parallel sessions, tmux, `session.sh` (4.2 section 3.1) vs one builder | one session with subagents in worktrees |
| The 14-day sprint day plan vs a 24-hour autonomous run | the stage order of section 11; the sprint's acceptance bars stay as the deferred stages' bars |
| Mac admin items (FileVault, Homebrew, drive, tunnel) in Stage 0's "done when" | moved to hosting (deferred); Stage 0 is closed |
| The change list's item numbers (its item 5 is 4.2's "change 4") | the saved file's numbers in `docs/decisions.md` |
| GG03's constant (guide 251,995.76; synth 252,000) | the guide's, within tolerance (D9) |
| `schema_version` "1.0" in the contract example vs 2.0 | 2.0, listed for esgOS |
| 4.2 6.2 `profile` "present in esgos-1.1 and full modes" vs contract 1.0 requiring it | present in every mode |
| Staged run mode through day 4 (O9) vs the team's instruction of 12 Oct | autonomous (D2) |
| Planted-misread tests in Stage 11 (4.2 rule 4) vs "no errors" now | written with each check, from Stage 1 (invariant 10) |
| `route` has no honest value for a bill verified locally without anchors | `template`, with `source: ocr` per value (D6) |

## 14. Deferred, with where each lives in 4.2

Hosting on the Mac behind a tunnel, Postgres, MinIO, `full` mode, permanent storage, terms, erasure, tenants and product keys (4.2 sections 6.1, 6.3, 6.6, 9A, 10, Stage 3); anchors, photo preparation and the quality gate (Stage 4); the tariff engine and state orders (5.5 part 2, Stage 5b); insights, leads and intelligence (9, Stage 6); the web app and live view (9D, Stage 7); the assistant (9C, Stage 8); MCP and the comparison lab (7, 9B, Stage 9); coverage state by state (Stage 10); the independent review, the full golden set and the launch gates (Stage 11); public launch (Stage 12). Each resumes from `docs/build-prompt-4.2.md` when the team says so; its stage numbers are unchanged so the change list's references hold.

## 15. What people must supply

1. Keys in `~/billx/.env`: `BILLX_OPENAI_API_KEY`, `BILLX_ANTHROPIC_API_KEY`. Without them the parser verifies digital PDFs and refuses scans honestly.
2. Confirmed bills: 10 AVVNL and 10 PVVNL in the studio (`docs/runbook.md`), then the other discoms.
3. The tariff orders for AVVNL (RERC) and PVVNL (UPERC) for the sample months, so `params` can be cited.
4. GitLab: shared runners enabled on the project; the CI variable `CLIENT_IDENTIFIERS`; `ESGOS_REGISTRY` and `ESGOS_REGISTRY_KEY` when esgOS grants them.
5. esgOS: agreement to consume `accepted` (6.5 item 7); its registry path.

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


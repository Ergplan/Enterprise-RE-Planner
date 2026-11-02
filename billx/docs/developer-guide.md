# billx Developer Guide: super billx (Part A)

Oct 7, 2026 · @joulewise · version 2, Part A only

This is Part A of "billx Developer Guide: super billx" (version 2), unchanged. Part B (the version 2 build prompt) is **replaced** by `docs/build-prompt.md` (the current build prompt, version 4.2) and is left out of this file; where Part A mentions Part B, the build prompt applies. Part C, the esgOS contract 1.0, is in `contract/esgos-1.0/contract.md`.

This file is normative for the generic checks G01–G14, layout checks S01–S06, gas checks GG01–GG05, tariff checks T01–T05, profile `rules` and `param()`, and the studio. Where `docs/build-prompt.md` changes any of these, the build prompt wins.

# Part A. Developer guide

## 1. What super billx is

billx turns Indian electricity bills into validated JSON. Super billx is the same engine, made into the bill reader behind esgOS:

- **A headless HTTP service in one container.** esgOS sends it a bill file. It returns the bill's values, where on the page each came from, and whether the bill's own arithmetic holds.
- **It does all the heavy lifting of reading bills:** every utility, every layout, phone photos, scans and digital PDFs. esgOS does none of it.
- **One copy runs inside esgOS's own stack,** on its private internal network. Bills never leave esgOS's infrastructure, except to OpenAI when esgOS allows it for that bill.

**esgOS is the master; super billx serves it.**

- **The contract (Part C) is set by esgOS.** Super billx implements it exactly: no extra calls, no extra or renamed fields, no different meanings. A change goes to the esgOS team as a proposal, and only a new contract version from esgOS changes it.
- **They meet only at the contract.** esgOS never reviews or edits billx's code, and billx never reaches into esgOS.
- **esgOS has no review step for bills.** A bill that super billx marks `passed`, and that also passes esgOS's checks against the account's earlier bills, goes straight into a company's monthly energy data and from there into its emissions. So **`passed` must mean proven** (section 2).

**What stays from billx:** the design rules, the core schema, the three validation layers, the utility profiles and their versions, and the provider interface.

**What changes:**
- The service replaces the command line as the way bills arrive.
- Local reading (the PDF's text layer and PaddleOCR) comes before any model.
- Every value carries its evidence.
- Every key value is read twice.
- Gas bills are added.
- The review screen becomes the **profile studio**: a development tool for building test sets and utility profiles, never part of the service.

## 2. Design rules every change must keep

- **The model transcribes, it never calculates.** Every number in `data` must be printed on the bill. All arithmetic lives in validation, which is where misreads are caught.
- **Passed means proven.**
  - A bill passes only when no check fails and every required field is present.
  - A check whose inputs are missing reports `skip`, never `pass`.
  - Doubt fails a bill; it never passes it. A bill held back is a small cost; a wrong number in a company's emissions is a large one.
- **Every value shows where it came from:** the page, the region on the page, and the text exactly as printed.
- **Read each key value twice.** Every guaranteed field (Part C, section 6) is read by two independent means. A disagreement is settled by re-reading that region, never by picking one reading.
- **Cheapest and most private route first:**
  1. the PDF's own text layer, when there is one
  2. local OCR with the utility's template
  3. the cloud vision model, only when the caller allows it, within its budget. With `allow_cloud_model` false, only the text layer, local OCR and templates run (Part C, section 4.2).
- **One core schema for every utility.** Fixed fields only for what every bill has; charges are captured as line items exactly as printed. Utility knowledge lives in YAML profiles, so onboarding a utility needs no code.
- **Utility versions are never edited in place.** A finalised version is frozen, and a layout or tariff change is a new version with a later `effective_from`. Tariff numbers cite the regulator's order they came from.
- **Exact numbers.** Every number is an exact decimal, from reading to response. Never a float.
- **Private by default.**
  - Files and results are deleted within 24 hours.
  - No bill value, name or account number is ever written to a log, a metric, a trace or an error message.
  - Real bills never enter git.
- **Providers and OCR are pluggable.** OpenAI is the default model provider, and Claude shares the same interface. The page image is authoritative over any OCR text.

## 3. What super billx does

| Area | Capability |
| --- | --- |
| **Inputs** | PDF (digital or scanned), JPG, PNG, HEIC, WebP and TIFF, up to 25 MB and 30 pages. Phone photos in any orientation. Several bills in one file. HT and LT bills, with time-of-day (TOD) slots, net metering and open access. English, Hindi and bilingual bills. Electricity and gas. |
| **Page preparation** | Renders PDF pages and reads the text layer with each character's position. For photos: EXIF rotation, document edge detection, perspective correction, deskew and crop. |
| **Quality gate** | Before reading, catches blur, glare, cut-off edges and low resolution. A bill too poor to read comes back unread, with a note saying what to retake ("Retake the photo: glare across the meter readings"). It is refused, never guessed. |
| **Page sorting** | Splits a file into bills (by bill number and account), skips pages that aren't bills (payment receipts, advertisements, terms), and says `not_a_bill` when there is none. |
| **Reading routes** | Cheapest and most private first: the PDF's text layer, then local OCR (PaddleOCR) with the utility's template, then a vision model. The model is used only for an unknown layout, or when a check fails and the caller allows it. Escalation re-reads only what failed, from a zoomed crop, where it can. |
| **Two readings** | Every guaranteed field is read twice by independent means: the text layer or PaddleOCR against a second reader on the field's crop, or the template against the model. A disagreement triggers a zoomed re-read; one that stays unresolved fails the bill. |
| **Proof by arithmetic** | Generic checks on every bill (readings, multiplying factor, quantity × rate, subtotals, net payable, power factor, TOD sums, kVAh against kWh). Each utility's own rules (duty, cess, fuel surcharge, power-factor incentive or penalty, minimum demand). Layout conformance and drift. Gas checks (volume, GCV, energy, amount). |
| **Tariff checks** | Printed rates compared with the regulator's tariff order for the consumer's category and month. A difference is a warning, not a failure: it can mean the utility billed wrongly, which is worth knowing. |
| **Evidence** | Every guaranteed value carries its page, its region on the page and the text as printed. Model-read values are matched back to the words on the page to find their region. |
| **Utility knowledge** | Profiles for every utility esgOS's clients use, onboarded family by family (sister utilities on one billing system share a base). Each has layout versions by effective month, templates with anchors for the template route, and tariff parameters with their orders. Drift is detected and a new draft version proposed for a person to finalise. |
| **Learning** | esgOS's corrections come back as feedback and are counted per utility, version, field, route and model. A field corrected repeatedly on one layout opens a profile task. Nothing is learned automatically into a final version. |
| **Text reading** | `kind: "text"` returns page text with word positions, for esgOS's scanned documents that aren't bills. |
| **Privacy and cost** | Local first. Cloud models only when allowed and within each job's budget. Results cached by file hash and versions. Files deleted within 24 hours. No values in logs. The image runs offline, with OCR models built in. |
| **Measurement** | A golden set of hand-checked bills per layout in a private bucket. A nightly evaluation reports silent errors, accuracy, coverage, cost and time, always with sample sizes. Zero silent errors is the release gate. |
| **Operations** | One CPU container, health and version, Prometheus metrics, JSON logs carrying esgOS's request and trace ids, a bounded queue that answers 429 when full, and graceful shutdown. Jobs survive a restart. |

**What super billx doesn't do.** These are esgOS's job:
- checks across bills: continuity of readings, period gaps and overlaps, duplicates, month-on-month change
- mapping accounts to sites, and splitting periods into calendar months
- emissions, factors and the calculation trace
- storing bills, and any screen for end users

## 4. How a bill is read

`POST /v1/jobs` queues a job. A worker then takes one file through these steps:

1. **Admit.** Check the type, size and page count (Part C, section 4.2), and hash the file. A cached result for the same hash and the same engine, profile and schema versions is returned as it is, with empty `usage`.
2. **Prepare the pages.**
   - Render every PDF page at 300 dpi with pypdfium2, and read its text layer with character boxes.
   - For a photo: apply EXIF rotation, find the document's edges, correct the perspective, deskew and crop.
3. **Gate on quality.** Measure blur (variance of the Laplacian), glare (saturated regions over text), resolution (character height in pixels) and cut-off edges. A page below the thresholds in `config/quality.yaml` ends the bill with `unreadable` and a note on what to retake.
4. **Find the words.**
   - A digital PDF's text layer gives exact words with boxes.
   - Otherwise PaddleOCR gives words with boxes and confidences, in English and Hindi, plus other scripts a profile names.
5. **Sort the pages.** Classify each page (bill, continuation, receipt, other) and group the bill pages into bills by bill number and account.
6. **Identify the utility and version.** Match each utility's `match` patterns against the words. Read the bill month early from the template's anchors when the layout is known, to pick the version in force. Otherwise use the latest version, and re-select after reading.
7. **Read, by route.**
   - **Template:** a finalised version with anchors reads every guaranteed field from the words. No model call.
   - **Model:** the vision model reads the whole bill into the core schema. It receives the full page plus three overlapping horizontal bands at the provider's maximum image size, the profile's prompt hints, and the JSON schema. This route runs for an unknown layout, or when the template route leaves a check failing or a required field missing. It runs only when the caller allows a cloud model, and within budget. A local model is deferred (B2 rule 17).
8. **Read twice (the X checks).** Each guaranteed field gets a second, independent reading:
   - On the template route, the second reader (Tesseract) runs on the field's crop. A digital text layer counts as exact.
   - On the model route, the value is matched against the words found in step 4.

   A disagreement is re-read from a zoomed crop: by the model if allowed, otherwise by a third local read. If it still disagrees, check X01 fails for that field.
9. **Align.** Every model-read value is matched to the words on its page, after normalising digits, separators and Devanagari numerals, preferring the match nearest its label. That gives its region. A guaranteed field that can't be placed gets `region: null` and a warning.
10. **Validate.** Run the generic checks (G), the utility's rules (R), the layout checks (S), the tariff checks (T, warnings only) and the two-reading checks (X) (section 6). Set `passed`.
11. **Respond.** Build the guaranteed fields from `data` through the profile's field map, as exact decimal strings with units. Then add the checks, the route, the profile, `usage` with the cost of every model call, and the time taken. Keep the job until `DELETE` or 24 hours.

## 5. Data model

One Pydantic model, `billx.core.schema.Bill`, describes every bill from every utility. All models use `extra="forbid"`, so a misspelled key is a validation error, not silently dropped.

**Changes in super billx (core schema 2.0):**

- **Numbers are `Decimal`** everywhere, serialised as strings. A migration step upgrades stored 1.x bills.
- **`bill_type`:** `electricity` or `gas`.
- **`period.reading_type`:** `actual`, `estimated`, `assessed` or `provisional`, as printed or implied by a printed marker such as "E" or "AVG".
- **`period.bill_kind`:** `regular`, `revised`, `supplementary` or `final`.
- **`energy.open_access_kwh` and `energy.green_tariff_kwh`,** where printed.
- **A `gas` section:** `volume_scm`, `gcv_kcal_per_scm`, `energy_mmbtu`, the pressure and temperature correction factor as printed, and the readings.
- **`evidence`:** for each guaranteed field, its page, region, printed text, source and the readings that were compared. It is kept internally and used to build the contract's field objects.

The contract's guaranteed fields (Part C, section 6) are produced from the schema through a **field map**: a default in `profiles/_common.yaml`, overridable per version. For example, `energy.kwh` comes from `energy.billed_units` when its unit is kWh, and otherwise from the kWh meter rows' net units.

| Section | Holds |
| --- | --- |
| `discom` | name as printed, short code, state, issuing office |
| `consumer` | name, address, `account_number` (KNO / AC No / CA No), `service_connection_number`, GSTIN, PAN |
| `connection` | tariff code and category, supply kV, metering side, meter number, contract demand, minimum billable demand, sanctioned load |
| `period` | `bill_month` (YYYY-MM), bill number, bill / due / disconnection dates (ISO), reading period, billing days, `reading_type`, `bill_kind` |
| `meters[]` | one row per printed meter register or TOD slot |
| `demand`, `energy` | recorded and billing demand; billed units and unit (kWh or kVAh), gross kWh/kVAh, open access, green tariff, off-peak, PF, load factor |
| `gas` | volume, GCV, energy, correction factor, readings (gas bills) |
| `line_items[]` | every charge, rebate, duty, arrear and adjustment, as printed |
| `totals` | current charges, arrears total, net payable, payable after due date |
| `payments`, `history[]` | previous bill and last payment; past months' consumption |
| `extra[]` | any other printed label/value pair worth keeping |
| `extraction_notes[]` | the model's own notes on unreadable, ambiguous or misaligned readings |

**Line items carry the bill's arithmetic.** Two fields tell validation how a line adds up:

| Field | Values | Meaning |
| --- | --- | --- |
| `kind` | `item` | a charge that adds into the bill |
|  | `subtotal` | a printed total of the items in the same `group` |
|  | `info` | a memo figure not added in (rate bases, "EC for PF", info-only tables) |
| `stage` | `current` | part of this period's charges |
|  | `arrear` | arrears, LPS, previous-period items |
|  | `adjustment` | applied after current + arrears (TDS, rounding) |

`group` is the printed section heading or letter, and `label` is the printed label, spelling mistakes included. `quantity`, `rate` and `rate_unit` are filled only when printed on the same line, which enables the quantity × rate check.

**Meter rows** carry `label`, `quantity` (kWh, kVAh, kVA, kW, kVArh, other), `tod_slot`, `present`, `past`, `difference`, `multiplying_factor` with `multiplying_factor_printed` (for example `40000/6`), `gross_units`, `open_access_units` and `net_units`.

**Schema versioning.** `SCHEMA_VERSION` is reported in every result. Bump the minor version for additive changes and the major version for breaking ones, and register an upgrade step in `billx/core/migrations.py`. The core schema is billx's own; the contract's fields are what esgOS sees, and they change only with the contract.

## 6. Validation

`validate(bill, profile)` runs five layers and returns a list of checks, each `pass`, `fail`, `warn` or `skip`. `passed` is true only when no check fails and every required guaranteed field is present. A check whose inputs are missing reports `skip`, never `pass`. Every check records `paths`, the guaranteed or schema paths it concerns.

**Layer 1: generic checks** (`billx/validate/generic.py`), which need no utility configuration. G01 to G14 carry over from billx; G15 onwards are new.

| Id | Check | Tolerance | On mismatch |
| --- | --- | --- | --- |
| G01 | utility name, account or SC number, bill month, net payable present | — | fail |
| G02 | present − past = difference, per meter row | 0.011 | fail |
| G03 | difference × MF = consumption | max(1, 0.006 × MF) | fail |
| G04 | consumption − open access = net units | 1 | fail |
| G05 | \|quantity × rate\| = \|amount\| (rate in % divided by 100) | ₹1, plus profile `qty_x_rate_rel` | fail |
| G06 | items of a section = its one printed subtotal | max(₹1, ₹0.01 per item) | fail |
| G07 | current-stage items = `totals.current_charges` | max(₹1, ₹0.01 per item) | fail |
| G08 | arrear-stage items = `totals.arrears_total` | same | fail |
| G09 | current + arrears + adjustments = net payable | ₹1 | fail |
| G10 | billing demand ≥ minimum billable; = max(recorded MD, minimum) | 1% | warn |
| G11 | power factor ≈ kWh / kVAh | 0.006 | warn |
| G12 | due date after bill date; billing days match the reading period | 1 day | warn |
| G13 | billed units within 0.33 to 3 times the history median | — | warn |
| G14 | the model wrote `extraction_notes` | — | warn |
| G15 | TOD slot units add up to the total units | 1 kWh | fail |
| G16 | kVAh ≥ kWh where both are printed | 0 | fail |
| G17 | net metering: import − export = net units billed | 1 kWh | fail |
| G18 | the bill month falls in the reading period, or is the month after it ends | — | fail |
| G19 | the period from date is before the period to date | — | fail |
| G20 | no guaranteed amount or quantity is negative, except credits printed as negative | — | fail |

G05 is deliberately tight: Indian tariffs print exact rates (6.048, 7.100), so a one-digit misread of a ₹14.8 crore amount fails it. A utility that prints rounded rates loosens it in its profile with `generic_tolerances: {qty_x_rate_rel: 0.0005}`.

**Gas checks** (`billx/validate/gas.py`):

| Id | Check | Tolerance | On mismatch |
| --- | --- | --- | --- |
| GG01 | customer id, period, net amount and volume or energy present | — | fail |
| GG02 | (current − previous reading) × correction factor = volume | 0.5% | fail |
| GG03 | volume × GCV ÷ 2,51,995.76 = MMBtu, where all three are printed | 0.5% | fail |
| GG04 | quantity × rate = amount, per line | ₹1 | fail |
| GG05 | items + taxes = net amount | ₹1 | fail |

**Layer 2: utility rules** (`billx/validate/rules.py`), written in the version YAML as two arithmetic expressions compared within a tolerance. They carry over unchanged from billx:

```yaml
rules:
  - id: pvvnl.electricity_duty
    description: ED = ED% x (total demand & energy charges + FPPA surcharge)
    severity: error            # error -> fail, warning -> warn
    tolerance: 1               # absolute; rel_tolerance also accepted
    actual: item("Electricity Duty", kind="item")
    expected: param("ed_pct") / 100 * (subtotal("Current Demand and Energy") + items_sum("FPPA|Fuel and Power Purchase", kind="item"))
```

| Helper | Returns |
| --- | --- |
| `field("energy.billed_units")` | a dotted path into the Bill |
| `param("ed_pct")` | a number from the version's `params` (or the latest `params_history` entry in force) |
| `item(label_regex, group=None, kind=None)` | the amount of exactly one matching line; none → skip, several → warn |
| `items_sum(label_regex, group, kind, stage)` | the sum of matching amounts (0 if none) |
| `subtotal(group_regex)` | the subtotal line of a group |
| `meter(label_regex, attr="gross_units")` | an attribute of exactly one meter row |
| `abs`, `min`, `max`, `round` | as in Python |

Regexes are case-insensitive searches. Expressions are parsed with `ast`, and only arithmetic, constants and these helper names are allowed. `__import__`, attribute access, lambdas and subscripts are refused at evaluation and when a version is saved. All arithmetic uses `Decimal`.

**Layer 3: layout conformance** (`billx/validate/conformance.py`), run when the version has a `template`. Unchanged from billx:

| Id | Check |
| --- | --- |
| S01 | fields the layout always carries are present |
| S02 | every required template line was found |
| S03 | no line items outside the template (warn) |
| S04 | meter rows match the template (warn) |
| S05 | matched lines use the template's `kind` and `stage` (warn) |
| S06 | layout drift: total differences ≥ `drift_threshold` (default 3) |

Below the drift threshold, S01 and S02 fail, because a few differences usually mean something was missed. At or above it they downgrade to warnings and S06 flags drift, because many differences usually mean the utility changed its layout.

**Layer 4: tariff checks** (`billx/validate/tariff.py`), always warnings. They compare the bill with the version's `params`, which come from the regulator's tariff order:

| Id | Check |
| --- | --- |
| T01 | each printed energy rate (per TOD slot where it applies) equals the order's rate for the tariff category and month |
| T02 | demand charge = billing demand × the order's demand rate |
| T03 | electricity duty and cess percentages equal the order's or the state's |
| T04 | the power-factor incentive or penalty falls in the order's band for the printed PF |
| T05 | the fixed or minimum charge equals the order's for the category |

A T warning that holds across many bills of one utility usually means a new tariff order. That's a new version, not a misread.

**Layer 5: two readings** (`billx/validate/readings.py`):

| Id | Check | On mismatch |
| --- | --- | --- |
| X01 | every guaranteed field's two readings agree, after a zoomed re-read where they first disagreed | fail |
| X02 | every guaranteed field on a passed bill could be placed on the page | warn |

**Normalisation** maps each line to a common code so bills compare across utilities: first the matching template entry's `code`, then the version's and the utility's `label_map`, then `profiles/_common.yaml`, else `other`. Amounts by code are kept as exact decimals.

## 7. Utility profiles and versions

Everything utility-specific lives in YAML: a folder per utility with an identity file and one file per version, where a version is one layout and tariff period. Adding a utility or a new tariff year is a data change reviewed like code, never a code change.

```
profiles/
  _common.yaml                 label regex -> common code; the default field map
  _template/                   copy this to onboard a utility (folders starting with _ are skipped)
  avvnl/
    discom.yaml                id, name, state, bill_type, match, label_map, extends
    versions/
      2023-04.yaml
  pvvnl/
    discom.yaml
    versions/
      2025-04.yaml             4 TOD slots
      2026-06.yaml             8 TOD energy lines + open-access table
```

**Where profiles are read from.** The service reads only the profiles built into its image, versioned together as `profiles_version` (Part C, section 4.1). A product can't change them. The studio and the command line also read a workspace's `profiles/` and `BILLX_PROFILES_DIR`, ahead of the built-ins, for profile work in progress.

**Version file keys**

| Key | Purpose |
| --- | --- |
| `version`, `effective_from` | version id (the file name) and the first bill month it applies to (YYYY-MM) |
| `status` | `draft` or `final`; final files are frozen |
| `prompt_hints` | layout quirks added to the extraction prompt |
| `params`, `params_notes` | tariff numbers used by the rules and the tariff checks, each with its unit and source |
| `tariff_order` | new: the order the params come from (regulator, number, date, link). Required for `final`. |
| `params_history` | optional dated params inside one version (the latest `from` ≤ bill month applies) |
| `generic_tolerances` | per-utility loosening of generic checks (`qty_x_rate_rel`) |
| `label_map` | regex on `"<group> :: <label>"` → common code; overrides `_common.yaml` |
| `field_map` | new: overrides of the default map from schema paths to the contract's guaranteed fields |
| `rules` | utility arithmetic (section 6) |
| `template` | the finalised layout: `required_fields`, `meters`, `line_items`, `drift_threshold`, and new `anchors` |
| `based_on`, `review_notes` | which golden-set bills it was learned from; rule pass rates on them |
| `finalized_by`, `finalized_at` | written by finalise |

**Anchors (new)** turn a finalised template into the template route. Each anchor names a guaranteed field, a label pattern (in every script the bill prints it), and where the value sits relative to the label: right of it, below it, or in a table column. It can also give the value's expected pattern. The template route reads a value only when its anchor is found once and the value matches its pattern; otherwise that field goes to the next route.

**Sister utilities.** `extends: avvnl` in `discom.yaml` inherits another utility's labels, rules, anchors and field map. A version overrides only what differs. JVVNL and JdVVNL start from AVVNL, and MVVNL, DVVNL, PuVVNL and KESCo from PVVNL.

**Which version checks a bill.** `select_version` takes the latest version whose `effective_from` is on or before the bill month; on a tie, `final` beats `draft`. A bill older than every version gets the earliest one, flagged out of range. The result reports the version used (Part C, section 5.2).

**Lifecycle of a version**

1. **Hand-check bills** of the new period in the studio. Approved bills become golden-set references.
2. **Propose** a draft from them, on the studio's Schemas page or with `billx discom propose`. A line seen in at least 90% of the bills is `required`, and labels that differ only in digits collapse into a `label_pattern`. Anchors are proposed from where each guaranteed field sat on the approved bills.
3. **Edit** the draft: required flags, codes, params with their `tariff_order`, rules and anchors. Saves go through `check_version`.
4. **Finalise.** It needs a template, anchors for every guaranteed field the layout prints, and a `tariff_order`. It sets `status: final` and re-checks every golden-set bill of that utility.
5. **Next period:** when S06 drift or a run of T warnings appears, the studio opens a draft proposal for that month. A person finalises it; nothing is finalised automatically.

**Onboarding a utility**

1. Copy `profiles/_template/` to `profiles/<id>/`. Set `id`, `name`, `state`, `bill_type`, and the `match` patterns that appear on its bills (the full name and abbreviation, in English and the local script). Set `extends` if it shares a billing system with a utility already done.
2. Collect and hand-check 10 to 20 of its bills in the studio, mixing PDFs, scans and photos. The dev team decides the exact number (B11 O5).
3. Add `prompt_hints` for quirks the failures reveal, and the state's duty and cess rules, with params from the tariff order.
4. Propose, edit and finalise. The nightly evaluation then covers the utility.

## 8. The service

`billx serve` runs the service (FastAPI on uvicorn), which implements Part C exactly. Implementation notes:

- **Calls:** `GET /v1/health`, `POST /v1/jobs`, `GET /v1/jobs/{job_id}`, `DELETE /v1/jobs/{job_id}` and `POST /v1/feedback`, nothing else under `/v1`. `/metrics` (Prometheus; counts and timings only) sits outside `/v1` and needs the same token.
- **Authentication:** `Authorization: Bearer` compared in constant time with `BILLX_TOKEN`.
- **Jobs:**
  - A SQLite job store and a folder per job under `BILLX_DATA_DIR`, so jobs survive a restart.
  - Up to `BILLX_MAX_JOBS` jobs run at once (at least 4, as the contract says). CPU work runs in a pool of `BILLX_WORKERS` processes, and model calls wait asynchronously.
  - Beyond `BILLX_QUEUE_LIMIT` queued jobs, the service answers 429 with `Retry-After`.
- **Idempotency:** the same `request_id` with the same file returns the same job; with a different file it returns 409.
- **Deletion:** `DELETE` removes the folder and the result at once. A sweeper deletes anything older than 24 hours, every 10 minutes.
- **Model budget:**
  - Before each model call, its worst case (input tokens and maximum output, priced from `config/prices.yaml`) is checked against what's left of `max_cost_usd`. A call that might exceed it is not made, and the bill ends `budget_exceeded`.
  - With `allow_cloud_model` false, only the text layer, local OCR and templates run, and a bill that would need a model ends `model_not_allowed`.
- **Feedback:** stores the path, utility, profile version, route, model and whether the value was right. The values themselves are deleted within 24 hours.
- **Errors:** exactly Part C, section 8, from one handler. A message never contains a bill value.
- **Tracing:** the trace id from `traceparent` and the `X-Request-Id` are written on every log line, so esgOS can follow a bill. Nothing is exported over the network (Part C, section 3); `X-Request-Id` is echoed.

## 9. The profile studio (development only)

The former review screen and workspace (sections 8 and 9 of the original guide) carry over unchanged in behaviour, renamed `billx studio <ws>` and bound to 127.0.0.1. The dev team uses it to:

- hand-check golden-set bills: an approved bill is a reference, and the approval gate still blocks on failing checks without a reason
- propose, edit and finalise utility versions, including anchors and tariff orders
- see statistics: corrections per field and utility, and esgOS's feedback

The studio is never started by the service, never exposed outside the developer's machine, and never shipped as an esgOS feature. esgOS has no review step.

## 10. Command line

All commands are subcommands of `billx`.

| Command | Does |
| --- | --- |
| `billx serve` | run the service (section 8) |
| `billx studio WS` | the profile studio (section 9) |
| `billx init WS`, `ingest`, `run`, `export`, `stats` | the studio's workspace commands, as before |
| `billx discom list / propose / finalize` | utility versions, as before |
| `billx extract PATH...` | one result per bill, through the same pipeline as the service |
| `billx validate JSON...` | re-run checks on results |
| `billx compare PRED REF` | field-level accuracy against hand-checked references |
| `billx eval` | the golden-set evaluation and its report (section 11) |
| `billx examples` | regenerate `contract/examples/` and check them against the running service |
| `billx synth` | render synthetic bills for a profile's layout with known values |
| `billx schema`, `billx profiles` | print the core schema; list utilities and versions |

## 11. Testing and accuracy

- **Synthetic bills, never real ones, in the repository.** `billx synth` renders bills for a profile's layout with known values. It produces PDFs, and photo-like variants with rotation, perspective, blur, glare and low resolution. Unit, service and contract tests use only these.
- **Planted misreads.** Every check has a test that a planted error trips it while the clean synthetic bill passes.
- **Contract tests** run every example in `contract/examples/` against the running image: one per route, one per `unread_reason`, one with a failing check, and one per error code.
- **The privacy test** runs a synthetic bill with distinctive values, then searches the logs, metrics, traces and error bodies for them, and fails on any hit.
- **The golden set** is the dev team's hand-checked real bills, in a private bucket in India (B8), fetched at run time and never committed. `billx eval` reports, per utility, input kind (digital PDF, scan, photo) and route:
  - **silent errors:** bills marked passed with any guaranteed field wrong. **The release gate is 0.**
  - **accuracy over attempted:** per guaranteed field, on passed bills
  - **coverage:** the share of bills passed
  - **correct refusals:** poor or unreadable bills refused rather than read
  - **cost per bill** (median and 95th percentile) and **time per bill** (median and 95th percentile)

  Every number carries its sample size, and a small sample makes no claim against a target.
- **The nightly evaluation** runs the golden set in CI and writes `docs/accuracy/<date>.md`. A rise in silent errors fails the run.

## 12. Operations and data handling

- **One CPU image** with OCR models built in: no downloads at runtime, a non-root user, and a read-only root filesystem except `BILLX_DATA_DIR`. Port 8080; the service name in esgOS's Compose file is `bill-engine`.
- **Memory.** esgOS runs it beside its app, database and other containers on one machine, so the image must stay small. Each release states its memory need, measured with 4 jobs at once.
- **Bills carry personal and commercial data:** consumer names, addresses, PAN, GSTIN, account numbers and amounts.
  - In the service they live only in the job folder, for at most 24 hours.
  - In the studio they live in a workspace on an encrypted disk.
  - In the golden set they live in the private bucket.
- **The repository holds no real bills** after Stage 0. The CI identifier search fails if one returns.
- **Model calls send page images to OpenAI** only when esgOS allows it for that bill. esgOS records the owner's agreement and passes it as `allow_cloud_model`.
- **API keys come from environment variables only.**

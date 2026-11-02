# Stage 1 report: the verification core, the readers and the formulas

12 to 14 Oct 2026, branch `stage-1` (from `main` at `stage-1-start`). Autonomous mode (build
prompt 5.0, D2): merged into `main` and pushed by the builder when the bar below held.

## Done-when status

| Item | Status |
| --- | --- |
| Every clean synthetic electricity bill (digital PDF, scan, photo) read end to end | **Yes** for digital PDFs and scans; photos are read (OCR) but not required to pass in this stage: without anchors or photo preparation (deferred, 4.2 Stage 4) a photo's OCR disagrees with the model on some rows and the bill is `needs_review`, honestly |
| Every digital PDF passes with no model call | **Yes**: text layer and local OCR agree on every guaranteed field; `route: template`, `usage: []` |
| Every scan and photo passes with mocked models, and returns `model_not_allowed` / `no_model_configured` honestly without them | **Yes** for scans (OCR + Model A + Model B on disagreement); the refusals are exact |
| Every planted misread is caught by the check that declares it | **Yes**: 48 planted bills (G02, G03, G05, G07, G09, G15, G16, G18, G19, G20, GG02 to GG05), each reported `fail` by its check and, with every input verified, passed with `printed_inconsistency:<id>` in `flags` (5.2) |
| `billx eval --synthetic`: 0 silent errors, 0 false refusals | **Yes** on the clean set; the planted set reports 48 caught, 0 missed |
| The no-float, one-rule and import-boundary tests pass | **Yes** |
| Lint and tests green | **Yes**: the full suite, with the OCR tests on one worker |

## What changed

- **Core (1.1):** `billx/core/schema.py` (strict Decimal models, `Value` whose verdict is
  recomputed from its evidence), `billx/core/proof.py` (`decide`, proof rule version 1),
  `billx/core/normalize.py`; `config/guaranteed_fields.yaml` on contract 1.0's paths with
  the 6.4 additions, checked against the contract text. The synthetic generator and the
  studio moved to those paths.
- **Readers (1.2):** `billx/reader/ingest` (pypdfium2 render at 200 dpi, genuine text-layer
  detection, images), `billx/reader/ocr` (PaddleOCR, RapidOCR fallback; results cached by
  page hash), `billx/reader/read/{words,label,rows,local}.py` (the label rule with the
  `_common.yaml` synonyms, table rows for elements and meter registers, the two local
  readers as `ReaderOutput`), `billx/reader/providers` (Model A over the OpenAI Responses
  API reading the whole bill, Model B over the Anthropic Messages API reading fields from
  the page and three bands, budget before ceiling, mocked tests only).
- **The rule and the pass rule (1.3):** `billx/reader/read/consensus.py` (fields and
  arrays matched item by item, near-identical keys for OCR confusions),
  `billx/reader/validate/passrule.py` (the five conditions of 5.2, printed inconsistency,
  `accepted`/`accepted_by`).
- **Checks and formulas (1.4, 1.5):** `billx/reader/validate/{registry,generic,gas,rules,
  conformance,tariff,formula}.py`: G01 to G20, GG01 to GG05, the rules engine (`ast`
  allow-list, Decimal, the guide's helpers plus `meters_sum`), S01 to S06, T01 to T05 as
  warnings, the formula recheck per element; every check with `detects:` and, for equality
  checks, `proves:`; the element catalogue and label-to-code map; `profiles/avvnl` and
  `profiles/pvvnl` as draft versions carrying the synthetic layouts' rates and rules.
- **Ladder, gate, pipeline (1.6):** `billx/reader/identify/gate.py` (local signals),
  `billx/reader/identify/profiles.py` (loading, `extends`, `select_version`, `match_discom`),
  `billx/reader/pipeline.py` (`read_file`: ingest → gate → discom → readers → consensus →
  transcription → checks with `unverified_inputs` → arithmetic on the Values → elements →
  the pass rule).
- **Tools (1.7):** `billx extract`, `billx validate`, `billx eval --synthetic|--golden`
  (`billx/platform/evals`: silent errors, coverage, refusals, per-field accuracy, formula
  coverage, planted caught/missed, cost and time, the rule-of-three bound; reports without
  values); `billx synth` writes the planted set and the misread fixtures; the studio
  pre-fills from the engine's own reading, with every reader's value and the checks.

## Decisions

In `docs/decisions.md` under "Stage 1": `decide()` in core; Model B temperature; budget before
ceiling; no page numbers from models; gas read from Stage 1; the line-grouping skew rule;
planted variants that trip two checks; silent errors on scalar fields; fixed synthetic rates;
the `ocr` test marker. Two more from the integration:

- **`cpu_threads` is not passed to PaddleOCR.** With it, PaddleOCR 3.7 on this Mac ran
  single-threaded and a page took 300 s instead of 12 to 25 s; two engines in one machine
  thrash each other (925 s for a page), so the OCR tests share one pytest worker and OCR
  results are cached by page hash (`BILLX_OCR_CACHE`).
- **A label may sit inside a segment for a typed field** (number, date, month) when its
  value follows immediately; a text or identifier label must start its segment. OCR joins a
  whole row into one segment, and a typed value is never mistaken for a label.

## Sample bills

None confirmed; the unconfirmed set (65 files, 11 discoms) is untouched by this stage. The
synthetic set: 42 clean documents (28 electricity, 4 gas, 10 others) and 48 planted.

## Model spend

None: no key is configured; every model path is tested with mocked HTTP.

## Pace

- Wall clock: 12 Oct 14:30 to 14 Oct (interrupted twice by the account's usage limits; the
  subagents for the four packages were resumed from their transcripts).
- Longest single wait: the OCR thread-thrash and the `cpu_threads` regression, about three
  hours of diagnosis across the full-suite runs.
- Next bottleneck: a person. Keys in `.env` make scans verifiable live; ten confirmed AVVNL
  and PVVNL bills make the first real `billx eval` possible.

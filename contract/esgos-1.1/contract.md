# Bill engine contract, version 1.1

Contract 1.1 is contract 1.0 (`contract/esgos-1.0/contract.md`, which esgOS owns and billx
never edits) plus optional additions. Every 1.0 call, field, enum and error code behaves
exactly as 1.0 says; a 1.0 client that ignores unknown fields works unchanged against a 1.1
server, and a 1.0 request without the new options behaves exactly as before. `passed` keeps
its 1.0 meaning. esgOS accepted contract 1.1 on 11 Oct 2026 (esgOS change list, item 3).

Served by the engine in `BILLX_API_MODE=esgos-1.1` (the embedded image's default). In
`esgos-1.0` mode none of this appears and a 1.1 request option is refused with 400
`bad_request`.

## 1. Additions to `POST /v1/jobs` options

| Field | Type | Meaning |
| --- | --- | --- |
| `contact` | object: `name`, `email`, `company`, `phone` | The uploading user. Stored with the job for the lead flow of build prompt 4.2 section 9.3 (deferred); never logged |
| `account_ref` | string | The caller's own label for the account or site, stored with the job |
| `pdf_password` | string | For a password-protected PDF; used once, never stored or logged. (Reading password-protected PDFs is deferred with build prompt 4.2 Stage 3.4; until then the job ends `unreadable` with note `password_required`) |
| `wait` | boolean, default false | When true, the response holds the finished job (status 200, the body of `GET /v1/jobs/{job_id}`) if it finishes within 50 seconds, otherwise 202 with the job id as in 1.0 |

## 2. Additions to each bill (section 5.2 of 1.0)

| Field | Meaning |
| --- | --- |
| `status` | `passed`, `confirmed`, `needs_review`, `unreadable`, `not_a_bill`, `wrong_document_type`, `model_not_allowed` or `budget_exceeded`; consistent with 1.0's `passed` and `unread_reason` |
| `review_reasons[]` | why a bill is not passed: `check_failed:<id>`, `unverified:<path>`, `disputed:<path>`, `insufficient_arithmetic`, `required_field_not_printed:<path>`, `layout_drift`, `unknown_utility`, `unverified_layout`, `password_required`, `source_conflict` |
| `flags[]` | on a passed bill, what does not stop it passing: `printed_inconsistency:<id>` (a check failed although every value it uses was verified: the bill itself is wrong). In 1.0 mode the same bill is `passed: false` with the note `printed_inconsistency:<id>` |
| `accepted`, `accepted_by` | whether the caller may use the bill, and by whose verdict: `engine` (passed) or `human` (confirmed by a named person in the studio). **esgOS consumes `accepted`** |
| `proof_rule_version` | the version of the verification rule that decided this result |
| `routes_used[]` | every reader that produced a returned value (`text_layer`, `local_ocr`, `model_a`, `model_b`) |
| `document_type` | `electricity_bill`, `gas_bill`, `water_bill`, `telecom_bill`, `other_invoice`, `not_a_bill` |
| `audit_status` | `not_audited` (no tariff-order audit yet: build prompt 4.2 Stage 5b), `audited` or `partially_audited`; a downstream financial or ESG report labels its figures with this and with `profile.status` |
| `elements[]` | every printed line with an amount: `index`, `label`, `group`, `kind` (`item`, `subtotal`, `info`), `stage` (`current`, `arrear`, `adjustment`), `code` (the catalogue of build prompt 5.7), `quantity`, `rate`, `unit`, `tod_slot`, `amount` (a field object), `formula_recheck` (`status` match/differs/not_computable, `computed`, `billed`, `difference`, `reason`, `formula`), `tariff_recheck` |
| `tariff_recheck` | `status: not_computable`, `reason: tariff_engine_pending`, and the per-element rechecks, until the tariff engine exists |
| `insights[]` | empty until build prompt 4.2 Stage 6a |

## 3. Additions to each field object (section 5.2 of 1.0)

| Field | Meaning |
| --- | --- |
| `verification` | `verified` (two independent readers agreed, or an anchored text-layer reading tied to the bill's arithmetic), `unverified` (one reading), `disputed` (readings disagree), `confirmed` (a named person) |
| `proof` | the proof levels the value earned: `consensus`, `arithmetic`, `exact`, `confirmed`, `single` |
| `readers` | the readers that agree with the returned value |

`verified` is an acceptance rule, not a guarantee; how often two readers share a misreading is measured on confirmed real bills and reported as `unmeasured` until then.

## 4. Added guaranteed fields (section 6 of 1.0)

All optional, each a field object verified like any other:

| Path | Unit |
| --- | --- |
| `consumer.name` | |
| `period.due_date` | date |
| `totals.current_charges`, `totals.arrears` | INR |
| `totals.due_date_rebate` | INR: the rebate for paying by the due date that the net payable deducts, as a positive amount |
| `charges.by_code[]`: `code`, `amount` | INR |
| `tariff.category` | the printed tariff code, until a mapping to the order's categories exists |
| `open_access.re_kwh`, `open_access.non_re_kwh`, `open_access.banked_kwh` | kWh, or kVAh where the bill prints kVAh: stored as printed, never converted; the field's `unit` says which |
| `energy.billed_units` | the units the discom bills (grid units) after open-access set-off, as printed; the field's `unit` says kVAh or kWh |
| `green_tariff.kwh` | kWh |

And one change to the required set: `energy.kwh` **or** `energy.kvah` is required, so a bill priced only in kVAh can pass.

`energy.kwh` and `energy.kvah` are the period's total consumption, before any open-access or captive units are set off; on a bill without open access that is the billed energy. Where a bill prints all three, check G22 ties them: total consumption - open-access units = `energy.billed_units` (added 26 Oct 2026, optional).

`totals.net_payable` is the amount payable when the bill is paid by the due date, after any due-date (prompt payment) rebate; on a bill without such a rebate it is the amount payable, and it is never the amount payable after the due date. This holds in 1.0 and 1.1. Check G09 ties it: current charges + arrears + adjustments - `totals.due_date_rebate` = net payable (27 Oct 2026; the rebate field is optional).

## 5. Resolved ambiguities in 1.0 (apply in both modes)

- `route` is the most expensive route that produced a returned value: `cloud_model` over `local_model` over `template`; `template` is the local, no-model route (text layer and local OCR); `none` with every `unread_reason`.
- `source` per value: `template` for an anchored read, `ocr` for text-layer or local-OCR words, `model` for a model reading; when several readers agree, the first of those in that order.
- `profile` (`id`, `version`, `status` `final`/`draft`/`none`) is on every bill in both modes.
- `schema_version` is the engine's core schema version (`2.0`); 1.0's example shows `1.0`.
- `checks[]` carries every check run, including skipped ones.
- Files and results are deleted within 24 hours; `DELETE` removes them at once.

## 6. Everything else

Calls, authentication, tracing, limits, the `text` kind, errors and versions are exactly 1.0's. Nothing in 1.1 nulls a printed value, changes `DELETE`, or needs a terms acceptance; those belong to the engine's `full` API (build prompt 4.2 section 6), not to this contract.

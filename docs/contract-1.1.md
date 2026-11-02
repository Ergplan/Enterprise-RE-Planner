# Contract 1.1: what it adds and why

Contract 1.0 (esgOS's, Oct 2026) describes a reader that returns values with their place on
the page and the result of the bill's arithmetic. It has no way to say *how well a value was
read*, *why a bill did not pass*, or *whether the caller may use it after a person corrected
it*. Contract 1.1 (`contract/esgos-1.1/contract.md`) adds exactly those, as optional fields,
so a 1.0 client keeps working and a 1.1 client can act on the engine's own confidence.

| Added | Why |
| --- | --- |
| `verification`, `proof`, `readers` on every field object | Build prompt invariant 0: billx never silently turns a plausible AI extraction into a trusted value. The caller sees whether two independent readers agreed (`verified`), one read it (`unverified`) or they disagreed (`disputed`) |
| `status`, `review_reasons`, `flags` on every bill | 1.0's `passed` is a boolean; a product that routes bills to people needs the reason. `printed_inconsistency` separates "the bill's own numbers don't add up" from "we misread it" |
| `accepted`, `accepted_by` | A bill a named person confirmed in the studio is `confirmed`, never `passed` (`passed` is the engine's verdict and keeps 1.0's meaning). esgOS consumes `accepted`, which is true for both, so corrected bills reach it (esgOS change list item 6, follow-up) |
| `profile.status` on every bill (1.0 already requires it), `audit_status` | A report built on a draft layout, or on a bill not audited against the tariff order, must be able to say so |
| `elements[]` with `formula_recheck` and `tariff_recheck` | Every printed line with an amount, coded to one catalogue and recomputed from its printed quantity and rate; the tariff-order recheck arrives with the tariff engine and says `tariff_engine_pending` until then |
| `energy.kwh` or `energy.kvah` required | A bill priced only in kVAh prints no kWh; under 1.0 it could never pass |
| `consumer.name`, `period.due_date`, `totals.current_charges`, `totals.arrears`, `charges.by_code[]`, `tariff.category`, `open_access.*`, `green_tariff.kwh`, `energy.billed_units`, `totals.due_date_rebate` | Fields esgOS's BRSR and energy accounting need that 1.0 left out |
| `contact`, `account_ref`, `pdf_password`, `wait` request options | The lead flow and account labelling of the hosted service (deferred), password-protected e-bills (deferred), and a synchronous call for small bills |

Not in 1.1, because they change 1.0's behaviour: nulling unverified optional values,
permanent storage, terms acceptance, the `full`-mode `DELETE`. They belong to the engine's
own API (build prompt 4.2 section 6), deferred with hosting.

Deployment matters that are not contract fields: two model providers (OpenAI and Anthropic,
esgOS change list item 2) and where the models run.

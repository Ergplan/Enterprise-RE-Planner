# Stage 3 report — avoided cost

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**Engine (pure: no database, network or model).**
- `engine/scope.py` — connection facts → scope context; nearest jurisdiction, then most specific row (operators are `rulebook/scope.py`'s, tested since Stage 1).
- `engine/tariff_eval.py` — one month of a connection under an approved `tariff_schedule` and `tod_slots`: demand charge on billing demand (floor % of contract), excess demand at the stated multiple in addition, energy by ToD slot with surcharge/rebate or a per-unit delta, retail wheeling, FPPCA, electricity duty (% or per unit), PF incentive/penalty, load-factor rebate, minimum-charge top-up, taxes, prompt-payment rebate; kVAh billing as the schedule states. Every line is a SourcedValue citing the rule fields it used and the quantities it multiplied. What a row does not state is a named gap, never an estimate.
- `engine/replay.py` — a bill rebuilt from billx's own quantities (units in the billing basis, MD, PF, ToD zones from billx's elements matched to the approved slots by the adjustment the bill applied) and compared group by group (demand, excess, energy+ToD, wheeling, FPPCA, duty, PF, LF, rebates, subsidies, each unmodelled line). Status match (≤ ₹1), explained (a named gap or a billx flag), unexplained; the bill takes the worst.
- `engine/avoided_cost.py` — the marginal avoided cost of a grid kWh as a 12 × 96 matrix (the 35,040 blocks are exactly that matrix laid over the calendar), rate cards per month and slot with cited components and the kVAh/kWh factor, and annual lines (energy at those rates over the profile, demand charges at the profile's monthly peaks with the billing floor).
- `engine/gaps.py` — 13 named gaps, each listed in `docs/known-gaps.md` (a test keeps them equal).

**API.** `GET /connections/{id}/replay`, `GET /connections/{id}/avoided-cost?as_of=` (tariff in force on `as_of`, default today). Billed amounts, computed amounts, differences and totals are SourcedValues: billed ones cite billx's element (`elements.N.amount`), computed ones the order pages and the bill quantities; every matrix cell points at a cited rate card. `SourceRef.url` is now serialised on every ref.

**UI — journey step 2, `/plan/today?c=`.** Each accepted bill rebuilt beside the real one, unexplained differences highlighted, status chips with the explanation on hover, page chips that open the stored order PDF at the page (quote on hover), "how the rebuilt lines are computed" (quantity × rate = amount with citations), the named gaps; the avoided-cost heatmap (month × time of day) with yearly energy and demand figures and the rate cards per ToD slot. Linked from step 4.

**Rulebooks corrected from what the replay found** (through the normal gate: duplicate, field citation, golden tests, approve):
- MSEDCL `tod_slots` v3: peak **+25%** for HT industrial and commercial. Case 75/2025's table prints "+20%#"; the # note is in the MYT order (Case 217/2024, p. 565): "For HT & LT Industrial & Commercial Categories = +25%". The April 2026 bill charges zone D at +25%. The golden test "peak +20%" was wrong and is corrected.
- NPCL and UPPCL `tariff_schedule` v2: billable demand = the higher of recorded MD and 75% of contract (general provisions, NPCL p. 354, UPPCL p. 410); excess demand at 200% of the normal rate in addition (pp. 355, 411).

**Real bills.** Fifteen real bills from the Mac mini read through billx (results cached in `data/bills/billx-results/`, gitignored): NPCL ×3, MVVNL ×5, PVVNL ×3, DVVNL, MSEDCL ×2 (and one Punjab and one unrecognised layout, not replayed).

**Tests.** 188 API tests (unit per line type with hand-computed expectations from the MERC and UPERC schedules, checked against the real MSEDCL April and NPCL July–August bills to the paisa; replay grouping, statuses, wrong-rule detection, proration, confirmed overrides; avoided-cost matrix values; gap registry; endpoints) and 14 web tests. The real-bill replay and the bill-drop-to-step-2 test run on the cached billx readings.

## Definition of done

| Check | State |
| --- | --- |
| Replay status match or explained on ten bills | **Met on 15 real bills, 0 unexplained.** Four fall inside the approved FY 2026-27 tariffs and are computed: MSEDCL Apr 2026 (demand, energy+ToD, wheeling match to the paisa), NPCL Jul–Aug 2026 (energy+ToD match; demand explained by `demand_proration`), MVVNL Jul 2026 and PVVNL Aug 2026 (demand and energy match). The other eleven predate those tariffs and are explained by `tariff_period` only: nothing is computed for them because the FY 2025-26 orders are not in the corpus. |
| Every line on step 2 opens its PDF page | Met: every rebuilt line carries order refs whose chips open `/api/documents/{id}#page=N`; a test asserts each computed line has such a ref |
| Unexplained list empty or filed with the rule gap named | Empty; 13 named gaps in known-gaps |
| Reviewer clean | Three rounds; the last finding is speculative (see below) |

## Skipped, and why

- Synthetic bills: the billx contract examples are generated from billx's own synthetic tariff, so replaying them against the real orders tests nothing; the line-type unit tests use bill-shaped data built from the real April 2026 MSEDCL bill instead.
- FPPCA, electricity duty, LF incentive, prompt-payment rebate, MSEDCL billing-demand floor, NPCL proration and regulatory discount are not computed; each is a named gap with the stage or document that closes it.
- A Playwright test of the step-2 page: the page was checked by screenshots against real data; the data contract is covered by the API e2e.

## Deviations

All dated in `docs/decisions.md` (1 Nov 2026, Stage 3): rules loaded in the API layer for pure engines; excess demand in addition; evaluation date (bill period end; avoided cost on today's tariff); grouping; ToD zone matching by adjustment; bill status rule and proration test; `tariff_period`; the 12 × 96 matrix; kVAh factor from bills; computed `url`; replay-driven rule corrections approved by `build-agent@ergplan`; replay tests on cached billx readings.

## Reviewer findings and resolution

Fixed: billed amounts, differences and totals were plain strings → SourcedValues citing the bill elements; the avoided-cost matrix carried bare numbers → indices into cited rate cards.

Not changed, with reason:
- "Annual energy omits wheeling/FPPCA refs" — it multiplies the full card rate (which includes wheeling) and cites every card; FPPCA is a named gap.
- "A billed SourcedValue might be built without refs in future" — `SourcedValue` requires at least one ref, and `_billed`/`_difference` return None rather than build one without inputs.

## Open questions

1. The UPERC FY 2025-26 tariff orders (NPCL and the state DISCOMs) and MERC's MSEDCL tariff before 1 April 2026: eleven of the fifteen bills fall in those periods. Can you put those orders on the mini so their bills replay against their own tariff?
2. The Maharashtra and UP Electricity Duty notifications (rates and base) and MSEDCL's FAC and NPCL's FPPAS monthly notifications: with them, duty and fuel adjustment become computed, cited lines. Where do you get them?
3. The NPCL bills carry a "regulatory discount @ 10%" on demand + energy and prorate the demand charge by days. Do you know the order paragraph? I have not found it in the FY 2026-27 order.
4. The real bills imply the 11–66 kV band (Rs 290/kVA, 6.80/kVAh) for these UP plants; the intake still assumes 11 kV until the client confirms. Should ergPLAN propose the band from the bill's printed rate (it already says so in the replay notes)?

## Cost

billx reads in this stage: 13 real bills, USD 2.61 for all 17 cached readings (OpenAI through billx). Reviewer: three gpt-5.1 calls, about 150k tokens in, about USD 0.25. ergPLAN app: no model calls. Builder: Claude subscription.

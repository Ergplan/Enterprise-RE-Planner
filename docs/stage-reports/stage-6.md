# Stage 6 report — optimizer

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**`optimizer/model.py` (pure Pyomo).** A `Problem` of blocks (month, ToD slot and slot class), the load, grid rates (Stage 3 avoided cost per month and slot), demand charge, billing-demand floor and excess-demand rate, contract demand (fixed or a step variable with a change cost), candidate sources, batteries, thermal units, the approved settlement rule and limits.
- Variables: capacity per source (OA must-take at capacity × shape, delivered at the meter after losses; behind-the-meter generation curtailable; exchange purchases dispatchable up to a cap), a "built" binary where a minimum OA size applies, battery kW and kWh with charge, discharge and state of charge, thermal output with on/off, start-up and shut-down, settlement per netting unit (set-off per source, deposits gross of the charge in kind, unbanked surplus, withdrawals per bucket, grid), bank inventory per bucket and step with drawal-window masks and lapse at period end, recorded and billing demand per month.
- Constraints: energy balance, no export behind the meter, settlement and bank as the rule says (the bucket and window logic is `settlement.simulate.Bank`'s), carry-over ceiling, regulatory limits (RE cap % of contract demand, storage mandates, minimum OA size, minimum contract demand for OA, minimum battery hours, rooftop ceiling), thermal technical minimum, ramp, minimum up and down time, must-run.
- Objective: annual INR — fixed costs × capacity, landed cost (Stage 4 `evaluate()` per month and slot) × delivered energy, grid energy at the avoided-cost rate, demand and excess-demand charges, banking charges, fuel and start-ups, contract-demand change, less payment for lapsed energy.

**`optimizer/highs_solve.py`.** Three passes: sizing on hourly blocks; 15-minute dispatch month by month with sizes fixed (battery charge and bank carried forward); a settlement pass under the rule's order per banking period. HiGHS, one thread, time limit and MIP gap from settings; gap logged.

**`optimizer/resettle.py`.** The judge: `settlement.simulate()` on the solver's dispatch; month-by-month comparison of grid, set-off, banked, charge, withdrawn and lapsed plus the year's totals against `ergplan_resettle_tolerance_kwh`; disagreement → `failed_resettle`. Costs reported come from the judge's quantities.

**`optimizer/scenarios.py`.** Scenario spec (candidates with ownership, quote, max/min MW; as-of; 15 or 60 minutes; contract-demand step; lapse price; grid factor; sensitivity ranges), IRR, payback, repricing.

**Runs (`platform/runs.py`, `platform/worker.py`).** Assembles the problem from approved rules through a recording reader; pins every rulebook version read, the load profile id and version, the price vintages, the solver version and the as-of date; stores summary, re-settlement check and settled dispatch; replay through the pinned versions. Worker: `python -m ergplan.platform.worker` (compose service `worker`), claims runs with `FOR UPDATE SKIP LOCKED`. Tables `scenarios`, `runs` (audited by trigger, writes refused without an actor), `run_results`.

**API.** `POST/GET /sites/{id}/scenarios`, `POST /scenarios/{id}/run`, `GET /runs/{id}`, `GET /runs/{id}/dispatch`, `POST /runs/{id}/replay`. Outputs: capacities, annual cost before and after, saving, capital, payback and IRR (owned plant only), emissions with the grid factor as a sourced value, settlement totals, contract demand, the waterfall per source at the chosen sizes, binding constraints in plain words with citations, sensitivities, provenance. Clients never see a run that is not settled.

**UI — journey step 5, `/plan/optimise?c=`.** Scenario cards side by side (sizes, saving, cost before → with plan, payback, IRR, grid CO₂, citation chips); analysts queue the three standard scenarios at 15 minutes or hourly; the settled dispatch for a chosen week as a stacked chart under the load line; binding constraints with page chips; price sensitivities; the judge's agreement for analysts.

**Tests.** 18 tiny-model tests (one or more per constraint family, optima worked by hand, the judge agreeing on each); 5 API integration tests at hourly resolution (validation and roles; run, client view, dispatch, replay identical to the paisa, audit rows and the refused unaudited write; failed re-settlement hidden from clients; an absurd draft tariff leaves a run unchanged; a UP site with banking); two 5 MVA sites at 15 minutes (`slow`); the end-to-end from the real NPCL bill to three scenarios at 15 minutes and a replay (`slow`); a web unit test.

## Definition of done

| Check | State |
| --- | --- |
| Both test sites solve at 15 minutes within two minutes with re-settlement agreement | Met on this workspace (2 cores): MSEDCL 5 MVA ≈ 30 s, PVVNL 5 MVA ≈ 75 s, both 0 kWh difference. Not yet timed on the VM (deployment is Stage 8's move). |
| Replay test passes | Met (identical summary digest, hourly in the watcher; 15-minute in the end-to-end) |
| Three scenarios compared on one screen | Met (`/plan/optimise`, real NPCL site) |
| Reviewer clean | See below |

## Skipped, and why

- One 35,040-block MILP: replaced by the three passes (decisions, Stage 6).
- Sizing a captive thermal plant; battery degradation; block-level IEX prices; land as a bound — in known gaps.
- Running sensitivities as re-solves: they reprice at fixed sizes.

## Deviations

Dated in `docs/decisions.md` (1 Nov 2026, Stage 6): three passes; the solver's own settlement pass and the deposit guard; lower carry-over ceiling in sizing; monthly comparison; per-kWh landed cost reuse; owned-plant costs and default bounds; payback and IRR for owned plant only; grid factor assumption; runs in `platform/`; pinned-rule reader for replay; `slow` marker; sensitivities at fixed sizes.

## Reviewer findings

Three rounds (`docs/stage-reports/stage-6-review.md` holds the last).

Fixed:
- The re-settled cost in the analyst check is now a quantised Decimal string.
- Every SourcedValue in a run summary is checked for refs by the integration test (more than 20 per run).
- `pinned_rules` is tested never to return a draft, and the recording reader never returns one.
- Reported costs no longer pass through floats: the problem carries Decimal inputs (`Exact`) beside the solver's floats; solver outputs become Decimals in one place.
- The resolution is pinned with the run.

Not changed, with reasons:
- The solver works in floats internally (HiGHS needs them). The optimizer settings (time limit, MIP gap) are floats too: they are solver options, not money or energy. Nothing stored or returned as money or energy is a float.
- "measured" is not a missing source-ref kind: `RefKind.MEASURED` exists since Stage 2. The reviewer saw only the diff.
- Older scenario rows without `resolution_min` cannot exist: the table is new in this stage, and the field defaults to 15.
- Things a diff cannot prove: solver determinism across library versions (pinned `highspy==1.15.1`), other client paths to unsettled runs (none exist: step 5 reads only `/runs` and `/sites/{id}/scenarios`, both filtered), the claims in this report.

## Open questions

1. Grid emission factor: which CEA CO₂ Baseline Database version should reports use (0.71 tCO₂/MWh is assumed)?
2. UP CRE Reg. 12 carry-over ceiling: "25 % of the energy injected during the month" — the simulator reads this as energy banked (surplus injected into the bank), not the plant's whole injection. Which does UPPCL apply in its statements?
3. Default bounds when you give none (rooftop: roof area ÷ 10 m²/kWp or the contract demand; battery: half the contract demand; OA: three times the contract demand) — are these sensible, or do you want per-client limits always asked?
4. Should payback and IRR be shown for mixes of a PPA and owned plant (on the owned capital against the owned assets' share of the saving), or is "owned plant only" right?

## Cost

No billx reads and no app model calls. Reviewer: three gpt-5.1 calls, about 200,000 tokens in and 10,000 out, about USD 0.35. Builder: Claude subscription.

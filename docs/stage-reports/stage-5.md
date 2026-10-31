# Stage 5 report — settlement simulator

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**`settlement/simulate.py` (pure, deterministic).** Blocks (month, ToD slot and the slot classes a rule may use, load, each source's energy at the meter), sources (set-off category; whether the rule's scope lets them bank) and the approved rule in; per block: grid drawal, set-off against the load and at the source, deposits net of the charge in kind, the charge, withdrawals, unbanked surplus; per banking period: lapse and balances by bucket.
- Granularities: block_15min, hourly, tod_slot_monthly, monthly_aggregate, annual.
- Banking: allowed or not; charge in kind or INR/kWh; period monthly, quarterly or financial year with or without carry-over; carry-over ceiling as % of injection and/or % of DISCOM consumption, combined higher or lower (UP CRE Reg. 12); drawal windows (deposit slots → allowed slots, optionally by month); per-slot or pooled buckets; FIFO lots; withdrawal priority same-slot-first or as listed; everything left lapses at the end of the financial year; lapse paid at a price when the rule says.
- Set-off order from the rule (captive generation, banked energy, bilateral, exchange).
- `statement()`: the year as cited SourcedValue lines (consumption, set-off per source, banked, charge, withdrawn, lapsed, unbanked, grid drawal, payment for lapsed energy), citing the rule's pages and the inputs.

**Generation.** Normative curves in `packages/profiles/cuf` (UP and Maharashtra solar and wind; hybrid = both), each scaled to an annual CUF and marked as an assumption; `intake/generation.py`. The landed-cost waterfall now exposes the delivered share after losses, so settlement works on energy at the meter.

**API and UI.** `POST /connections/{id}/settle` (analyst): sources with capacity and ownership, a normative curve or a 15-minute injection → statement and month table with bucket balances. `/settlement?c=` analyst explorer: the cited statement and month-by-month stacks of direct set-off, bank and grid, banked / charge / withdrawn / lapsed and the bank at each month's end.

**Tests.** 14 hand-worked cases, table-driven in `apps/api/tests/settlement/cases/*.yaml` and mirrored in `packages/rulebooks/golden/{up,mh}/settlement-cases.yaml` (a test keeps them equal):
- UP (the approved CRE Regulations rule): surplus banked after 8%, off-peak deposits not drawable in peak; carry-over capped at the higher of 25% of injection and 30% of DISCOM drawal with the rest lapsing; peak deposits drawn off-peak and in peak; financial-year-end lapse.
- MSEDCL (the approved Regulation 20.3 rule): solar surplus cannot serve normal or peak; normal surplus serves solar; peak surplus serves every slot; no carry-over.
- Synthetic rules for monthly-aggregate pooled banking with an INR charge, hourly, annual, set-off order, quarterly period with a ceiling, month-limited drawal windows.
Property tests on generated quarters under four rules: every block balances (load = set-off + withdrawals + grid; injection = set-off + deposits + charge + unbanked), nothing negative, deposits = withdrawals + lapse over the run. Endpoint and generation tests. 237 API tests in all.

## Definition of done

| Check | State |
| --- | --- |
| Golden settlement cases for UP and Maharashtra pass | Met |
| Real statements reproduced within 0.5%, or the gap named | **Not run**: no settlement statements were supplied (`data/settlements/` is empty). Recorded in known-gaps. |
| Reviewer clean | Met (no code defects) |

## Skipped, and why

- The e2e against real OA statements — no data.
- Selling ISTS surplus at a scenario price: the simulator reports unbanked surplus; pricing it is the optimizer's (Stage 6).
- Separate banks for sources under different settlement scopes (one bank per consumer for now).

## Deviations

Dated in `docs/decisions.md` (Stage 5): one governing rule; spreading aggregated results to blocks; deposits before withdrawals within an aggregated month; charge in kind on deposit; ceiling per period from that period's injection and DISCOM drawal; slot classes; normative curves; no real statements.

## Reviewer findings

No code defects. Unprovable-from-diff notes: the month table of the analyst endpoint is plain numbers (analyst-only; the client-facing statement is SourcedValues); invariant 2 and 8 rely on code from earlier stages (repository, profile provenance), which earlier reviews covered.

## Open questions

1. Can you share a year of real open-access settlement statements (UP or Maharashtra, anonymised) for `data/settlements/`? That is the Stage 5 check against reality.
2. For clients mixing intra-state captive and ISTS third-party power, should each have its own bank (as the regulations would treat them), or is one consolidated view enough for planning?

## Cost

No billx reads and no app model calls. Reviewer: one gpt-5.1 call, 32k tokens in, about USD 0.05. Builder: Claude subscription.

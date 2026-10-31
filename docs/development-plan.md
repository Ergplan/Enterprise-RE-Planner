# ergPLAN — Development Plan v0.1 (approved 31 Oct 2026)

Living copy of the approved plan: https://claude.ai/artifact/NLparJwTT1PM2CmNYA7BFi. The master prompt (`docs/MASTER-PROMPT.md`) implements it.

## 1. What ergPLAN is

ergPLAN tells an industrial consumer, from its electricity bills alone, what each unit of power costs it today and what the cheapest green replacement costs delivered to its meter, in its state, under its DISCOM's tariff and its state's open-access and banking rules, and then sizes the mix (rooftop, BTM BESS, open-access solar, wind, BESS, pumped storage, IEX purchase) that replaces grid and thermal power at the lowest annual cost. A jouleWise product.

The client journey: (1) drop a bill, or speak or type state, DISCOM, voltage, contract demand and approximate bill; (2) see today's cost rebuilt from the tariff order line by line; (3) see landed cost cards for every source with a waterfall by ToD slot, every charge sourced; (4) describe the site (shifts, assets, thermal station, roof and land) and get a 15-minute load profile; (5) optimise under the state's settlement rules, RE cap, BESS mandate, banking windows and thermal constraints; (6) take away a live plan link with voice what-if, a jouleWise analyst view, and a PDF.

## 2. Landed cost

Per source, per 15-minute block (or ToD slot), INR/kWh at the meter:

L = (P + τ) / Π(1 − ℓ_i) + (C_ISTS + C_STU + C_SLDC) / E + CSS + AS + ED + BC + DSM

P generation price (PPA, IEX MCP + fee + margin, LCOE, thermal variable cost); τ per-kWh wheeling/transmission; ℓ losses in kind at each stage crossed; C capacity charges per month over scheduled energy E; CSS cross-subsidy surcharge; AS additional surcharge; ED duty on OA units; BC banking charge on banked units; DSM deviation pass-through. Each term is a scoped rule row with exemptions (captive ≥26 %/51 %, GEOA CSS cap and AS condition, state RE waivers with sunsets, ISTS waiver by commissioning date). Every number carries `{value, unit, source_ref}` with regulation, page, quote and a link opening the stored PDF at that page.

Sources: discom grid and green tariff, rooftop PV (net metering regimes), BTM BESS, OA solar/wind/hybrid intra-state and ISTS, OA BESS, pumped storage, IEX DAM/RTM/GDAM/G-TAM/TAM/HP-DAM, captive thermal, group captive.

## 3. Avoided cost and the saving

Saving = Σ_t (A_t − L_s,t) x_s,t − ΔFixed − ΔPenalties − LostRebates − CRF·Capex. A_t is the slot's energy charge with ToD adjustment, FPPCA, duty and taxes; fixed and demand charges stay unless contract demand changes; LF and PF incentives, minimum charges, excess demand penalty and prompt-payment rebates are modelled. The bill replay test accepts a DISCOM's tariff data only when ergPLAN recomputes the real billx-read bill line by line.

## 4. Settlement rules as data

One schema for every state: granularity (block_15min, hourly, tod_slot_monthly, monthly_aggregate, annual); banking allowed and charge (in kind % or INR/kWh); bank period and carry-over; drawal windows (slots × months); lapse treatment (lapses, paid at APPC × factor, paid at RE tariff); set-off order; scope (ISTS vs intra-state, source, ownership, capacity, dates). Deterministic engine; the LLM drafts rows from regulation PDFs with page citations; an analyst approves. Families: settlement, tariff_schedule, oa_charge, regulatory_limit, ists_waiver, net_metering, tod_slots.

## 5. Database

PostgreSQL; rules in JSONB validated by JSON Schema; `rulebook_versions` draft → approved → superseded with effective dates; `rules` with indexed scope; `rule_tests` golden cases gating approval; `source_documents` with stored PDFs; `price_series` with vintages; clients, sites, connections, bills (billx results with proofs), load_profiles with provenance, assets, scenarios/runs/results pinned to versions; `audit_log` by trigger.

## 6. Optimizer

MILP (Pyomo + HiGHS) over 35,040 blocks: capacities and dispatch per block including bank buckets, BESS SOC, thermal unit commitment (technical minimum, ramps, min up/down, must-run waste heat), regulatory limits, demand and LF terms; objective annualised capex + landed cost + fixed charges + penalties − incentives. A deterministic settlement simulator runs first and re-settles every optimizer result.

## 7. Intake

Three doors into one `SiteIntake`: billx bill drop (contract esgos-1.1, accepted bills, one-click confirmations for needs_review), OpenAI Realtime voice calling typed tools, typed form. Most clients have only bills, so a 15-minute profile is synthesised from 12 bills using industry shapes, matching monthly kWh, ToD split and recorded MD exactly; measured ergOS/SCADA data when it exists. IEX price CSVs are uploaded by jouleWise in the application. Normative defaults are shown as editable assumption chips.

## 8. Architecture and locked decisions

See section 4 of `docs/MASTER-PROMPT.md`.

## 9. Stages

0 Skeleton · 1 Rulebook and regulation reader (UP, Maharashtra seeded) · 2 Intake and site · 3 Avoided cost · 4 Landed cost · 5 Settlement simulator · 6 Optimizer · 7 Journey, voice, live plan · 8 Breadth (8 more states) and launch.

## 10. Decisions taken 31 Oct 2026

Source on every number with PDF page link (invariant); built directly in this repo, separate from House of Rama; most clients have only bills; IEX CSVs uploaded in the app; tariff-order reader from Stage 1; deliverable is a live link with voice what-if plus jouleWise view and PDF; UP and Maharashtra first; captive coal/gas with waste heat must-run, fixed cost sunk; Google Cloud asia-south2 VM.

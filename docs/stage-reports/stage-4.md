# Stage 4 report — landed cost

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**Engine (pure).**
- `engine/landed_cost.py` — twenty sources (DISCOM grid and green tariff, rooftop PV, behind-the-meter battery, open-access solar/wind/hybrid intra-state and ISTS, OA storage, pumped storage, six IEX segments, captive thermal, group captive). `evaluate()` builds the waterfall in the master prompt's order: price P; per-kWh charges on injection (STU transmission, wheeling, ISTS); loss gross-up of P and those charges over the loss stages whose rows apply; capacity charges over scheduled energy (capacity × CUF × hours); drawal charges (CSS, additional surcharge, duty on OA, DSM, standby, exchange fee, trading margin; `percent_of_price` too); banking charge on the full injected quantity, labelled as the upper bound; ISTS waiver by commissioning date (charges and losses, with its term); exemptions by condition with sunset dates, each a negative line citing the exemption field. Missing components are named gaps. `coefficient()` gives total = a·P + b for block series.
- `engine/lcoe.py` (and `lcos.py`) — CRF, LCOE with degradation, LCOS; every input a SourcedValue (assumptions by default, editable).

**Rulebooks (through the gate, with review notes and field citations).**
- UP `oa_charge` v2: the inter-state transmission loss (1.56%) was scoped to intra-state transactions too; now inter-state only.
- NPCL v4, UPPCL v3: wheeling, OA distribution loss, CSS and additional surcharge were scoped to intra-state OA only, although the orders apply them to all OA consumers on the distribution network; captive and group-captive CSS exemption added from the UPERC CRE Regulations 2024, Reg. 11.II ("A Captive Generating Plant shall not be liable to pay cross subsidy surcharge", PDF p. 13), with golden tests.

**Prices.** IEX clearing prices enter as the mean over each ToD slot's blocks in the calendar month from the latest live vintage, cited with a new `market` source-ref kind (`/prices/vintages/{id}` names the file and SHA-256).

**API.** `GET /connections/{id}/landed-cost?scenario=` (per-source price, ownership, commissioning date, capacity, CUF, equity cost; month; as_of; GEOA), `GET /rulebooks/limits`, `GET /prices/vintages/{id}`.

**UI — journey step 3, `/plan/landed?c=`.** Comparison bars of every source against the grid's avoided cost, slot by slot; one card per source with "how it adds up" (each line with its order-page chip), "saves/costs vs grid" per slot; month switch; the jouleWise view lists the rule rows behind each card; a panel of what is not available and why.

**Tests.** 211 API tests (component and exemption tests with hand-computed expectations: loss gross-up, injection charges, captive CSS exemption citing Reg. 11.II, banking upper bound at 8% in kind, ISTS waiver and capacity charge on synthetic CERC-shaped rows, exemption conditions and sunset, LCOE/LCOS; the nine spreadsheet consumers; every non-price line cites a stored page; endpoints; the step-3 end to end from the real NPCL bill with the real RTM file loaded through the analyst endpoint) and 14 web tests.

## Definition of done

| Check | State |
| --- | --- |
| Spreadsheet comparison to the paisa for six consumers and every source, or a named gap | **Partly met.** The spreadsheets (`tests/fixtures/landed_cost_up.csv`, `landed_cost_mh.csv`: 11, 33 and 132 kV in each state, UP third-party and captive) match to four places for open-access solar. They are **drafts by the build agent** — hand-computed from the approved pages, independently of the engine — because the prompt asks jouleWise to supply or approve them. Other sources are not in the spreadsheets yet. |
| Field-trace shows every step-3 field with an owner | Met (20 rows; CI checks) |
| Reviewer clean | Two rounds; the remaining two findings are not code defects (below) |

## Skipped, and why

- **CERC rules** (ISTS charges, ISTS waiver, IEX fees, GEOA Rules) are not in the corpus, so ISTS and IEX sources carry those components as named gaps; the engine handles them when approved rows exist (tested on synthetic rows).
- **Maharashtra OA** wheeling, losses, additional surcharge and the captive CSS exemption are not yet read; MSEDCL OA landed cost is P + CSS only, flagged.
- **Regulatory limits** (RE cap % of CD, storage mandate, minimum OA size and CD): no approved `regulatory_limit` rows; the endpoint returns an empty list and the gap.
- **GDAM, G-TAM, TAM, HP-DAM**: no price files.
- **CUF curves**: deferred to Stage 5 (no capacity-based OA charge is approved yet).

## Deviations

Dated in `docs/decisions.md` (1 Nov 2026, Stage 4): per-slot landed cost for a chosen month; gross-up base; exemption lines; banking upper bound; default prices as assumptions and rooftop in daylight slots only; `market` refs; OA scope corrections; draft spreadsheets; CUF deferred.

## Reviewer findings and resolution

Fixed: exemption helper made pure (returns lines and the exemption pointers used); STU loss gap; INR/MW/day and hours-per-month constants exact (365/12, 8,760/12); fractional economic life refused.

Not changed, with reason: field-trace owners list every table a field can come from (the grid line uses no price series; IEX lines do); the CSS assertion in the API test is on the MSEDCL fixture connection, where p. 106 is right; per-slot PPA prices are deliberately not accepted (one price per source, `extra="forbid"`).

## Open questions

1. Please review or replace the two draft spreadsheets (`apps/api/tests/fixtures/landed_cost_up.csv`, `landed_cost_mh.csv`), and add rows for the other sources you want checked.
2. The CERC documents (ISTS Sharing Regulations 2020 and the waiver orders, GEOA Rules 2022, IEX fee schedule) and the MERC DOA Regulations: can they go into the corpus on the mini?
3. Is 3.10 / 3.60 / 3.50 INR/kWh a fair default for intra-state solar / wind / hybrid quotes in UP and Maharashtra, or do you want your recent offers as defaults?

## Cost

No billx reads and no app model calls in Stage 4. Reviewer: two gpt-5.1 calls, about 90k tokens in, about USD 0.15. Builder: Claude subscription.

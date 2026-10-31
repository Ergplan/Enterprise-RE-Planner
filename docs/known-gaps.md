# Known gaps

What is not yet right, and the stage that fixes it.

| Gap | Fixed in |
| --- | --- |
| `docker/compose.yaml` has not been run (no Docker daemon in the build workspace); first run happens on the Mac mini | Before Stage 5 |
| The independent reviewer is a tool script that imports `openai` directly (outside `ergplan/providers`); it is not app code and logs no `model_calls` row | By design |
| Only 5 of the 19 indexed orders are in the build workspace (UP ×2, MSEDCL ×3); the rest are on the Mac mini and register with the same command | Stage 8 |
| Seeded rulebooks are approved by `build-agent@ergplan`; a jouleWise analyst should review each in `/rulebooks` and re-approve under their own name (duplicate → approve) | Before client use |
| HV-2 **rural** schedule (7.5% rebate on the 11 kV urban base rate, no ToD) is not representable: `tariff_schedule` has no "rebate on base" field | Stage 3 |
| NPCL and UPPCL tariffs are "in force seven days after newspaper publication"; versions carry the order date (2 Jul 2026) because the publication date is not in the corpus | When the date is known |
| UP open-access **exemptions** not yet on the rows: captive users exempt from CSS (CRE Reg. 11.II), UP Solar Energy Policy 2022 wheeling/transmission exemptions (50% captive and third party, 100% sale to DISCOM; CRE Reg. 10.III table p. 14), embedded OA consumers and EHV consumers exempt from wheeling (on the rows as notes, condition `other`) | Stage 4 (exemption engine) |
| UP biomass banking proviso (excess over the ceiling sold at Rs 1/unit or the PPA rate) not modelled | Stage 5 |
| Maharashtra OA wheeling charge, OA losses, additional surcharge and banking charge not yet read (MERC MYT order Case 217/2024 and DOA Regulations) | Stage 4 |
| Only HT industrial and commercial categories are seeded (UP HV-2; MH HT I(A), HT II); LT industrial (UP LMV-6, MH LT V) not yet | Stage 2–3 as clients need them |
| No ISTS waiver, regulatory limits or net-metering rulebooks yet (CERC documents not in the corpus) | Stage 4 |
| Real bills: NPCL and MSEDCL pass end to end; two per DISCOM are still needed for PVVNL, MVVNL, DVVNL (files in `data/bills/` not yet run) and a second MSEDCL month | Stage 3 |
| Only RTM and DAM IEX files are present (`data/iex/`); GDAM, G-TAM, TAM and HP-DAM files are needed for "six IEX CSVs loaded" | When the files arrive |
| billx returned no ToD split for the two real bills read, and the synthetic PVVNL bill names its slots `Tod-1..3` without hours; such a split is not used (the month's total is, with a warning); the API accepts typed ToD hours (`MonthFacts.tod`) but step 1 has no editor for them yet. Mapping slot names to the order's windows needs either billx printing the hours or a per-DISCOM slot table | Stage 3 (bill replay checks the ToD energy charges) |
| Back-solving monthly units from a bill amount when only the amount is known needs the approved tariff (`site_intake` takes energy as given) | Stage 3 |
| A flat-topped shape cannot reach a recorded MD well above its plateau by stretching alone; the rest of the MD is placed as one 15-minute peak block (`peak_method: linear+peak_block`), which is realistic for MD but not for the hour around it | Measured data replaces it |
| Voltage is assumed from the category (UP HV-2 11 kV, MSEDCL HT 22 kV) when not stated; MSEDCL HT supply may be 11, 22 or 33 kV | Client confirms in step 1 |
| Months without a bill are extrapolated at the billed months' mean daily energy (no seasonality) | Stage 3 (seasonality from history when billx returns it) |
| Hand-built landed-cost spreadsheet for six test consumers needed as `tests/fixtures/landed_cost_<state>.csv` | Stage 4 |
| A year of real OA settlement statements (anonymised) needed in `data/settlements/` | Stage 5 |

## Named rule gaps used by the bill replay (Stage 3)

A replayed bill line that differs from the approved tariff is "explained" only by one of these ids (`apps/api/ergplan/engine/gaps.py`; a test keeps the two lists equal).

| Gap id | What is missing | Fixed in |
| --- | --- | --- |
| `fppca_monthly` | Fuel and power purchase adjustment (MSEDCL FAC, UP FPPAS) is notified monthly by the DISCOM; no monthly FPPCA rulebook | Stage 4 (monthly FPPCA family with the DISCOM notifications) |
| `electricity_duty` | Electricity duty is set by the state Electricity Duty Acts (UP; Maharashtra 7.5% of demand + energy + wheeling + ToD + FAC on the April 2026 bill), not by the tariff order; the Acts are not in the corpus | When the Acts are added to the corpus |
| `tax_on_sale` | Maharashtra tax on sale of electricity (paise per unit) | With the duty Acts |
| `load_factor_incentive` | Load-factor incentive bands (MERC) are in the order but not yet read into `tariff_schedule.lf_incentive` | Stage 4 |
| `prompt_payment_rebate` | Prompt-payment rebate terms are in the orders' general conditions, not yet read | Stage 4 |
| `bulk_consumption_rebate` | MSEDCL bulk and incremental consumption rebates | Stage 4 |
| `state_subsidy` | State industrial subsidies (Maharashtra textile and region-based) are government schemes outside the tariff order | Not modelled (client-specific; entered as stated) |
| `regulatory_discount` | NPCL's 10% regulatory discount on demand + energy, printed on the FY 2026-27 bills; the order provision is not yet located | Stage 4 |
| `tod_split_unknown` | The bill gives no energy by ToD slot, so the ToD adjustment cannot be recomputed | When billx returns the split |
| `billing_demand_rule` | The schedule row states no billing-demand floor (MSEDCL) while recorded demand is below contract | Stage 4 (MERC billing-demand clause) |
| `demand_proration` | NPCL prorates the monthly demand charge by days in the billing period (31 / (365/12)); the provision is not yet located | Stage 4 |
| `tariff_period` | No approved tariff covers the bill's dates: the FY 2025-26 orders (UPERC for NPCL and the UPPCL DISCOMs, MERC for MSEDCL before 1 Apr 2026) are not in the corpus | When those orders are added |
| `unmodelled_line` | A miscellaneous line the bill prints (delay-payment surcharge, rounding, adjustments) | By design |

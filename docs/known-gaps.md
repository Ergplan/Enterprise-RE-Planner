# Known gaps

What is not yet right, and the stage that fixes it.

| Gap | Fixed in |
| --- | --- |
| The independent reviewer is a tool script that imports `openai` directly (outside `ergplan/providers`); it is not app code and logs no `model_calls` row | By design |
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
| Six-consumer landed-cost spreadsheets are drafts by the build agent (`tests/fixtures/landed_cost_up.csv`, `landed_cost_mh.csv`); jouleWise to approve or replace | Before client use |
| Maharashtra captive CSS exemption (EA 2003 s. 42(2) proviso; MERC DOA Regulations) not in the rulebook: a captive MSEDCL consumer is shown paying CSS | When the MERC DOA Regulations are added |
| UP Solar Energy Policy 2022 wheeling and transmission exemptions (50% captive and third-party, 100% sale to DISCOM; CRE Regs p. 14) not applied: the policy's validity period is not in the corpus | When the policy is added |
| Normative PPA prices, LCOE and LCOS inputs are assumptions (editable) | Client quotes |
| A year of real OA settlement statements (anonymised) needed in `data/settlements/` to check the simulator within 0.5% (Stage 5 DoD); the simulator is checked against hand-worked cases and properties until then | When supplied |
| One bank per consumer (the first matching settlement rule); mixed rules across sources share it or net without banking | When a client mixes rules |
| Sizing passes under-value genuinely surplus banked energy by the deposit guard (at most the spread between the best withdrawal rate after the charge and the deposit slot's rate) and take the lower carry-over ceiling: sizes lean small where banking matters; the reported numbers are exact (judge) | A sizing refinement loop |
| Sources of different set-off categories in block-level netting (UP): the rule draws the bank before bilateral supply in a block; the settlement pass maximises direct set-off first, so a captive + third-party mix with banking may fail re-settlement (it is then not shown) | When such a mix is needed |
| Capacity of a captive thermal plant is not sized (existing units are dispatched with on/off, ramp and minimum up/down times); unit commitment at 15 minutes for a year is slow — use the hourly preview for sites with thermal | Stage 7 if needed |
| Battery degradation, auxiliary consumption and a depth-of-discharge limit are not in the dispatch | Stage 7 |
| IEX purchases priced at the month-slot mean, not block by block | When block prices matter for a client |
| Land area does not bound any candidate (no on-site ground-mount source yet) | When one is added |
| Generation for settlement comes from normative CUF curves unless a 15-minute injection is supplied | Developer profiles |
| The audit shows one time-of-day slot's landed cost per source (the first; "slots differ" is shown when they do); a working's per-slot figures are set against that slot only | When a client's working is per slot |
| Runs made before 2 Nov 2026 have no stored chain: the audit shows their waterfall lines without rates or rules until the plan is run again | Next run of each plan |
| A scanned working has no text to ground figures in; its figures are typed against the chain by hand (the quote check then fails) | OCR for workings, if needed |
| The audit compares annual money lines and site energy, not month by month | When a client's working is monthly |
| Accepting a proposal needs the regulation registered as a source document; an analyst gives its id by hand (no search in the queue yet) | Next analyst UI pass |

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
| `settlement_rule` | No approved settlement rule for the source's ownership in the state (in UP, third-party open access: the approved rows, from the CRE Regulations 2024, cover captive and group captive only): set-off in the same 15-minute block, no banking | When the state's OA/GEOA banking regulation is read and approved |
| `tod_split_unknown` | The bill gives no energy by ToD slot, so the ToD adjustment cannot be recomputed | When billx returns the split |
| `billing_demand_rule` | The schedule row states no billing-demand floor (MSEDCL) while recorded demand is below contract | Stage 4 (MERC billing-demand clause) |
| `demand_proration` | NPCL prorates the monthly demand charge by days in the billing period (31 / (365/12)); the provision is not yet located | Stage 4 |
| `tariff_period` | No approved tariff covers the bill's dates: the FY 2025-26 orders (UPERC for NPCL and the UPPCL DISCOMs, MERC for MSEDCL before 1 Apr 2026) are not in the corpus | When those orders are added |
| `ists_charges` | ISTS transmission charges (CERC Sharing of ISTS Charges and Losses Regulations 2020) are not in the corpus | When the CERC documents are added |
| `ists_waiver` | The CERC ISTS waiver schedule by commissioning date is not in the corpus | When the CERC documents are added |
| `oa_wheeling` | No open-access wheeling charge for the DISCOM and voltage (Maharashtra not yet read) | Stage 4 follow-up (MERC MYT order) |
| `oa_losses` | No open-access distribution loss for the DISCOM (NPCL and Maharashtra not yet read) | Stage 4 follow-up |
| `oa_css` | No CSS for the category and voltage | As categories are added |
| `oa_additional_surcharge` | No additional surcharge row (Maharashtra not yet read) | Stage 4 follow-up |
| `iex_fees` | IEX transaction fee and trader margin (CERC) not in the corpus | When the CERC documents are added |
| `scheduled_energy` | A capacity charge cannot be spread without the source's capacity and CUF | Scenario input |
| `green_tariff` | DISCOM green-tariff premiums are not yet read into the tariff schedules | Stage 4 follow-up |
| `iex_prices` | GDAM, G-TAM, TAM and HP-DAM files not supplied (RTM and DAM are loaded) | When the files arrive |
| `regulatory_limits` | No `regulatory_limit` rulebook yet: the RE cap (% of contract demand), storage mandate, minimum OA capacity and minimum contract demand for OA need their regulations (GEOA Rules 2022, state GEOA regulations) in the corpus | When those documents are added |
| `unmodelled_line` | A miscellaneous line the bill prints (delay-payment surcharge, rounding, adjustments) | By design |
| Voice has not been tried end to end with a real microphone in this workspace (no audio device); the Realtime session minting, the tool relay and the tools are tested, one real minting call is marked external | First use on the Mac mini |
| Editable assumption chips on the live plan cover PPA prices and contract demand; other assumptions (capex, CUF, grid factor) are visible in the jouleWise view but not yet editable by the client | Stage 8 |
| What-if is an hourly check with sizes held; re-sizing on a changed assumption needs a new run (analyst or "Build my plan" after the change) | By design for speed |
| Explanations are in English only | When a client asks |
| Voice sessions and text chat in intake mode can be opened by anyone who reaches the site (plan mode needs a valid share token); each session costs OpenAI audio usage. Login, roles per endpoint and rate limits are Stage 8 (rule 12) | Stage 8 |
| Karnataka open access: CSS, additional surcharge (not levied) and each ESCOM's HT wheeling charge and HT technical loss are approved; not yet: KPTCL transmission charges and losses (separate order), banking (separate KERC orders), the captive CSS exemption | When the KPTCL transmission order and KERC banking orders are added |
| Punjab open access: CSS (Large Supply), wheeling (LTOA/MTOA per MW; NRSE within the State 2 % in kind) and T&D losses by voltage are approved; not yet: STOA wheeling, additional surcharge, PSTCL transmission charges, banking, the captive CSS exemption | When the PSERC OA regulations and PSTCL order are added |
| Telangana open access: CSS and the aggregate T&D charge per DISCOM are approved (FY 2026-27 order); not yet: additional surcharge for H2 FY 2026-27 (the order states H1's Rs 0.13/kWh only), open-access losses (the order's 'L' includes commercial losses), banking (TGERC OA regulations), STU/transmission charge as a separate line, the captive CSS exemption (Electricity Act s. 42(2)) | When the TGERC OA regulations and the H2 additional-surcharge order are added |
| Gujarat HTP-I is approved (slabs, excess rate, energy and ToD bands by billing demand, HV/EHV rebate); not yet: the graded power-factor adjustment (11.6), open-access charges (GERC OA order), the other HT categories | When needed / the GERC OA order is added |
| Where the energy or ToD rate depends on billing demand (Gujarat), the optimizer and the judge price every block at the band of the contract demand; a plan that moves billing demand across 500 or 2,500 kVA is not re-banded (the monthly bill replay is exact) | A band-aware judge if a client sits near a boundary |
| Rajasthan (the stored file is an HTML page) and Haryana (a scanned 7-page notice) need the actual order PDFs | When supplied |
| Andhra Pradesh HT-III(A) is approved from Table 11 (page 197); not yet: the minimum energy charge (50 kVAh per kVA of billing demand), open-access charges, other HT categories | When needed |
| Tamil Nadu: FY 2026-27 rates are the FY 2025-26 rates indexed by CPI from 1 July 2026; the indexed schedule is not in the corpus | When TNERC publishes or jouleWise supplies it |
| Punjab ToD (mid-month seasons, Rs 5.50/kVAh off-peak cap) cannot be expressed by `tod_slots`; PSPCL energy is priced flat | Schema change |
| The VM runs at `https://<ip>.sslip.io` until a jouleWise hostname is pointed at it; sign-in links are issued by the operator until SMTP is set | A hostname and an SMTP account |
| The Mac mini serves the LAN on plain http (`http://<the mini's address>`): no https, no public hostname, sign-in links issued by the operator until SMTP is set; the session cookie travels unencrypted on the office network | A public hostname (Cloudflare Tunnel or port forwarding) with TLS, and an SMTP account |
| The mini's address comes from DHCP; if it changes, rerun `tools/dev/mini-install.sh` (it updates `ERGPLAN_PUBLIC_URL`) or reserve the address in the router | Router setting |
| No rate limiting on sign-in-link requests; wrong-password throttling is per API process and in memory (resets on restart) | Before public launch |
| Ownership of ids sent in a request body is checked by each route (`owned_bills`, `owned_connection`), not centrally; a new body-id route must call them | When body-id routes multiply |
| LlamaParse (billx's third reader) is off on the server: LlamaIndex refused the key (401 in both regions). Until a working key is placed, a value only the OpenAI model reads (account number, energy kWh, some charges) stays unverified, and a figure both local readers misread the same way (a power factor without its decimal point) stays disputed for the client to confirm | A working `LLAMA_CLOUD_API_KEY` on the server |
| On PVVNL open-access adjustment bills billx's own arithmetic checks G08, G09 and G21 fail on the "Other Adjustment (FPPA Surcharges+Arrears)" and "Total Arrear" lines (how the layout nests them), so the bill is held for review even when every planning value is verified; the client accepts it on the hand-off screen | A billx profile change for the layout, measured on the team's golden set |
| The reading view replays billx's stored evidence step by step (each reader's readings, then agreement, then the checks); billx does not yet stream live reading events (4.2 section 9D.2), so while a file is read the page shows billx's job state and the elapsed time only | billx job events |
| billx's source is in `billx/` (the `readers-docling-llamaparse` branch, ahead of the team's GitLab `main`). The team merges it there after regenerating billx's contract examples on the Mac (they are compared with PaddleOCR's regions; on Linux two of them fail); until then the two copies differ | The billx team's merge |
| Bill search is keyword ranking (BM25) over billx's stored readings; a question-answering assistant over search and analytics (numbers as references to rows, billx 4.2 section 9C) is not built | Next |
| Recognition reads the open-access kind (captive, group captive, third party, exchange, GEOA) only from words in billx's stored line labels and slot names, not from every word printed on the bill; most bills do not print it, so the client states it on the intake review | When billx returns the bill's open-access type as a field |
| Approved settlement rules exist for UP and Maharashtra only. In Karnataka, Telangana, Punjab, Andhra Pradesh, Gujarat, Rajasthan, Tamil Nadu, Haryana, Himachal Pradesh and Assam the hand-off says "no approved settlement rules yet" and banking and set-off are not applied | As each state's OA and banking regulation is read and approved |

# Decisions log

Dated entries. Every deviation from `docs/MASTER-PROMPT.md` is one.

## 2026-10-31 — Plan approved, repository seeded

- Product name ergPLAN under jouleWise; a separate product, not part of House of Rama.
- Every client-visible number carries regulation, page and a link opening the stored PDF at that page (invariant 1).
- First states: Uttar Pradesh (NPCL, PVVNL) and Maharashtra (MSEDCL). Then Karnataka, Gujarat, Rajasthan, Tamil Nadu, Telangana, Andhra Pradesh, Punjab, Haryana at Stage 8.
- Most clients have only bills: profile synthesis from 12 bills is a Stage 2 deliverable.
- IEX prices come from CSVs uploaded by jouleWise in the application.
- The regulation reader (tariff orders → draft rule rows with citations) is built in Stage 1, not later.
- Deliverable is a live shareable plan link with voice what-if and a jouleWise analyst view; PDF export of the same page.
- Thermal: captive coal and gas with waste heat as must-run; station fixed cost treated as sunk.
- Build machine: laptop Compose to Stage 4, then a Google Cloud VM in asia-south2.
- Stack and tooling as section 4 of the master prompt.

## 2026-11-01 — Stage 0 decisions

- **Model provider: OpenAI only for the app.** The regulation reader, explanations, voice and the stage reviewer use the OpenAI key from the Mac mini (`~/Downloads/Keys.rtf`, copied into the git-ignored `.env` only). No Anthropic API key is used anywhere; Claude builds on the subscription. Master prompt section 4 updated.
- **tariff-oder is upstream.** `Ergplan/tariff-oder` already reads tariff orders into reviewed, published facts with page-level evidence. ergPLAN imports its releases (`regreader/tariff_oder.py`) instead of rebuilding extraction; a direct OpenAI reader with a verbatim-quote grounding check covers documents tariff-oder does not (OA/banking regulations, CERC orders). Master prompt section 4 and Stage 1 updated.
- **Corpus from the Mac mini.** The tariff orders in `~/Downloads/India_DISCOM_Tariff_Orders_Final_2026` and `~/Downloads/Tariff Orders` are the regulation corpus. Their index `tariff-library.json` (regulator URL, schedule page ranges) is committed at `packages/rulebooks/corpus/`; the PDFs live in git-ignored `data/corpus/` and are registered by `python -m ergplan.documents.corpus`.
- **Build workspace without Docker.** The cloud build workspace has no Docker daemon. Services run natively there (Postgres 16 via `pg_ctl`, uvicorn, `next dev`); `docker/compose.yaml` is the deliverable for the Mac mini and is not exercised in the workspace. Flagged in known-gaps until someone runs it on the mini.
- **Harmony is vendored**, not installed as a package: `Ergplan/designsystem` has no published npm package. Copied to `apps/web/public/vendor/harmony` with the commit in `ORIGIN.txt`; `tools/dev/sync-harmony.sh` re-copies.
- **The document viewer renders pages as images** (`/documents/{id}/pages/{n}.png`) with an "Open the PDF at this page" link, because embedded PDF viewers are blank in headless browsers and inconsistent across browsers. The citation link `/documents/{id}#page=N` still opens the real PDF.
- **`SourcedValue.source_refs` is a list** (at least one), where invariant 1's prose says `source_ref`: a derived value carries every input's ref.
- **Web reaches the API through `/api/*` rewrites**, so the PDF link is same-origin.
- **Stage tags are recorded in `docs/stage-tags.md`**: the build workspace's git proxy does not accept tag pushes. `tools/dev/stage-tags.sh apply` recreates them on the Mac mini.

## 2026-11-01 — Stage 1 decisions

- **`tariff_schedule.body.retail_wheeling_charge` added.** MERC bills a per-unit wheeling charge to every HT consumer below 66 kV as part of the retail tariff (MSEDCL FY 2026-27: Rs 0.81/kVAh at 33/22/11 kV, none at EHV). Without it Maharashtra's avoided cost of a grid unit would be understated. Optional; other states leave it out.
- **Golden tests are written from the build agent's own reading of each page's text layer**, independently of the reader's output, and gate approval. Where both agree the version is approved.
- **Seeded rulebooks are approved by `build-agent@ergplan`** (role analyst), so Stages 3–6 can run on approved rules. They are marked so; a jouleWise analyst should review each version in the analyst UI and re-approve (duplicate → approve) under their own name. Listed in known-gaps.
- **Analyst corrections are made through `rulebook.service.update_row`** with a review note (audited), e.g. NPCL CSS bands printed "at 11 kV up to 66 kV" read as above 11 kV; ToD `season` moved from scope to `season_note` because `months` already scopes the row.
- **Grounding accepts two worded numbers**: a value of 0 where the page says "zero"/"nil", and an exemption's `waived_pct` 100 where the page says the charge is not payable, exempt or waived. Every other number must be printed.
- **`given.where` in golden tests** filters rows on body fields (several OA components share one scope).
- **Rate block and season match on words** ("(A) Urban Schedule:" matches "urban").
- **The UP banking rule PDF on the Mac mini is a scan** (34 pages, no text layer). The UP settlement rulebook waits for OCR (tesseract is available; Stage 1 follow-up).
- **Settlement schema extended for the UPERC CRE Regulations 2024 (Reg. 12)**: `banking.cap` (percent of injection and/or of DISCOM consumption, combined higher/lower, per captive user, per period), `banking.ageing` (FIFO), `banking.requires_day_ahead_schedule`, `banking.in_block_banking_pct`, `lapse.rec_eligible`, and `set_off_order` values `captive_generation`, `banked_energy`, `bilateral`, `discom`. Additive; existing rows stay valid.
- **OCR for scanned regulations** (`documents/ocr.py`, tesseract): page text falls back to OCR words stored under `data/ocr/<sha256>/` when a page has no text layer; grounding and citations work on them. The UP CRE Regulations 2024 (34 scanned pages) were read this way.
- **Slot names in settlement rules bind to the DISCOM's ToD rows.** UP CRE Reg. 12(viii) speaks of "peak" and "off-peak" hours as defined in the prevailing tariff order: `peak` = ToD slots carrying a surcharge, `off_peak` = every other hour. MSEDCL's rows use the tariff order's own names (`normal`, `solar`, `peak`). The settlement simulator (Stage 5) implements this binding.
- **UP CRE Regulations dated 17 Oct 2025** (handwritten date on the scanned p. 1, read from the page image because OCR garbled it); applicable from notification to 31 Mar 2029.

## 1 Nov 2026 — Stage 2

- **`SourceRef` kind `bill`** (with `bill_id` and `field_path`): a value billx read from the client's own bill is neither a regulation nor a client statement. It links to the stored bill PDF at the value's page (`/bills/{id}/file#page=N`), and `SourcedValue.is_sourced` counts it as sourced. The JSON Schema `source_ref.schema.json` gains the kind with the two fields required.
- **A `needs_review` bill becomes usable when every value intake takes from it is verified by billx or confirmed by the client** (one click, or a correction). Required: bill month, energy (kWh or kVAh), recorded MD, contract demand, tariff category, and each ToD slot's energy when printed. The bill row then reads `accepted_by: bill_confirmations`. This is the per-field confirmation of invariant 7.
- **The bill PDF is stored** (`data/bill_files/<sha256>.pdf`, gitignored) so a bill citation opens the page; ergPLAN never reads it (billx does). The same file is never sent to billx twice.
- **Industry shapes are parametric YAML** (base level, working blocks per weekday, dips, ramps) that expand to the 672-value week the master prompt describes, rather than 672 literal values: easier to read, review and edit; `profile_synthesis.shape()` produces the 7 × 96 array.
- **Synthesis algorithm**: (1) the shape laid over the month, weekly offs and shutdowns at base; (2) each ToD window scaled to its energy (exact); (3) deviations from each window's mean stretched by one factor (bisection) until the month's maximum equals MD × PF — window energies unchanged. When that stretch would need negative load (flat-topped shapes), the stretch stops while the lowest block stays above half the shape's minimum and the rest of the MD is placed as one 15-minute block at the busiest block, its energy taken pro rata from the same window. Stored kW is rounded to the watt and each month's rounding residue is put back one watt at a time on blocks near the month's median, so stored monthly energy equals the bill exactly. Months without a bill: mean daily energy of the billed months, flagged extrapolated.
- **kVAh-only months** are converted to kWh with the month's power factor (0.95 assumed when absent) for the profile; the stored intake keeps the bill's unit.
- **A ToD split whose slot names carry no hours is not used** (the month's total is), with a warning to the client, rather than guessing which order window `Tod-1` means.
- **IEX vintages**: one vintage per file; a file overlapping a live vintage of its segment is refused (409) unless `replace`, which marks the old vintages superseded and keeps their rows (pinned runs replay identically). Duplicate (day, block) rows: identical ones dropped; disagreeing ones resolved to the latest `Scraped At` (or the later row) and counted. The jouleWise files are `.xlsx` with sheet `15min`; CSV is accepted too.
- **Real-bill e2e runs on its own database** (`ergplan_e2e`) so it can run while the unit suite truncates `ergplan_test`.

## 1 Nov 2026 — Stage 3

- **Rules are loaded in the API layer and passed to pure engines.** `engine/` takes `RuleView`s and quantities; `platform/routers/cost.py` reads `rules_approved` through `rulebook.repository` (invariant 2) and calls the engines. `engine/scope.py` builds the context and picks rows; the scope operators stay in `rulebook/scope.py` (tested there), so one grammar serves the analyst sandbox and the engines.
- **Excess demand is charged in addition to the demand charge on the whole recorded demand**, at the row's multiple of the demand rate on the excess: UPERC general provisions 7(ii)(b) ("200% of the normal rate apart from the normal fixed / demand charges") and MERC's 150% clause read the same way.
- **A bill is evaluated on the tariff in force at its period end** (`period.to`, else the bill month). Avoided cost uses the tariff in force on `as_of` (default today) with each profile month choosing its seasonal and ToD rows: the plan faces today's tariff, not last year's.
- **Replay groups lines** (demand, excess demand, energy and ToD together, wheeling, FPPCA, duty, PF, LF, prompt payment, minimum, taxes, and each unmodelled line by its label), because DISCOMs print ToD inside energy (NPCL, UPPCL) or as a separate line (MSEDCL). Credits (rebates, subsidies) are negative. Printed totals and payable amounts, arrears and adjustments are left out. When a layout prints energy only as ToD zone information lines, those are the billed energy.
- **ToD zones on the bill are matched to the approved slots by the adjustment the bill applied** (a zone printed at its full rate, base × (1 + p), or as the adjustment alone, base × p). A zone whose adjustment no approved slot carries is put on the nearest slot and reported, so a wrong rule shows as an unexplained energy difference. This is how the MSEDCL peak rule (+20% read, +25% billed) was found and corrected from the MYT order's footnote.
- **Bill status is the worst of its line statuses.** A line is explained only by a named gap (engine/gaps.py, listed in known-gaps) or a billx `printed_inconsistency` flag. `demand_proration` is recognised only when billed / computed equals days / (365/12) within 0.02%.
- **Bills dated before the approved tariffs are replayed as `tariff_period`** (explained, nothing computed) rather than against a later order.
- **The marginal avoided cost is a 12 × 96 matrix**, because the retail rate depends only on month and time of day; the 35,040 block values are that matrix laid over the calendar. Components the rulebook does not hold (FPPCA, duty) are left out and named.
- **kVAh-billed schedules convert to INR per kWh with the bills' kVAh/kWh ratio** (bill-sourced), else 1 / the bills' power factor, else 1 / 0.95 assumed.
- **`SourceRef.url` is a computed field** in every serialised ref (`/documents/{id}#page=N` or `/bills/{id}/file#page=N`) and is dropped on input, so refs round-trip.
- **Rulebook corrections found by the replay were approved by `build-agent@ergplan`** through the normal gate (duplicate, edit with review note and field citation, golden tests, approve): MSEDCL `tod_slots` v3 and NPCL and UPPCL `tariff_schedule` v2. The golden test "peak +20%" was wrong and was corrected.
- **The replay test runs on billx's stored readings of the real bills** (`data/bills/billx-results/<sha256>.json`, gitignored), so it needs no network; reading a bill through billx again would cost about USD 0.2 each.

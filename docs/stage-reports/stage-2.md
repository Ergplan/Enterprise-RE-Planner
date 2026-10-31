# Stage 2 report: intake and site

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## What was built

**Data model (migration 0006).** `clients`, `sites`, `connections`, `bills` (billx's whole result as JSONB, `accepted`, `accepted_by`), `bill_confirmations`, `assets`, `load_profiles` (versioned, provenance check constraint, compressed Decimal kW, `method` JSONB), `price_vintages`, `price_series`.

**Bills (invariant 7).**
- `intake/billx_client.py` speaks contract esgos-1.1 over HTTP: it submits the bill, then polls past billx's 50-second wait.
- `intake/bills.py` does four things:
  - stores each file once (the same file is never read twice);
  - lists every value intake takes, with billx's verification and page;
  - records one-click confirmations or corrections in `bill_confirmations`;
  - marks a `needs_review` bill usable (`accepted_by: bill_confirmations`) once nothing required is left unconfirmed.

  Values from a bill carry a new `SourceRef` kind, `bill`, which opens the stored bill at the value's page.
- billx profile ids map to DISCOMs.
- Printed tariff codes map to the order's categories, for example "HV-2(L & H POWER)" → HV-2 and "105 HT-I A" → HT I(A). The mapping is recorded as an assumption.

**SiteIntake (`intake/site_intake.py`, `intake/defaults.py`).**
- Every field is a `Fact` with a value, a provenance (bill, client_stated or assumption) and a SourceRef.
- Validation covers:
  - DISCOM/state consistency;
  - known shapes;
  - weekdays;
  - month uniqueness;
  - positive energy and demand;
  - power factor range;
  - shutdown days;
  - ToD split versus total and quarter-hour times;
  - shift days and times;
  - asset params per kind. The captive-thermal set follows the stage prompt; the reviewer's checklist is applied to the others.
- Defaults are each an `assumption` ref with a note:
  - voltage from the category;
  - two-shift pattern;
  - weekly off from the shape;
  - power factor 0.95.
- `from_bills` prefills from accepted bills. `build` persists everything and synthesises a profile. The intake is stored with the profile so step 4 can edit it and rebuild.

**Profile synthesis (`intake/profile_synthesis.py`).**
- Eight parametric industry shapes are in `packages/profiles/shapes/`, each with notes.
- Monthly energy is exact to the paisa-equivalent watt: stored Decimals sum to the bill.
- The ToD split is matched within 0.1%.
- The month's maximum equals MD × PF, by a deviation stretch. When a flat-topped shape cannot reach the MD, the stretch stops before load goes too low and the rest is placed as one 15-minute peak block.
- Weekly offs and shutdown days are honoured.
- Months without a bill take the billed months' mean daily energy and mean peak, and are flagged as assumed.
- The full method and per-month achieved values are kept in `method`.

**Measured upload (`intake/measured_upload.py`).** Takes a CSV of 15-minute kW or kWh. Gaps of up to 8 blocks are interpolated and counted; longer gaps reject the file.

**IEX loader (`intake/iex_loader.py`).**
- Reads jouleWise's `.xlsx` snapshots (sheet `15min`) and CSV.
- Segment comes from the caller, the file name (DAM, RTM, GDAM, G-TAM, HP-DAM, TAM) or a `Session ID` column.
- Duplicates are dropped; conflicts are resolved to the latest scrape.
- One vintage per file. An overlap is refused (409) unless the upload says replace, which supersedes the old vintage and keeps its rows for replay.
- A coverage query feeds the calendar.

**API.** Twelve endpoints are listed in `docs/architecture.md`:
- `/bills`, `/bills/{id}`, `/bills/{id}/file`, `/bills/{id}/confirm`;
- `/intake/shapes`, `/intake/from-bills`;
- `/sites`;
- `/connections/{id}`, `/connections/{id}/intake`, `/connections/{id}/profile`, `/connections/{id}/profile.csv`, `/connections/{id}/profile/measured`;
- `/prices`, `/prices/vintages`, `/prices/coverage`.

Profile months are returned as `SourcedValue`s and appear in `docs/field-trace.md`.

**UI (Harmony).**
- **Step 1, `/plan/intake`**, has three doors:
  - drop bills: each bill shows its values with verification and page, and the client confirms or corrects highlighted values;
  - tell (voice): a placeholder until Stage 7;
  - type the facts.

  It then shows "What we understood", with a provenance chip on every value. A bill chip opens the bill page; an assumption chip carries its note.
- **Step 4, `/plan/site?c=`** shows:
  - the profile: the year's energy, the highest 15-minute demand, months from bills, a week chart with the MD line, and twelve months with their sources;
  - the site description and existing assets, with a rebuild button;
  - a CSV download of all 35,040 blocks.
- **Analyst page, `/prices`**: upload, vintages, and a coverage calendar per segment.

The browser flow was checked end to end with a real NPCL bill: upload, confirm, review, build, site page. The real RTM and DAM files were loaded through the API: 37,095 and 37,056 blocks, 1 Sep 2025 to 24 Sep 2026.

**Tests.**
- Unit tests cover:
  - synthesis properties (energy, ToD, peak, offs, shutdowns, extrapolation, exact stored Decimals, all shapes);
  - IEX parsing (both layouts, segments, duplicates and conflicts, errors, overlap and replace, coverage, real files when present);
  - every SiteIntake validation and default;
  - category mapping;
  - bills ingest, review and confirmation;
  - measured upload;
  - `bill` and `measured` refs.

  They use a fake billx answering with billx's own contract examples (synthetic, copied with origin noted).
- Integration tests cover every new endpoint.
- **End-to-end (`tests/e2e/test_stage2_intake.py`, `-m external`)** ran against the running billx with two real bills from different DISCOMs:
  - the NPCL HV-2 bill for June 2026;
  - the MSEDCL HT I(A) bill for April 2026.

  Each came back `needs_review`, was confirmed field by field through the API, and became a connection with twelve months and a synthesised profile. The billed month's energy matched exactly and its maximum equalled MD × PF. **Both pass.**
- Totals: 153 API tests (plus 3 external end-to-end tests) and 11 web tests. The watcher is green.

## Definition of done

| Check | State |
| --- | --- |
| e2e passes on two real bills from different DISCOMs | Met (NPCL, MSEDCL) |
| A needs_review bill round-trips through confirmation | Met (both real bills, plus the fixture tests) |
| Six IEX CSVs loaded with vintages | **Not met: two of six.** Only RTM and DAM files exist in `data/iex/`. GDAM, G-TAM, TAM and HP-DAM files are needed; the loader detects them by name. |
| Reviewer clean | No open code defect; remaining findings are listed below with reasons |

## Skipped, and why

- **Typing ToD hours in the UI.** The API accepts typed windows (`MonthFacts.tod`), but step 1 has no editor yet.
- **Back-solving units from a bill amount.** This needs the approved tariff (Stage 3). The intake takes energy as given.
- **Voice door.** Placeholder until Stage 7, as the stage prompt says.
- **Docker.** The compose stack still has not run in this workspace (no daemon). The services ran natively.

## Deviations

All are dated in `docs/decisions.md` (1 Nov 2026, Stage 2):
- the `bill` SourceRef kind;
- the per-field acceptance rule;
- bill PDFs stored for citation;
- parametric shapes instead of 672 literal values;
- the synthesis algorithm, including the single peak block;
- kVAh months converted with the power factor (0.95 assumed when absent, carried as an assumption ref);
- ToD splits without hours not used;
- the vintage overlap and replace rules;
- the e2e on its own database.

## Reviewer findings and resolution

There were four review rounds; `stage-2-review.md` holds the last one.

Fixed:
- A document ref's link now opens the stored PDF at its page (`/api/documents/{id}#page=N`).
- A kVAh month's energy carries the conversion assumption, with a test.
- Field-trace owners for the profile months are now composite (`series_kw + method`).
- Shift days and times are validated.
- The bill link uses the API's `url`.
- `measured` and `bill` refs count as sourced, with a test.
- `tsconfig.tsbuildinfo` was being tracked (a 285 KB build cache that truncated the review diff). It is now gitignored.
- The reviewer tool now skips PDFs and the large JSON fixtures.

Not changed, with reasons:
- **"Float arithmetic inside synthesis."** Internal arithmetic uses numpy. Every stored and returned value is Decimal, and stored monthly energy is exact (tested). Rule 15 concerns stored and returned values.
- **"`max_kw` never client_stated."** It is client_stated when the client types the MD; `_refs` passes the input's ref through.
- **"Coverage ignores segment."** The query filters by segment and live vintages, and a test asserts it.
- **"Reviewer tool calls `.decode` on a str."** `text=True` was removed in the same change; the tool ran four times.
- **"Measured refs not clickable."** By design: a meter file is not a regulation page.
- **"kVAh months ignore a typed PF."** The conversion uses the month's PF fact when present and 0.95 only when absent.

## Open questions

1. GDAM, G-TAM, TAM and HP-DAM files for `data/iex/`? They are needed for the "six segments" check and for Stage 6 scenarios that buy on those markets.
2. Some bills print ToD slots without hours (`Tod1`–`Tod4` on NPCL, `Tod-1..3` on the synthetic PVVNL). Should ergPLAN keep a per-DISCOM table mapping slot names to the order's windows? Or should billx return the hours?
3. MSEDCL HT voltage defaults to 22 kV. Is 11 kV or 33 kV more common among your Maharashtra clients?
4. For months without a bill, is flat mean daily energy acceptable until clients give twelve bills, or should seasonality come from an industry profile?

## Cost

- **billx reads:** 7 real-bill reads at about USD 0.18–0.24 each (OpenAI through billx), about USD 1.5. This includes two reads lost to a test-database deadlock when two suites shared a database; the e2e now has its own.
- **Reviewer:** four gpt-5.1 calls, about 660k tokens in and 12k out, about USD 0.9.
- **ergPLAN app:** no model calls in Stage 2.
- **Builder:** Claude subscription.

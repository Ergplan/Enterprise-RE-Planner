# Stage 1 report — rulebook and regulation reader

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**Data model (migrations 0002–0005).** `jurisdictions`, `rulebook_versions`, `rules`, `rule_tests`, `rule_test_runs`, `audit_log`, view `rules_approved`. Triggers in the database, not only in code:
- `ergplan_audit`: every write to `rules`, `rulebook_versions`, `rule_tests` needs `ergplan.actor` and is appended to `audit_log` with before and after.
- `ergplan_rules_frozen`: rows of a non-draft version cannot change.
- `ergplan_version_gate`: approval needs role `analyst` and every golden test of the family and jurisdiction run on this version and passed (at least one); superseded and rejected are final.
- `rules_approved` shows approved rows effective on the evaluation date (session variable `ergplan.on_date`, default today). Status check constraints; foreign keys from rules and golden runs.

**Rulebook package.** Family JSON Schemas loaded with refs; `scope.matches` (strict: a context missing a constrained field never matches; category codes normalised; inclusive and exclusive voltage bands; months, commissioning dates, sources incl. `any_re`); `service` as the single writer (propose, revise, update_row, delete_row, duplicate, run_golden, approve with supersession, reject); `repository.approved_rules` / `applicable` (nearest jurisdiction first: DISCOM → group → state → CERC) as the engines' only door; `sandbox` for drafts; golden tests from files with `where` filters; YAML export of approved versions to `packages/rulebooks/states/` and restore through the same gate, byte-identical.

**Regulation reader.**
- `direct`: pages → OpenAI (`gpt-5.1`, prompt `regreader_<family>_v2`) → grounding → schema. Grounding rejects a row whose quote is not on its cited page (whole, or verbatim fragments joined by "…", or on OCR pages the quote's words in order within a tight window) or whose numbers are not printed on a cited page (by magnitude; "zero"/"nil" and "not payable/exempt/waived" accepted for 0 and waived_pct 100 only).
- `tariff_oder`: maps published facts from `Ergplan/tariff-oder` (API or export) into tariff_schedule, tod_slots and oa_charge rows, each field cited by its fact's evidence; unmappable facts listed.
- `locate` (topic pages), `voltage` (band phrases), OCR fallback (tesseract) for scanned regulations.

**API.** `/rulebooks/*` (jurisdictions, families, versions, rows, golden, approve, reject, duplicate) and `/regreader/*` (locate, direct, tariff-oder), analyst identity by dev headers until Stage 8.

**Analyst UI.** `/rulebooks` (versions by jurisdiction, status, golden state), `/rulebooks/[id]` (each row with schema-described fields, inline editing of drafts, quote and page links, reader and model, review notes, golden results, approve / reject / duplicate), a "Read into a rulebook" panel on the document viewer.

**Seeded from the real orders (12 approved versions, 91 golden tests).**

| Jurisdiction | Family | What | Source (PDF page) |
| --- | --- | --- | --- |
| npcl | tariff_schedule | HV-2 urban: Rs 300/290/270/270 per kVA/month, Rs 7.10/6.80/6.40/6.10 per kVAh by voltage band | UPERC NPCL FY 2026-27 order, p. 387 |
| npcl | tod_slots | Summer and winter ToD, ±15% | p. 388 |
| npcl | oa_charge | Wheeling Rs 1.03/kWh (embedded and EHV exemptions noted); CSS HV-2 0.57/0.51/0.36/0.36; additional surcharge 0 | pp. 315, 321, 323 |
| uppcl | tariff_schedule, tod_slots | HV-2 urban (same rates); ToD differs from NPCL | UPERC State DISCOMs FY 2026-27 order, pp. 445–446 |
| uppcl | oa_charge | Wheeling Rs 0.9318/kWh; OA distribution losses 13.07/8/3/1%; CSS HV-2 0.38/0.49/0.33/0.14 | pp. 379, 384, 386 |
| UP | oa_charge | Intra-state transmission Rs 0.3075/kWh; ISTS loss 1.56%; STU loss 3.18% | pp. 377, 384 |
| UP | settlement | Captive RE banking: 15-min accounting, monthly carry-forward capped at the higher of 25% of injection or 30% of DISCOM consumption per user, FIFO, day-ahead scheduling, off-peak energy only off-peak, charge 8% (solar/wind/hybrid) or 12% (biomass, small hydro), lapse without compensation (REC-eligible), set-off captive → banked → bilateral/exchange → DISCOM; none for third-party sale | UPERC CRE Regulations 2024 (scanned, OCR), pp. 14–20 |
| msedcl | tariff_schedule | HT I(A) and HT II, EHV and HT: Rs 650/kVA/month, Rs 8.44 and 13.72/kVAh, retail wheeling Rs 0.81/kVAh below 66 kV; effective 1 Apr 2026 | MERC Case 75/2025 post-remand order, p. 100 |
| msedcl | tod_slots | normal 00–09, solar 09–17 (−15% Apr–Sep, −25% Oct–Mar), peak 17–24 (+20%) | pp. 77, 79 |
| msedcl | oa_charge | CSS HT I(A), HT II Rs 2.11/kWh | p. 106 |
| msedcl | settlement | Monthly ToD-slot banking, no carry forward; normal → normal + solar, solar → solar, peak → all | pp. 77–79 |

**Tests.** 74 API tests (rulebook invariants: unattributed writes refused by the database, absurd draft invisible to engines, approval needs analyst and green goldens in service and database, approved rows frozen, supersession, audit actors, effective dates in the view itself; grounding; tariff-oder mapping against a contract-shaped fixture; reader with stubbed model; every endpoint; OCR fallback; committed rulebooks round trip) + 7 web tests + the real-input e2e (`-m external`: NPCL p. 387 read, grounded, approved, exported) which passes.

## Skipped, and why

- Maharashtra OA wheeling, losses, additional surcharge and banking charge; UP OA exemptions; ISTS waiver, regulatory limits and net metering rulebooks: listed in `docs/known-gaps.md` with the stage that adds them. The DoD's "approved tariff_schedule, tod_slots, oa_charge with page citations for both states" is met.
- Golden tests number 91 against the DoD's "at least five per state per family": tod_slots and oa_charge in UP have 6–10 each; MSEDCL oa_charge has 4 (one table, one value).

## Deviations

All dated in `docs/decisions.md` (1 Nov 2026): `retail_wheeling_charge`; settlement schema extensions for the UP CRE Regulations; `24:00` slot ends; named RE sources in scope; slot-name binding; golden tests written from the page by the build agent; versions approved by `build-agent@ergplan` pending a jouleWise analyst; OCR; worded zero and waiver in grounding.

## Reviewer findings and resolution

Five review rounds (`docs/stage-reports/stage-1-review.md` has the last). Fixed from the reviews:
- `rules_approved` did not apply the evaluation date → the view now does (migration 0003) and a raw-query test proves it.
- The reader reached into schema-registry internals → `scope_schema()`.
- No status check constraint → migration 0004.
- Unknown model prices silently cost 0 → the call row says so.
- Negative values compared with sign against unsigned printed numbers → compared by magnitude.
- No foreign keys from rules and golden runs → migration 0005.
- Missing tests for `/rulebooks/families`, `/regreader/locate` (success and 404), the reader's 502/503 branches and the OCR fallback → added.
- The reviewer saw a truncated diff and reported tests as missing that existed → it now receives code and tests first and a larger budget.

Not changed, with reason:
- Tests that run raw `UPDATE rulebook_versions … status='approved'` (flagged in the last round): they are the attack the triggers must refuse, and they pass because the database refuses it.
- `regreader` imports `providers` (flagged in round 1, withdrawn by the reviewer): regreader is the designated model caller; the architecture test forbids it only in engine, settlement, optimizer and rulebook.
- Season and rate-block word matching, decimal comparison of golden values, ambiguity counting as failure, broad `locate` patterns: by design (documented in the code).
- No client-facing `SourcedValue` yet: Stage 1 has no client numbers; Stage 3 adds them.

## Open questions

1. The 12 rulebooks are approved by `build-agent@ergplan`. Who at jouleWise should review and re-approve them under their name?
2. NPCL and UPPCL tariffs come into force seven days after newspaper publication. Do you have the publication dates? The versions carry 2 Jul 2026 for now.
3. Which LT industrial categories matter first (UP LMV-6, MSEDCL LT V)? Only HT categories are seeded.
4. Should the HV-2 rural schedule (7.5% rebate on the 11 kV base, no ToD) be modelled now, or is it rare among your clients?
5. Is there a tariff-oder instance with published UPERC releases I can point `TARIFF_ODER_URL` at, so the adapter runs against live facts?

## Cost

Reader: 22 OpenAI calls, 106,270 tokens in / 42,930 out, about USD 0.56 (list prices, `model_calls`). Reviewer: five gpt-5.1 calls, about 750k tokens in, about USD 1.0. Builder: Claude subscription.

# Stage 3 report: real bills, the sample run and the first profiles

14 Oct 2026, branch `stage-3` (from `main` at `stage-3-start`, after release 0.1).

## Done-when status

| Item | Status |
| --- | --- |
| The unconfirmed set runs end to end with no crash and a status for every file | **Yes**: 65 files (11 discom folders and `unsorted`), 0 errors, a status for each (`docs/accuracy/2026-10-14-unconfirmed-survey.md`) |
| The report holds no value or name | **Yes**: counts, status codes, reason codes, check ids and field paths only |
| The runbook's steps are exact | **Yes**: `docs/runbook.md`, "Confirm the sample set", seven numbered steps |
| Lint and tests green | **Yes** (the final gate run before the merge) |

## 3.1 The survey of the team's bills (counts only; nothing here is an accuracy figure)

Run without model keys and with `allow_cloud_model: false`, so the only readers were the
text layer and local OCR, and the honest outcome for every file is `model_not_allowed`
(5.3): a field only a model could prove is never passed on one reading.

- **65 files, 0 crashes, median 0.5 s per file** once the OCR words are cached (the first
  pass took 25 to 160 s per file, 1 to 7 pages).
- **Discom identified on 47 of 65 files** from the printed name, in English, Hindi or the
  short code; after the whitespace-tolerant match and the single-word patterns added in this
  stage. The 18 `none` are mostly PVVNL scans and photos whose name is a logo image, three
  PVVNL digital PDFs that print no recognisable name, one TGSPDCL and three unsorted files.
  A profile `match` on another printed token (a division name, a URL) will cover those once
  the team has confirmed a bill of each.
- **What the generic label rule found on real layouts** (required fields with a value, and
  in brackets those two readers agreed on): APCPDCL digital: account number and net payable
  on all 3 (3); PSPCL digital: kWh, bill month, net payable on all 3 (3); MSEDCL digital:
  bill month on all 6 (6); TANGEDCO digital: net payable on 2 (2); DVVNL: bill month and net
  payable (1); NPCL and AVVNL scans: account number and bill month found by one reader only
  (0 agreed); GESCOM: nothing. **The reading period was found on no real bill**: the
  layouts print it under labels the generic list lacks. That is the expected state before
  profiles exist (`profile.status` is `draft` or `none` on every file): with the keys in
  `.env`, Model A reads every field and the text layer, OCR or Model B confirm them; with a
  confirmed sample per discom, the version's own labels make the local readers sufficient
  for digital PDFs.
- Document type: every file classified `electricity_bill` by the local signals; none refused
  as `not_a_bill`.

## 3.2 Profiles

`profiles/<id>/discom.yaml` now exists for all eleven discoms in the sample (AVVNL and PVVNL
with their draft synthetic versions; MVVNL, DVVNL, MSEDCL, GESCOM, APCPDCL, NPCL, PSPCL,
TANGEDCO, TGSPDCL with match patterns and no version). MVVNL and DVVNL `extend` PVVNL.
`match_discom` tolerates line breaks and doubled spaces inside a printed name.

## 3.3 The studio

The confirmation screen pre-fills from the engine's own reading (every reader's value, the
verification, the checks and the review reasons); the runbook's seven steps confirm a bill in
one pass. Not changed in this stage beyond the runbook.

## 3.4 The run report

`docs/stage-reports/run-2026-10-12.md`.

## Decisions

- A refused bill (`model_not_allowed`, `unreadable` without a model) carries the discom,
  the profile and every field as read with its verification, as 5.2 says for bills that
  don't pass; it was dropping them.
- The survey (`billx eval --unconfirmed DIR`) is the only way the builder touches real
  bills: it reads files programmatically and reports counts; no value, name or file name
  leaves it.

## Model spend

None.

## Pace

- Wall clock: about three hours, mostly the two survey passes (OCR on about 150 real pages
  the first time) and the full-suite gate.
- Next bottleneck: the keys and ten confirmed bills per discom (`docs/pending-for-user.md`,
  items 13 and 14).

# Stage 0 report: safe repository, build loop, synthetic bills, confirmation tooling

12 Oct 2026, branch `stage-0` (from `main` at `stage-0-start`). Not merged: run mode is
staged through day 4 (O9), so a person reviews and merges.

## Done-when status

| Item | Status |
| --- | --- |
| doctor.sh passes on the Mac | **No**: 21 items fail (re-run in the second pass), all needing a person or an admin (FileVault, sleep settings, Homebrew tools, the claude CLI, Docker memory, the external drive, keys, model calls, the mirror job). The checks themselves work |
| No real bill in the tree | **Yes**: none was ever added; the identifier search (9 drafted identifiers) finds nothing |
| The builder's tests green natively and in CI | Natively **yes** (43 tests, ruff clean). CI **not run**: no GitHub repository yet |
| Both images build and land on ghcr.io | arm64 engine image builds locally (91 MB) and runs. ghcr.io **waits on the GitHub repository** |
| PaddleOCR (or the recorded fallback) reads a synthetic bill on all three platforms | **Yes**: PaddleOCR on macOS arm64 and linux/arm64; RapidOCR (recorded fallback) on linux/amd64 |
| The studio confirms a synthetic bill end to end | **Yes**: checked in a browser; the manifest entry matched the truth file |

## What changed

- 0.0 `tools/mac/`: doctor.sh, session.sh, the nightly mirror and its launchd job (written,
  not activated: no drive), the nightly evaluation job (written, inactive until Stage 11),
  install-jobs.sh, the OCR check; `.claude/settings.json` allow-list; the one-token model
  call `billx/reader/providers/ping.py`.
- 0.1 No real fixtures existed (new repository). `tools/identifiers.py` (tracked files, a
  directory, an image tar, stdin) and gitleaks in CI; a draft identifier list in
  `~/billx-data/client-identifiers.txt`.
- 0.2 The section 10.4 layout; the import-boundary test.
- 0.3 `tools/watch/watch.py` → `.status/checks.json`; `.github/workflows/ci.yml` (checks,
  gitleaks, both images to ghcr.io, identifier search over the amd64 image, release copy to
  esgOS's registry, native amd64 OCR check); `docker/engine.Dockerfile`.
- 0.4 `billx synth` (session B): 42 synthetic files with truth files, deterministic.
- 0.5 The studio's confirmation mode with one-model pre-fill and the golden manifest
  (session C). The browser check found Confirm and Not printed clipped at 1024 px; fixed.
- 0.6 (second pass, same day) Part A saved as `docs/developer-guide.md` and Part C as
  `contract/esgos-1.0/contract.md`, both byte for byte as supplied.
- 0.7 (second pass) `docs/esgos-changes-2026-10-11.md` saved as supplied; `docs/decisions.md`
  opens with one entry per item (1 to 11), each pointing at its sections. The supplied list
  is a rebuild from the build prompt's summary (its own note); the original is still asked
  for. Reading the guide and contract against the build prompt gave one real conflict,
  `profile.status` (`final` in contract 1.0, `verified` in 6.2), defaulted and sent to
  pending-for-user, and the mapping from the provisional field paths to the contract's for
  Stage 1.1 (decisions.md, "Stage 0.6 and 0.7").
- The 61 bills supplied are in `~/billx-data/golden/unconfirmed/<discom>/` with
  `intake.csv`; none is confirmed yet.

Defaults chosen are in `docs/decisions.md` under "Stage 0"; open items in
`docs/pending-for-user.md`.

## Sample bills (by discom and input kind; no values)

| Discom | Digital PDF | Scan | Photo |
| --- | --- | --- | --- |
| AVVNL | 0 | 6 | 0 |
| PVVNL | 4 | 11 | 1 |
| Others (Stage 10): MVVNL 16, MSEDCL 6, GESCOM 4, APCPDCL 3, NPCL 3, PSPCL 3, TANGEDCO 2, DVVNL 1, TGSPDCL 1 | | | |

## Model spend

None: no product keys are configured. Builder: this Claude Code session (Max plan).

## Pace

- Wall clock 11:50 to 12:40 IST, about 50 minutes; three sessions (this one, B on 0.4,
  C on 0.5) for about 1.9 session-hours.
- Hours lost to plan limits: 0.
- Longest single wait: the linux/amd64 OCR image built and run under emulation (about
  15 minutes), in the background.
- Second pass (0.6, 0.7 and re-running the checks): about 15 minutes, one session.
- Next bottleneck: people. The GitHub repository and the Mac's admin items gate the rest of
  Stage 0; keys gate the studio's pre-fill and Stage 1.2. Contract 1.0 is now in the tree,
  so Stage 2 no longer waits on a document.

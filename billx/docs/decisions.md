# Decisions

## esgOS changes (11 Oct 2026, from Joulewise)

One entry per item of `docs/esgos-changes-2026-10-11.md`. Each overrides anything in build
prompt 4.1 that conflicts and is not reopened. That file says of itself that it was rebuilt
from build prompt 4.2's summary and answered decisions, not the original list; its item
numbers are therefore the rebuild's (see "Change list numbering" under Stage 0.6 and 0.7).

| # | Change | Where the build carries it |
| --- | --- | --- |
| 1 | esgOS (`Ergplan/esgOS`) is billx's first customer and goes live within days | 1 (priorities), 6.6, 13.1 |
| 2 | esgOS accepts OpenAI and Anthropic as configured providers for bill reading | O17, 5.1 (`model_b`), 5.3 (scans and photos pass on two-provider consensus from Stage 2), 10.3 |
| 3 | esgOS accepts contract 1.1, written and served, not proposed | 6.1, 6.5, Stage 2.6 |
| 4 | esgOS calls the hosted service on the `esgos` key in `esgos-1.1` mode with permanent storage; the embedded image from its own registry until then; the switch is a URL and token change, then esgOS resubmits every stored bill once | O21, 6.6, 10.2, Stage 3.8 and 3.9 |
| 5 | Unverified layouts pass for esgOS (the `esgos` key and the embedded image) under the 5.2 rules, with `profile.status` on every bill | O10, 6.1a, 6.6 (`accept_unverified_layouts`), 12.4 (where it is called "change 4") |
| 6 | What esgOS consumes: the bill's status is `passed` | 6.5 items 6 and 7: the follow-up that esgOS consumes `accepted`, so human-confirmed bills reach it; listed in pending-for-user for esgOS's build agent |
| 7 | Gas bills are read generically right after Stage 2 | Stage 2b, 6.1a (`gas_not_yet_supported` until then) |
| 8 | esgOS gets insights on every passed bill and owns its own leads | 6.6 (`insights: true`, `savings_leads: false`), 9.3, Stage 6a |
| 9 | esgOS's sign-up terms include billx's; the `esgos` tenant's acceptance at key issue covers its users | O16, 9A.1 |
| 10 | Local OCR timing: Stage 4, as planned | O20, 5.3, Stage 4 |
| 11 | billx never creates branches in `Ergplan/esgOS` | O21, 6.6, Stage 9.4 |

## Stage 0 (12 Oct 2026)

- **Repository.** No billx repository existed on the Mac and none was supplied, so billx
  starts as a new repository at `~/billx` (the path section 3.1 fixes). The person's folder
  `~/Documents/Bill Reader APplication/` holds a link to it. Stage 0.1 ("move tests/samples,
  real fixtures, examples and screenshots out") and 0.2 ("move modules into the 10.4
  layout") therefore had nothing to move: the layout is created empty and no real bill has
  ever been in the tree. There is no GitHub remote yet (pending-for-user).
- **Python 3.12 from uv, not Homebrew.** This Mac has no Homebrew and the build account has
  no admin rights; `uv` (already installed with `pip --user`) provides CPython 3.12.14 for
  the project venv. Homebrew-only tools (gh, tmux, tesseract, cloudflared) wait for an admin
  (pending-for-user).
- **Provisional guaranteed-field list** (`config/guaranteed_fields.yaml`). Contract 1.0's
  lists are in Part C of the Developer Guide (supplied later the same day; see Stage 0.6
  and 0.7 below for the path mapping). The file holds only the
  fields the build prompt names (5.6, 6.4, 6.5, 13.1 critical fields, 2b.2), marked
  `provisional-0`. Stage 1.1 replaces it with the contract's list word for word.
- **Bills placed for the sample set.** The 61 files supplied on 12 Oct 2026 were copied (not
  moved) to `~/billx-data/golden/unconfirmed/<discom>/` with `intake.csv` (discom, input
  kind, pages, sha256). They join the sample set only when a person confirms them in the
  studio (12.1); nothing is in the golden manifest yet.
- **Client identifiers.** `~/billx-data/client-identifiers.txt` was drafted from the bills'
  text layers (GSTIN, PAN, account numbers in file names). Consumer names and numbers that
  appear only on scans and photos must be added by a person; the CI secret
  `CLIENT_IDENTIFIERS` gets the same list.
- **gitleaks in CI** runs as the official container CLI; the gitleaks GitHub Action needs a
  paid licence for organisation accounts.
- **esgOS registry path** is a repository variable (`ESGOS_REGISTRY`, the full image path)
  and its key the secret `ESGOS_REGISTRY_KEY` (a service-account JSON, `_json_key` login,
  as Artifact Registry expects for project `esgos-510707`). The release job is skipped until
  both exist.
- **Model ids** (O2): Model A `openai:gpt-6.1-sol`, Model B `anthropic:claude-sonnet-5-5`,
  reviewer `openai:gpt-6-astra` (on `OPENAI_BUILD_REVIEW_KEY`), assistant chat model
  `openai:gpt-6.1-sol` until O13 chooses. All in `.env`; `doctor.sh` calls each once.
- **The builder may not read `~/billx-data` or `.env`** under the Claude Code allow-list
  (`.claude/settings.json`). People see bills in the studio; the live sample run (1.8) is a
  short attended session.
- **Nightly mirror** is written (`tools/mac/mirror.sh`, launchd job at 01:30 IST) but not
  activated: no external drive is mounted, so it could only fail. `tools/mac/install-jobs.sh`
  activates it once the drive is set in `.env` (`BILLX_MIRROR_VOLUME`). The evaluation job
  (02:00) is written and stays inactive until Stage 11.
- **Local OCR** (`tools/mac/ocr_check.sh`, a synthetic page with known words): PaddleOCR
  3.7 (paddlepaddle 3.3.1) reads it natively on macOS arm64 and in the linux/arm64 image.
  In the linux/amd64 image (built under emulation on the Mac) PaddleOCR fails inside its
  oneDNN executor (`NotImplementedError ... ConvertPirAttribute2RuntimeAttribute`), so, as
  section 3.1 says, **RapidOCR is the local reader on linux/amd64**; it reads the page. The
  check is re-run on a native amd64 runner in CI before Stage 4 relies on it.
- **Studio (0.5).** Model calls live in `billx/reader/providers/` and prompts in
  `billx/reader/prompts/` (10.4's reading of rule 9; a test fails on a model-SDK import
  anywhere else). Shared settings in `billx/core/settings.py` (`BILLX_CONFIG_DIR`,
  `BILLX_DATA_DIR`, `BILLX_ENV_FILE`). `config/providers.yaml`: timeout 120 s, 3 attempts,
  429 waits 60 s then 120 s, 5xx waits 5 s, 4,000 output tokens, `max_cost_usd_per_call`
  1.00; temperature per model, unset until the live check says whether the model accepts
  0 (invariant 6). `config/prices.yaml` holds **placeholder** prices (every usage record
  says `prices_placeholder: true`). Model A runs on the OpenAI Responses API with JSON
  output and SDK retries off. Pre-fill numbers stay literal text. One usage record per
  call: ids, model, prompt version, attempts, tokens, costs, timing, status; never values.
  A save needs every field confirmed, typed or `not_printed`; seconds run from page render
  to save; pre-fill match is exact string equality (normalised comparison is Stage 1).
  Split: sha256 of `"{seed}:{sha256}"`, first byte odd = held out, seed 20261012, recorded
  `tuning` until Stage 11 (`config/studio.yaml`). The studio binds 127.0.0.1 as a constant.
  Its field table was made to fit narrow windows after the browser check found Confirm
  and Not printed clipped at 1024 px.
- **Synthetic bills (0.4).** Two bills per electricity layout per seed (`avvnl-ht-synth-v1`,
  `pvvnl-hv2-synth-v1`), each as a digital PDF, an image-only scan PDF and five photo
  variants (rotation, perspective, blur, glare, low resolution); gas in two layouts
  (per SCM, per MMBtu), water, telecom, a tax invoice (`other_invoice`), a receipt and a
  letter (`not_a_bill`). Output is byte-identical for a seed. Truth files hold normalised
  values and a `printed` map; fields a layout doesn't print are `null`. `account` is the
  KNO on AVVNL, the AC-No on PVVNL; `tariff.category` is the printed code until a mapping to
  the order's categories exists; PVVNL's bill month is the month after the reading period
  (exercises G18's offset). Line amounts are quantity × rate rounded half-up to 2 dp;
  MMBtu = SCM × GCV / 252,000 to 3 dp.

## Stage 0.6 and 0.7 (12 Oct 2026, second pass)

The Developer Guide (Part A, and Part C as `contract/esgos-1.0/contract.md`) and the change
list arrived and are saved byte for byte as supplied. Reading them against the build prompt
and the Stage 0 code gave these decisions; none changes code.

- **Change list numbering.** The saved list is a rebuild (its own note says so). Its item 6
  ("status is passed") matches the build prompt's 6.5 item 7, but its item 5 is unverified
  layouts, which 12.4 calls "esgOS change 4". The rebuild's numbers are used in the table
  above; if the original list arrives it replaces the file and the table's numbers are
  re-checked (pending-for-user).
- **`profile.status` values conflict between contract 1.0 and the build prompt.** Contract
  1.0 (5.2) puts `profile` on every bill with `status` `final`, `draft` or `none`. Build
  prompt 6.2 calls `profile` an addition "present in `esgos-1.1` and `full` modes" with
  `verified`, `draft` or `none`. Default until Joulewise and esgOS say otherwise: the build
  prompt keeps 1.0 "working unchanged" and a minor version may only add optional fields
  (contract 9), so `esgos-1.0` and `esgos-1.1` modes return `profile` on every bill with
  `final` where the build prompt says `verified`; `full` mode uses `verified`. Stage 2
  carries it; listed in pending-for-user.
- **Guaranteed-field paths.** `config/guaranteed_fields.yaml` stays `provisional-0` until
  Stage 1.1 replaces it with contract 1.0's section 6 list plus 6.4's additions. Its
  provisional paths map onto the contract's as: `utility` → `utility.name`; `account` →
  `consumer.account_number`; `period.start`, `period.end` → `period.from`, `period.to`;
  `demand.recorded`, `demand.contract` → `demand.max_kva`, `demand.contract_kva`; gas
  `customer_id` → `consumer.customer_id`. `bill_number` is not a contract field (it stays in
  the core schema's `period`). The contract adds fields the provisional list lacks:
  `meter.number`, `connection.tariff_category`, `period.bill_date`, `readings[]`,
  `energy.tod[]`, `energy.power_factor`, `net_metering.export_kwh` and `.import_kwh`,
  `charges.energy`, `charges.demand`, and for gas `meter.number`, `readings.previous` and
  `.current`. The 13.1 critical fields are read through the same map (`demand.recorded`
  is `demand.max_kva`, `demand.contract` is `demand.contract_kva`).
- **Studio confirmations before Stage 1.1** would record the provisional paths and miss the
  fields above, so each bill confirmed now needs a second pass for those fields after 1.1.
  Default: the studio keeps working as it is (no input waits, rule 11), and Stage 1.1 maps
  existing manifest entries through the table above and marks the added fields
  `unconfirmed` for a person to finish.
- **GG03's constant.** The guide divides by 2,51,995.76 kcal per MMBtu within 0.5%. The
  synthetic gas bills print and compute `SCM x GCV / 252000`, a convention real bills use;
  the two differ by 0.002%, well inside GG03's tolerance, so the synthetic bills stay as
  they are and Stage 2b implements GG03 with the guide's constant.
- **Where the guide and the build prompt differ, the build prompt wins** (the guide's own
  line 7): the second reader is Model B, not Tesseract (5.1); the studio is the build
  prompt's (0.5, 3.10); `full` mode's permanent storage and `DELETE` (6.2) apply outside
  the esgOS modes; `schema_version` reports 2.0 after Stage 1 (already in pending-for-user).

## Build prompt 5.0 (12 Oct 2026, from the team's instruction)

The team asked, before leaving for 24 hours, for every conflict to be resolved, a
first-level parser with no errors and with formulas, and an autonomous run. Version 5.0
(`docs/build-prompt.md`) is the rebuild; 4.2 is kept as `docs/build-prompt-4.2.md` and
nothing in it is cancelled. The conflicts and their settlements are its section 13 and
the defaults its section 12 (D1 to D12); they are not repeated here. The items below are
what this session decided beyond the prompt.

- **Remote.** `origin` is `https://gitlab.com/icac1/ocr-bill-extraction.git`. The remote's
  one commit (GitLab's generated README) is replaced by a force push of `main`, as the
  team's instruction spelled out (`git push -uf origin main`). The GitHub workflow is
  removed and `.gitlab-ci.yml` added (checks now; images in Stage 2).
- **`main` carries Stage 0.** The earlier rule (a person merges) is replaced by autonomous
  mode (D2), so `stage-0` is merged into `main` and pushed.
- **The four bills in `~/Documents/OCR Application/`** were copied, unread, to
  `~/billx-data/golden/unconfirmed/unsorted/`; the folder itself now holds a `billx` link
  to the repository. The repository stays at `~/billx` (the prompt's path and every tool's).
- **Local OCR in the project venv.** `paddlepaddle`, `paddleocr`, `rapidocr` and
  `onnxruntime` are installed into `.venv` (the `ocr` extra in `pyproject.toml`); the
  separate `.venv-ocr` stays only for `tools/mac/ocr_check.sh`.

## Stage 1 (12 Oct 2026)

- **`decide()` lives in `billx/core/proof.py`.** The build prompt names
  `billx/reader/validate/proof.py`; core cannot import the engines (section 9) and the core
  schema's validator must call the rule, so the implementation is in core and the named
  path re-exports it. The one-rule test allows exactly those two files to assign a
  verification (plus `schema.make_value`, which copies the decision into a Value).
- **Model B temperature.** The installed Anthropic SDK (1.13) has no `temperature`
  parameter and the configured model rejects non-default sampling; a spec listed under
  `temperature:` in `config/providers.yaml` is sent through `extra_body`, by default none
  is sent (invariant 6: "where the model accepts it"). The live one-token check confirms.
- **Budget before ceiling.** The caller's `max_cost_usd` is checked first (`BudgetExceeded`,
  usage `reason: budget`), then `max_cost_usd_per_call` (`ProviderError`, `reason: ceiling`);
  both write a `status: refused` usage record. The pipeline passes the *remaining* budget.
- **Model B's estimate counts four images per page** (the page and three bands) at
  `tokens_per_image`; with placeholder prices a one-page read is about $0.08 to $0.09, and
  `max_output_tokens` dominates.
- **Model readings carry no page or region.** The prompts don't ask for page numbers, so a
  model `RawRead` has `page: None`; X02 is a warning. Multi-page attribution is a new prompt
  version when a sample needs it.
- **Gas in Stage 1.** The pipeline reads gas bills from Stage 1 (the label rule, the GG
  checks) rather than refusing them with `gas_not_yet_supported`; Stage 2b's job is to make
  every synthetic gas bill pass. A gas bill that isn't fully verified is `needs_review`.
- **Line grouping on OCR words** compares a word with its nearest neighbour in x and allows
  a vertical skew of 0.015 of the page height per unit of horizontal distance (the synthetic
  scans drift about 0.009 across a row; rows are 0.018 apart). The union-of-extent rule
  drifted into the row beneath a label grid; a fixed tolerance split skewed rows.
- **Planted variants that trip more than one check.** The G15 variant (one slot's units
  changed, total unchanged) also trips G03 on that row; the G19 variant moves two strings
  (the dates swap). The declared check is what `billx eval` requires to fail; a second
  failing check is not an error.
- **Silent errors are measured on scalar guaranteed fields.** The synthetic truth files
  carry the arrays (`readings[]`, `energy.tod[]`, `charges.by_code[]`) as `tod` and
  `charges`, not on contract paths; array accuracy is added to the eval when a sample needs it.
- **Synthetic rates fixed** so the draft profiles can carry them as `params`: AVVNL energy
  7.30/kVAh and fixed 330.00/kVA, PVVNL demand 300.00/kVA and energy 7.10/kVAh; FPPCA stays
  random (notice-based). Every synthetic byte changed for a seed as a result; nothing else did.
- **Tests that run the local OCR engine** carry the `ocr` marker (`pyproject.toml`), run by
  default; deselect with `-m "not ocr"` for a quick pass.

## Stage 2 (14 Oct 2026)

- **A printed inconsistency counts as arithmetic coverage.** Condition 3 of 5.2 (the money
  and the energy take part in a passing equality check) is met also by an equality check
  that failed on fully verified inputs: the arithmetic ran and tied the values, the bill
  itself is wrong, and the bill is flagged `printed_inconsistency:<id>`. Otherwise a bill
  whose only check on the net payable is the one it breaks (the planted G09 case) could
  never pass with the flag, which is what 5.2 says it does.
- **1.1 `notes` carry no review reasons or flags**; those are fields. In 1.0 mode both go in
  `notes`, as 6.1a says.
- **Embedded store (F).** `BILLX_MAX_JOBS` below 4 is raised to 4 (the contract's "at least
  4"); `Retry-After` on a full queue is ceil((waiting + 1) × the median recent job time ÷
  max_jobs), at least 5 s, with 30 s assumed per job until there is history; retention
  runs from `submitted_at`; a worker that raises records the exception's class name only.
- **The image (G).** `paddlepaddle==3.3.1` comes from Paddle's own index
  (`--no-deps --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/`) before
  `pip install --editable '.[ocr]'`: PyPI has no linux/aarch64 wheel past 3.2.2. The install
  is editable at `/app` because `profiles/` and `config/` resolve relative to the package.
  `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` keeps a no-network container from probing the
  model hosts. The OCR engine runs a tiny predict at init and falls back to RapidOCR when it
  fails (linux/amd64 fails inside oneDNN at predict time); `BILLX_OCR_ENGINE` forces one.
- **Building on this Mac.** Container egress through Docker Desktop is throttled to tens of
  KB/s while the host does several MB/s; builds pass `--build-arg HTTP_PROXY=
  http://http.docker.internal:3128` (and HTTPS_PROXY), Docker Desktop's own proxy, which
  gives several MB/s. BuildKit does not bake the args into the image; CI needs none of it.
  A wedged daemon (500 on every call after a large `--load`) was cleared by restarting
  Docker Desktop's processes (`docs/runbook.md`).
- **The image runs two jobs at once by default** (`BILLX_MAX_JOBS=2` in the image and in
  `docker/compose.yaml`). Measured on linux/arm64 with four digital bills submitted at once:
  four workers peak at 2061 MiB, two workers at 1850 MiB, and both finish the four bills in
  about 100 s, because OCR is serialised inside one container (one page at a time; the
  engine is CPU-bound and not thread-safe). Four jobs are still accepted at once and queued
  (contract 1.0 section 9); `BILLX_MAX_JOBS=4` restores four workers where memory allows.

## Live readers (15 Oct 2026, the first reads with real keys)

The first live read of a synthetic AVVNL scan passed with two silent errors and two false
printed inconsistencies, each fixed the same day:

- **Profile `prompt_hints` reach the models** (prompt files `read_bill_v2`, `read_fields_v2`,
  a `{{HINTS}}` slot; v1 untouched). Both models took AVVNL's "A/c No" (an office code) for
  the consumer's account number and agreed, so it was `verified` and wrong: the shared
  misreading 5.2 warns about, here a semantic one the profile resolves ("the account number
  is the KNO"). Hints say where a field is printed or which identifier is meant; never a value.
- **`utility.name` is the whole printed line** from every reader (the models transcribe the
  full name; the local rule gave the bracketed short code, so they never agreed). The eval
  compares `utility.name` by containment.
- **A merged array key takes the spelling most readers gave; a tie is settled by how often
  each spelling occurs across all rows** (OCR's "MOMING PEAK" on the kVAh row lost to
  "MORNING PEAK", which both readers gave on the kWh row). The TOD-surcharge rule then sums
  both peak slots.
- **G06 compares a group's items with its one subtotal, stage for stage,** and skips a group
  that prints several subtotals (Model A groups a whole billing table, including "Current
  Charges", "Arrears" and "Net Payable", under one heading); G07 to G09 own those totals.
- Cost of one synthetic scan with both models: about $0.09 at the placeholder prices
  (`config/prices.yaml` still says `placeholder: true`); 40 to 50 s end to end.

## Reading a real scan (16 Oct 2026, the team's PVVNL bill "Site Electricity Apr-25")

The studio showed almost no pre-fill for a real PVVNL scan even with both keys in place.
The causes, all fixed on branch `fix-real-scan-reading`:

- **The studio kept a stale reading.** It cached its first reading (made while the OpenAI
  key was still rejected) and never read the bill again. A cached pre-fill now carries a
  fingerprint (engine and prompt versions, model and profile configuration, which keys are
  present, cloud allowed or not) and is read again when it no longer matches; each bill
  page has a "Re-read with the engine" link.
- **Model A never returned a usable answer.** Its answer was cut at 4,000 output tokens,
  then (at 16,000) timed out at 120 s. Timeout now 300 s.
- **Model B was asked only for fields local OCR had already found.** A field no reader had
  found counted as settled. It no longer does: Model B reads every field not yet verified.
- **OCR-only rows entered the arithmetic.** When Model A has read a table, its rows are the
  bill's rows and another reader's rows only confirm them (5.3).
- **Unverified values took the first reader's reading in the transcription.** The checks
  now run on Model A's reading wherever a value is not verified (5.2, condition 4), never
  changing a field's own value or verdict.
- **Bills print a summary table and a details table for the same charges.** Prompt
  `read_bill_v3` asks the model to mark a line that itemises or repeats another printed line
  (`detail_of`, kind `info`); such lines stay out of the current-charges sum, and the new
  equality check **G21** verifies that they add up to the line they detail. A label that
  prints its own minus ("(-)") subtracts in every sum. "0.00" printed in an empty units or
  rate column is a placeholder, not a quantity x rate (G05). A rebate that applies only if
  paid by a date is `info`. Prompts `read_bill_v3` and `read_fields_v3` ask for the English
  form where a value is printed in two scripts.
- **Smaller:** dates printed with a time ("12-MAR-2025 16:33") normalise; a negative arrear
  or adjustment passes G20; bilingual labels ("हिंदी / English") match on the English part;
  "Account No." with a period matches; PVVNL is recognised when a scan cuts "PAS" from its
  name, and the discom is identified again from the models' verified name; PVVNL's version
  carries hints for this real layout (account number, reading period from the meter table,
  bill month from the six-month history, kVAh as Net Billed Unit, payable vs payable by due
  date) and `bill_month_offset` [0, 1].

## Proof rule 2 and field meanings (23 Oct 2026, after the team confirmed 31 real bills)

Comparing the studio's pre-fill with the 31 confirmed bills showed **verified values that
were labels**: on digital HPSEBL, MSEDCL and PVVNL bills the text layer and local OCR both
took a neighbouring label as the value ("CONNECTED LOAD(KW)" as the tariff, "OA TYPE" as the
tariff, "ADDRESS" as the consumer name, "STANDARDSUPPLYVOLTAGE(KV)11.00" as the account
number, the wrong kVAh and net payable) and their agreement counted as consensus.

- **Proof rule 2:** two local readers never verify each other; they find a field by the same
  label rule. A value is verified only by a local reader and a model agreeing, or two model
  families agreeing. Every bill now needs a model reading until layouts have anchors. A
  refused bill still carries every field as read and every check run on it.
- **Field meanings:** every guaranteed field has a `description` (config/guaranteed_fields.yaml)
  that prompts `read_bill_v4` and `read_fields_v4` give the models. The open-access fields
  were read on none of the three open-access bills because a model only saw
  "open_access.re_kwh: number, kWh"; the description now says what the field is and how
  MSEDCL and PVVNL print it ("Units Offset Against Current Month Generation", "Final
  Adjustable Adjusted Units").
- **The label rule** rejects an identifier that is not at least half digits and a text value
  that ends in a colon, carries a bracketed unit or is a heading word.
- **Max demand** is the recorded demand in kVA after the multiplying factor: the team's
  confirmed value on a PVVNL bill is its raw recorded demand times the M.F. Said in the
  field's description and in PVVNL's hints.
- **Two bills removed from the studio** at the team's request: "Site Electricity Bill-May-26
  & June-26.pdf" (PVVNL) and "12. Electricity bill March-25 (unit-1 & unit-2).pdf" (AVVNL, an
  empty file). Their copies moved to `~/billx-data/golden/excluded/`.
- **Contract examples under rule 2:** a passed bill now always has route `cloud_model`, so
  `route-template-passed[-pvvnl]` became `route-cloud-model-passed[-pvvnl]`. These and
  `printed-inconsistency` replay a correct model from the synthetic truth file
  (`ReplayModel`, `"models": "replay"` in `request.json`); no example calls a real model.
  The new `digital-without-a-model` shows a digital bill refused without one, still carrying
  its reading and checks.

## Open-access units on PVVNL adjustment bills (26 Oct 2026)

The team found `open_access.re_kwh` empty on every PVVNL "Open Access Adjustment Bill". Asked
for the three open-access fields alone, Model B read the 'Final Adjustable Units' total; asked
for all 27 fields it gave null: the bill never says its open-access units are renewable and
prints them in kVAh. The field's meaning now says that open-access units set off without a
named source belong in it, given as printed in kWh or kVAh, and PVVNL's hints name the
column. Following the team's own confirmation of an earlier PVVNL adjustment bill. The
figure is printed in kVAh while the field's unit is kWh: open with the team.
- **Stored as printed, in kVAh** (the team's decision, 26 Oct 2026): a profile version's
  `printed_units` names fields a layout prints in another unit than the field list's, with a
  regex on the bill's text. On a matching bill the value keeps the printed figure, never
  converted, and its `unit` says kVAh, in the API response and in the studio. PVVNL's open-access
  adjustment and settlement bills use it for the three open-access fields.

## Consumption, open access and grid units (26 Oct 2026, the team's definition)

The team set out how an open-access bill reads (a PVVNL adjustment bill): the month's total
consumption (the 'MONTHLY CONSUMPTION' total for the consumption month), the open-access units
set off (the 'Final Adjustable Units' total) and the units the grid supplied, which the discom
bills (the 'BILLABLE CONSUMPTION AT DISTRIBUTION LICENSEE' total); the first less the second
is the third.

- `energy.kwh` and `energy.kvah` are the **total consumption before any set-off**. On a bill
  without open access that is the billed energy, so nothing changes there; on an
  open-access bill it is the month's whole consumption, which BRSR reports, with the
  open-access share in `open_access.*`.
- **`energy.billed_units`** (new, optional, contract 1.1): the units the discom bills, as
  printed, with the unit on the field (kVAh by default; a profile's `printed_units` says
  otherwise).
- **Check G22** (fail): total consumption - open-access units = billed units, within 1 unit,
  comparing figures only when they are printed in the same unit. A one-digit misread in any
  of the three fails it (the scan of one adjustment bill misread one digit of the billed units).
- The field map now carries the open-access, green-tariff and net-metering fields into the
  transcription, which it did not before, so checks can use them.
- The team's earlier confirmations of MSEDCL open-access bills may hold the net (billed)
  kVAh in `energy.kvah`: to be rechecked by the team under this definition.

## Release 0.2 (27 Oct 2026)

48 bills confirmed; one more bill ("Annexure 2- Discom Settlement Bill.pdf", PVVNL) removed
from the studio unreviewed at the team's request, its copy in `~/billx-data/golden/excluded/`.
ENGINE_VERSION 0.2.0 (the OpenAPI document now carries it). Measured on the 18 bills read by
this engine before confirmation: docs/release-notes/0.2.md. Open: which printed amount is the
net payable on PVVNL open-access bills (pending item 20).

## Net payable is the amount after the due-date rebate (27 Oct 2026, the team's answer)

Pending item 20 asked which printed amount is the net payable where a bill prints both the
amount payable and the amount payable by the due date (less a due-date rebate). The team:
**after the rebate**, on every bill.

- `totals.net_payable` is the amount payable when the bill is paid by the due date, after
  any due-date (prompt payment) rebate: on PVVNL monthly bills 'Payable by Due date', on
  PVVNL open-access adjustment bills 'Amount Payable before Due Date (Rebate@1%)'. On a bill
  without such a rebate it is the amount payable, as before; never the amount after the
  due date. The PVVNL hint that said the opposite is replaced.
- **`totals.due_date_rebate`** (new, optional, contract 1.1): the rebate the net payable
  deducts, as a positive amount; on PVVNL monthly bills the 'Due Date Rebate (₹)'.
- **Check G09** is now current charges + arrears + adjustments - due-date rebate = net
  payable (₹1). Without the rebate field it is checked as before, so a bill whose rebate is
  not read and whose net payable is after the rebate fails G09 and goes to review rather
  than passing on a wrong figure.
- Six PVVNL monthly bills were confirmed under the old hint with the amount before the
  rebate. The team confirmed the rule for them in chat (27 Oct), and the manifest records a
  correction for each: the printed 'Payable by Due date' and 'Due Date Rebate (₹)', each
  pair checked against 'Payable Amount' within ₹1. The superseded entries stay readable.

## Readers upgrade: page sorting, slot-wise open-access units (1 Nov 2026, Joulewise via ergPLAN)

The team asked (1 Nov 2026, from the ergPLAN build) to make bill reading as exact as it can be,
using Docling and LlamaParse as readers that count towards verification (not only as the
comparison lab of 4.2 section 9B), with a live reading view. Work happens on the branch
`readers-docling-llamaparse`; `main` is untouched until the team merges it.

- **Page sorting (5.0), implemented.** A file holding several bills (a PVVNL open-access
  adjustment bill scanned with the month before it) was read as one bill: the model mixed the
  two months' tables and every check failed. `billx/reader/identify/split.py` groups pages
  by `Page k of n`, the printed bill number (one character of OCR noise tolerated) and the
  printed bill date, from local text only; a file without these signals stays one bill. Each
  bill is read on its own pages, and the model budget is the file's (what one bill spent
  counts for the next).
- **Slot-wise open-access and net units.** Meter rows gain `open_access` and `net` (the
  core schema's `open_access_units` and `net_units`), so G04 (consumption - open access =
  net) runs per slot. Model A's prompt `read_bill_v5` asks for one row per register and slot
  of the bill's own consumption month, merged across the slot-reading, consumption and
  open-access tables, with the slot label as printed including its hours. Contract 1.1 adds,
  as optional fields, each reading's `consumption`, `open_access` and `net`, and each
  `energy.tod[]` slot's `kvah`, `open_access` and `net`; a bill priced in kVAh now lists its
  slots in `energy.tod[]` (1.0 is unchanged).
- **The `docling` reader (proof rule 3).** Docling runs as a docling-serve container
  (`quay.io/docling-project/docling-serve-cpu`, pinned in `docker/compose.yaml`, profile
  `readers`) rather than inside the engine image: its models are several gigabytes and the
  engine image stays as it is. Its OCR on a scan is RapidOCR and its tables come from
  TableFormer (accurate mode). It finds a value by its table cell, so it does not share the
  label rule's neighbouring-label mistake; but its characters can come from the same OCR
  family as `local_ocr`, so it is a local reader (method `layout`, added to the local
  methods) and verifies only with a model reader. `PROOF_RULE_VERSION` is 3. On the first
  real PVVNL open-access file it read every slot's consumption, open-access and billable
  units of both bills, which the label rule cannot reach.
- **Labels.** `Tariff Type` joins the tariff category labels and `Sanctioned Load (KVA)` the
  contract demand labels in `profiles/_common.yaml` (the PVVNL open-access layout prints both
  in its connection table; a sanctioned load printed in kW does not match).
- **The `llamaparse` reader (family `llamaindex`).** LlamaExtract v2 (agentic tier) reads
  the bill's pages with the same schema and transcription rules as Model A and finds every
  value by its meaning, so it is a model reader. Its family is `llamaindex`: it verifies with
  a local reader or with Model A (OpenAI), never alone. LlamaIndex does not say which model
  its agentic tier runs, so the chance that it shares a mistake with Model A is not known; it
  is measured on the confirmed bills like every other reader, and a person can always see
  which readers agreed. It runs beside Model A (not after it) so a bill waits for one model
  call, not two; the budget reserves Model A's worst case first. Credits are priced at a
  placeholder rate in `config/providers.yaml` until the team confirms the plan's price.
  Without Model B's key (ergPLAN's server has none), LlamaParse is the second model family
  that lets a scan pass.
- **Every reader's reading in contract 1.1.** A 1.1 field object gains `readings[]`
  (optional): each reader's printed text, normalised value, page and box. A person reviewing a
  disputed value sees what each reader read and where, beside the page (4.2 section 9D.1's
  review screen), and a live reading view can replay the readers honestly.
- **First live run on the PVVNL open-access file (ergPLAN's server, 1 Nov 2026).** With local
  OCR, Docling and Model A (LlamaParse's key was refused by LlamaIndex, 401, in both regions):
  the file was split into its two bills, and every slot's consumption, open-access and billed
  units of both bills, the tariff category, maximum and contract demand, current charges,
  rebate and net payable were verified (Docling and Model A agreeing); G04 and G15 hold.
  Still disputed: the power factor where both local readers lost the decimal point, the
  consumer name and DISCOM name as printed, one due date. G08, G09 and G21 fail on this
  layout's "Other Adjustment (FPPA Surcharges+Arrears)" and "Total Arrear" lines: a profile
  matter for the team (measured on the golden set before any rule changes). Docling now also
  gives the register totals (energy and billed units from the "Total" rows) and keeps each
  slot's own cell box; `Account ID` joins the account-number labels.
- **Column layouts (AVVNL's digital bill, 1 Nov 2026).** Docling returns some bills as one
  large grid where headings stand over their values. Docling now: reads a typed value under
  a heading that ends a joined cell ("Reading Date Bill Issue Date" over a date) and a month
  printed first in a joined cell ("202601 NAME"); takes no row pair from a row of headings
  (two or more labels and no figure) or from a month-by-month history row (three values of
  one type after the label); reads register rows (KWH, KVAH, KVA) by the reading headings of
  the nearest row above them, so a meter table inside a larger grid is found; and takes a
  register printed once with no slots as its own total (a kVA register's consumption is the
  recorded demand). The label rule no longer takes the rest of a longer label ("& Address.")
  or a row starting with a date as a name, and "Name & Address" is one label. The month
  normaliser accepts `YYYYMM` (years 2000 to 2099, months 01 to 12) because AVVNL prints the
  billing month that way and Model A transcribes it as printed.
- **A reading its field cannot carry is no reading (1 Nov 2026).** The first ten real bills read
  on ergPLAN's server (AVVNL, PSPCL, MSEDCL, TNPDCL, MVVNL, GESCOM, HPSEBL layouts) showed the
  label rule and Docling returning neighbours as values: a month as an account number, a
  "label : value" pair or a bracket fragment as a tariff category, a charge as the power
  factor. `label.sane()` now drops such a reading in both readers (an identifier that is a
  date or month; words around one number keep the number, around two keep nothing; a text
  value with an inner "label : value" or an unclosed bracket; a power factor above 100). The
  consensus rule is unchanged: these readings were already disputed, never verified, but a
  disputed field sends the bill to a person where a missing local reading lets Model A's
  value wait for a second reader.
- **The label rule's typed values sit next to their label (1 Nov 2026).** On DVVNL and MVVNL
  bills that number their labels ("Power Factor 8 :", "Minimum Payable Amount 10"), the label
  rule took the footnote number as the power factor and the net payable, because a number,
  date or month was taken from anywhere right of its label. Now the value must be the first
  word after the label (a colon, a currency mark or leaders aside), a one- or two-digit
  number before the label's colon is a footnote marker, and otherwise the value is looked for
  below the label. A power factor reading must be a ratio (0 to 1) or a percentage (40 to
  100). New common labels from the scans of a manual MVVNL bill and a GESCOM bill:
  "DUEDATE" and "DUEDATEAMOUNTRS." as printed glued, "Payable before Due Date Amount Rs.",
  "Prompt Payment Rebate Amount", and "for the Month of" with a two-word month ("May 2025").
- **A label heading a row of figures has no single value (1 Nov 2026).** On an HPSEBL bill,
  "Total kWh Energy" heads a meter row (new, old, difference, multiplier, consumption) and
  "Total Amount Payable" a row of column totals; the label rule took the first figure (the
  new reading, the first column) as the field. A number, date or month label followed by
  four or more figures on its line now gives no value; the meter-row rules read such rows.
  The value may also follow the formula that names it ("Current Bill Amount (Rs.) A + B+ C
  - G 1,823,331.00", PSPCL): single letters and operators between label and value are
  passed over.
- **UPPCL meter tables and rate annotations (2 Nov 2026).** The DVVNL, MVVNL and PVVNL bills
  print the meter table with "Previous" and "Current" over "Date" and "/Read" columns, the
  register and its slot in one cell ("KVAH TOD-1 05-11"), and the consumption with its unit
  ("KVAH 500", "750 KWH"). Docling's register rows now read two heading rows together,
  never take a date column as a reading, take the slot from the register's cell, read
  "Meter Units" as consumption, and read a figure printed with its unit. The label rule
  passes over a rate annotation between label and value ("Due date rebate @1% 990.00").
  New common labels from an MSEDCL bill: "Highest Recorded Demand" (recorded demand) and
  "KVAH Units" (kVAh).
- **Contract demand from a sanctioned load, and billed units (2 Nov 2026).** UPPCL bills
  print the contract demand as "Sanction Load : 600 kVA". A sanctioned or sanction load is
  now read as the contract demand only when the figure is printed in kVA (a load in kW or HP
  is not a demand in kVA), in the label rule and in Docling's pairs. `energy.billed_units`
  gains labels of its own ("Net Billed Units", "Billed Units", "Units Billed", "Total Billed
  Units", "Units billed by <DISCOM>"); column headings such as "Billable Consumption" are
  left to the table readers, which take the total row. A label inside a sentence
  ("Net Billed Units are the units used for ...", a DVVNL footnote) takes no figure from
  below: a lower-case word right after the label marks prose.

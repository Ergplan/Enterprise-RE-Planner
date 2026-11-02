# billx architecture

The folder layout is section 10.4 of `docs/build-prompt.md`. This file records what each
folder holds once it holds code.

## billx/core

- `settings.py`: where configuration comes from (rule 12). The config folder (`config/`, or
  `BILLX_CONFIG_DIR`), the data folder (`BILLX_DATA_DIR`, default `~/billx-data`), and
  settings read from the environment first, then the git-ignored env file
  (`BILLX_ENV_FILE`, default `~/billx/.env`). It lives in core so the engines and the
  platform can share it without crossing the import boundary.

## billx/core (schema 2.0)

- `normalize.py`: the normalisation of 5.1, one function per field type; a string that cannot
  be read as its type gives None, which never matches anything.
- `proof.py`: `decide()`, the verification rule of 5.2 (`PROOF_RULE_VERSION`). It lives in
  core because the schema's validator calls it; `billx/reader/validate/proof.py` re-exports it.
- `schema.py`: the strict Decimal models. `Value` is built only through `make_value`, and its
  validator recomputes verification, value, proof, readers and source from the readings and
  rejects a mismatch. `Bill` is the transcription; `BillResult` and `Envelope` are what the API
  modes render from.

## billx/reader (the pipeline)

- `pipeline.py`: `read_file(path, allow_cloud_model, max_cost_usd, model_a, model_b, contract)`
  → `Envelope`. Ingest, the gate, discom and version, readers, consensus, the transcription
  (`normalize/fields.py`), checks with `unverified_inputs` filled from the Values, arithmetic
  added to the Values the passing equality checks prove, elements with the formula recheck,
  the pass rule. Every caller (CLI, API, studio, eval) goes through it.
- `identify/gate.py`: the document-type gate on local signals (`document_signals` in
  `profiles/_common.yaml`); a page below the floor is `type_unclear`.
- `identify/split.py`: page sorting (5.0): a file's pages grouped into bills by `Page k of
  n`, the printed bill number and the printed bill date; `read_file` reads each group as its
  own bill (`bills[i].index`, `bills[i].pages`), the model budget shared by the file.
- `read/docling.py`: the `docling` reader (method `layout`, local). docling-serve
  (`BILLX_DOCLING_URL`) converts the whole file once, in the background while local OCR and the model readers run (a bill joins the conversion after its model readings, `_layout_reading`);
  each bill reads its own pages from the conversion (`Document.docling`): fields by the label
  rule over Docling's words plus label-value pairs in table rows, meter rows from slot tables
  (consumption, open access, net by column heading) and slot-wise reading tables (present and
  past by read date), lines from amount columns and label-amount pairs. Every reading carries
  its page and cell box. It verifies only with a model reader (proof rule 3).
- `read/consensus.py`: `ReaderOutput` (what every reader produces: fields, meter rows, lines as
  raw strings), `consensus_fields` and the array matching of 5.1.
- `validate/passrule.py`: `verdict()`, the five conditions of 5.2 and the printed-inconsistency
  rule, from Values and CheckResults; it reads verifications and never sets one.
- `normalize/fields.py`: the field map (contract paths ↔ schema paths), the required-field
  lists, and `bill_from_values` (the transcription from the decided Values).

## billx/reader/ocr (cache and threads)

`read_words` caches each page's words by the SHA-256 of its PNG bytes, the cache version and
the engine name (`cache_dir()`), and builds the engine with `cpu_threads` from
`BILLX_OCR_THREADS`. The cache holds OCR words only, never a decided value.

## billx/reader/providers

- `llamaparse_reader.py`: the `llamaparse` reader (family `llamaindex`, method `vision`):
  LlamaExtract v2 with a JSON schema of the guaranteed fields, meter rows and printed lines
  (all strings as printed) and `llamaparse_extract_v1` as its system prompt. Only the bill's
  own pages leave the machine, as one PDF. Citations give a field's page and box. The
  pipeline (`_start_third_reader`) starts it on a thread beside Model A with the budget left
  after Model A's worst case; Model B then reads what is still unsettled after both.
  `make_model_c()` builds it from `LLAMA_CLOUD_API_KEY`; the API, `billx extract` and
  `billx eval` pass it as `model_c`.

The only code that imports a model SDK (rule 9; a test enforces it).

- `base.py`: `Page`; `ModelReading`, what both model readers return (guaranteed fields as
  printed strings by contract path, meter rows and printed lines as dicts of strings or
  None, `extraction_notes`, the call's `UsageRecord`) with `to_output()` producing the
  `ReaderOutput` of `RawRead`s that `billx/reader/read/consensus.py` consumes (reader
  `model_a`/`model_b`, method `vision`, family, model id, prompt version); `BaseReader`,
  the one call path both readers share: the worst-case cost estimate (prompt tokens, every
  image, the full output allowance, at `config/prices.yaml`) compared with the caller's
  remaining `max_cost_usd` (`BudgetExceeded`, 5.3 step 7) and with `max_cost_usd_per_call`
  (`ProviderError`) before any request, bounded retries (429: wait
  `rate_limit_wait_seconds`, then back off; 5xx, overload and connection errors: the short
  wait), and one usage record after every call, refused ones included. `ProviderError`
  carries ids and error classes only, plus the call's `UsageRecord` so a failed or refused
  call is still accounted for. The JSON parsing keeps a model's numbers as the literal text
  it wrote (`parse_int=str`, `parse_float=str`): never a float. The prompt renderer fills
  `{{BILL_KIND}}`, `{{FIELDS}}` (path, type, unit only) and `{{LINES}}` (heading and
  label only). Factories `make_model_a()` / `make_model_b()` build a reader from
  `BILLX_MODEL_A` / `BILLX_MODEL_B` (else `config/providers.yaml`) and the keys
  `BILLX_OPENAI_API_KEY` / `BILLX_ANTHROPIC_API_KEY`, and return `None` when the key is
  missing or the spec is not that family; `make_prefill_provider` is Model A for the
  studio. Each reader has `family` (`openai`/`anthropic`) and `reader_name`
  (`model_a`/`model_b`).
- `openai_reader.py`: Model A over the OpenAI Responses API (JSON-object output,
  `max_retries=0` so the 429 wait is ours). `prefill()` is the studio's pre-fill (Stage 0,
  prompt `prefill_v1`, bounded by the per-call ceiling only); `read_bill(pages,
  bill_kind=, fields=, bill_id=, max_cost_usd=)` is 5.3 step 3: the whole bill into
  `ModelReading` (fields, meter rows, every printed line with an amount with its group,
  kind `item|subtotal|info` and stage `current|arrear|adjustment`, extraction notes),
  prompt `read_bill_v1`.
- `anthropic_reader.py`: Model B over the Anthropic Messages API with image blocks
  (`max_retries=0`). `read_fields(pages, bill_kind=, fields=, bill_id=, max_cost_usd=)`
  (5.3 step 5) sends, per page, the whole page then its top, middle and bottom bands, and
  reads the guaranteed fields only, prompt `read_fields_v1`; `read_lines(pages, lines=,
  bill_id=, max_cost_usd=)` (5.3 step 6) asks for the quantity, rate, unit and amount of
  named printed lines, prompt `read_lines_v1`. Model B is never shown another reader's
  value: of a line dict only `group` and `label` reach the prompt, of a field dict only
  path, type and unit (a test plants a value and asserts it is in no request). The
  anthropic 1.x SDK has no `temperature` parameter; a model id listed under `temperature`
  in `config/providers.yaml` gets it through `extra_body`, one not listed is called
  without (invariant 6).
- `images.py`: Pillow only. `downscale` resizes a page whose longest side is above
  `max_image_edge_px` (both readers, before encoding); `bands` cuts the three horizontal
  thirds, each extended by half of `BAND_OVERLAP` (15 % of a band's height) into its
  neighbours so a line cut by one band's edge is whole in the next. A band is a crop of
  the page, never a region another reader found.
- `usage.py`: Decimal cost from `config/prices.yaml` and the JSONL usage record (ids,
  model, prompt version, purpose, page and image counts, tokens, costs, timing, status
  `ok|refused|failed|unparseable`; never a value).
- `ping.py`: one one-token call per configured model id for `tools/mac/doctor.sh`.
- Settings: `config/providers.yaml` (model ids, timeout, retries, ceiling,
  `max_image_edge_px`, per-model temperature), `config/prices.yaml` (placeholder prices for
  both configured models, marked). Prompts: `billx/reader/prompts/<name>_v<n>.md`
  (`prefill_v1`, `read_bill_v1`, `read_fields_v1`, `read_lines_v1`), never edited in
  place; every prompt says: transcribe only, every value as printed, never calculate, null
  when not printed, every value a JSON string.
- Tests mock the SDKs' HTTP layer (both are built on `httpx2`) with a transport that
  raises on any request beyond the scripted ones; no test reaches the network.

## billx/platform/studio

The confirmation studio (Stage 0.5): FastAPI serving plain HTML on 127.0.0.1 only.

- `workspace.py`: a workspace is `<BILLX_DATA_DIR>/workspaces/<name>/` holding
  `workspace.json` (source folders, bills by sha256 and path; files are never copied),
  rendered page images (pypdfium2), cached pre-fills and `usage.jsonl`.
- `app.py`: the pages. The person names themself once per session and chooses whether
  the cloud model may be used; each bill shows its page images beside the guaranteed
  fields of `config/guaranteed_fields.yaml` (electricity or gas), pre-filled by Model A.
  Each field is confirmed (one click), typed as printed, or marked `not_printed`.
- `golden.py`: the append-only golden manifest `<BILLX_DATA_DIR>/golden/manifest.jsonl`
  (one entry per save; a later entry for the same sha256 supersedes) and the seeded
  tuning / held-out split, recorded as `tuning` until Stage 11 (`config/studio.yaml`).
- `cli.py`: `billx studio --workspace <name> --port <port>`.

## billx/platform/store

The embedded store behind the API (Stage 2.2): what `POST /v1/jobs` writes, the workers
read and `DELETE` and the sweeper remove, all under `BILLX_DATA_DIR` (the image mounts
`/data`). The API package (`billx/platform/api`) is written against these interfaces and
holds no state of its own, so jobs survive a restart.

- `jobs.py`: `JobStore(root, *, clock)` over `<root>/jobs.sqlite` (stdlib `sqlite3`, WAL,
  one lock and one connection per call, so request threads, workers and the sweeper share
  it). A row per job: `job_id` (a UUID v7, time-ordered), `request_id`, `product`,
  `sha256`, `media_type`, `size`, `kind`, the validated `options` as JSON (never logged),
  `status` (`queued`, `reading`, `done`, `failed`), `submitted_at`/`started_at`/
  `finished_at` as `2026-10-07T10:15:02Z`, `error_code`, `error_message` (an identifier
  such as an exception class name, never a value), `result_path`, `attempts`. `create`
  runs its request_id check and insert in one `BEGIN IMMEDIATE` transaction: the same
  request_id with the same sha256 returns the existing job (`created=False`); with a
  different sha256 it raises `RequestIdConflict` (the API's 409). `requeue_stale` puts
  every `queued` or `reading` job back to `queued` on start. Nothing stored is a float: a
  `Decimal` in the options is kept as its string, and a float is refused (`_json.py`).
- `files.py`: `FileStore(root)` keeps `<root>/jobs/<job_id>/` with `input<suffix>` (the
  upload), `result.json` (the rendered result) and `feedback.jsonl` (one line per
  correction). A job_id must match `[0-9a-f-]{1,64}` and resolve under `<root>/jobs/`
  (a symlink out is refused), so nothing outside the jobs folder is ever touched;
  `delete` removes the whole folder at once (contract 4.4).
- `queue.py`: `Queue(store, process, *, max_jobs, queue_limit)`: `max_jobs` daemon worker
  threads (`BILLX_MAX_JOBS`, at least 4) take jobs in submission order. `submit` raises
  `QueueFull` once `queue_limit` jobs are waiting (`BILLX_QUEUE_LIMIT`); its
  `retry_after_seconds` is (waiting + 1) x the median recent job time / workers, in
  integer seconds, at least 5 (the API's 429 `Retry-After`). A worker marks the job
  `reading`, calls `process(job)` (the API's function: run the pipeline, write the result
  through the `FileStore`, mark done) and on any exception marks it `failed` with the
  exception's class name only, logging the job id and the class (invariant 9): a message
  could carry a value. `recover()` resubmits what `requeue_stale` returns, past the limit.
- `sweeper.py`: `Sweeper(store, files, *, retention_hours=24, interval_seconds=600)`: a
  daemon thread deleting every job (row and folder) submitted more than the retention
  ago, and any folder with no row once it is that old; `run_once()` returns the count, and
  the log carries counts only. `BILLX_RETENTION_HOURS` sets the retention.
- `__init__.py`: `Settings.from_env()` (`BILLX_DATA_DIR`, `BILLX_MAX_JOBS`,
  `BILLX_QUEUE_LIMIT`, `BILLX_RETENTION_HOURS`) through `billx.core.settings.setting`
  (rule 12). Tests: `tests/unit/test_store.py`, `tests/unit/test_queue.py`.

## billx/platform/synth

`billx synth --out DIR --seed N [--no-planted]` (Stage 0.4, planted misreads from Stage 1)
writes synthetic documents with known values, the same bytes for the same seed.

- `values.py` builds every value as a `Decimal` from its parts (TOD slots into registers,
  quantity x rate into lines, lines into current charges, plus arrears into net payable)
  together with the string each layout prints. The energy and demand rates are fixed
  (`AVVNL_RATES`: 7.30 per kVAh, 330.00 per kVA; `PVVNL_RATES`: 300.00 per kVA, 7.10 per
  kVAh) so the draft profiles of the synthetic layouts carry the same numbers as `params`
  and T01 to T05 run end to end; FPPCA stays random because it is notice-based.
- `electricity.py` renders two HT layouts that imitate the structure of AVVNL and PVVNL
  bills; `documents.py` renders gas (two layouts), water, telecom, tax-invoice, receipt
  and letter documents for the document-type gate. The renderers read the `printed`
  strings of the bill dict, never the values.
- `degrade.py` turns a digital PDF into an image-only scan PDF and photo-like JPEGs
  (rotation, perspective, blur, glare, lowres).
- `planted.py`: **planted misreads** (build prompt sections 2, 5.4, 10). From each clean
  electricity and gas bill, one variant per check, rendered from a deep copy of the bill
  dict with ONE printed string changed by one digit where the check can catch it:
  G02 (a TOD row's present reading, leading digit), G03 (a slot's consumption, leading
  digit), G05 (a charge line's amount), G07 (current charges), G09 (net payable), G15 (a
  kVAh slot's consumption while the total register stays), G16 (the kVAh total printed
  below the kWh total), G18 (the bill month three months after the period), G19 (the
  reading dates swapped), G20 (electricity duty printed negative); gas GG02 (present
  reading), GG03 (MMBtu by about 1%), GG04 (the gas charge amount), GG05 (the total).
  The file is `<base>.planted-<check>.pdf`; its truth keeps the clean bill's values and
  adds `planted: {path, check, original_printed, planted_printed, kind:
  printed_inconsistency}` (`swapped_with` for G19); the manifest entry has `planted:
  true` and `check`. The same module writes the **reader-misread fixtures**
  `<base>.misreads.json` for every clean electricity bill: one plausible misread per
  printed scalar guaranteed field (a digit changed, an inner digit group dropped, or an
  OCR-confusable character) whose normalised value differs from the truth, so the
  evaluation can simulate a reader disagreement without rendering.
- `cli.py` writes the files, the truth sidecars (`<stem>.truth.json`: document type,
  layout, input kind, variant, the guaranteed-field values from
  `config/guaranteed_fields.yaml` as strings, every printed line and TOD slot) and
  `manifest.json` with sha256 per file. All names and numbers are invented; nothing is
  read from a real bill.

## billx/platform/evals

`billx eval --synthetic DIR | --golden [--allow-cloud-model] [--max-cost-usd N] [--report
PATH]` (build prompt section 8) runs the engine over a set with truth and reports per
layout x input kind x route, always with n.

- `manifest.py`: one `EvalCase` per file (path, expected document type, layout, input
  kind, the truth on the contract's field paths, the planted record) from a `billx synth`
  manifest, or from the golden manifest (the latest entry per sha256; cases are named by
  a sha256 prefix, never by file name; `not_printed` becomes None). Truth files are read
  with floats refused.
- `metrics.py`: silent errors (a field `verified` on a passed bill whose normalised value,
  through `billx.core.normalize.normalise` with the type from
  `config/guaranteed_fields.yaml`, differs from the truth) with the rule-of-three bound
  3/n over passed bills when none is seen; coverage (passed / bills); correct refusals
  (non-bills refused) and false refusals (bills refused as `not_a_bill`, `unreadable`,
  `wrong_document_type`, read as no bill, or classed as another type); non-bills read as
  bills; bills declined as `model_not_allowed` or `budget_exceeded` (the caller's choice,
  neither passed nor refused); accuracy over attempted per field on passed bills; formula
  coverage (elements whose recheck is `match` or `differs`); planted misreads caught (the
  declared check reports `fail`) or missed, taking part in no other metric; cost and
  seconds per bill, median and nearest-rank p95, all Decimal.
- `runner.py`: `run(cases, read_file, *, allow_cloud_model, max_cost_usd)` sequentially
  with timing; `evaluate_synthetic(folder, read_file, ...)`, `evaluate_golden(read_file,
  ..., manifest=None)`; `read_file` is `billx.reader.pipeline.read_file`, imported lazily
  when None so tests inject a fake. An engine exception is recorded by class name only.
  `EvalResult.summary()` (JSON, Decimals as strings), `.markdown()`, and `.ok()` (no silent
  error, no false refusal, no non-bill read as a bill, no engine error, every planted
  misread caught: what section 10 demands on `main`).
- `report.py`: `write_report(result, path)` writes the Markdown report (headed with the
  set name, date and engine version; `unmeasured` for a real set) and the JSON summary
  beside it. Both carry counts, rates, case ids, field paths and check ids only; never a
  value or a name. The report for a stage goes in `docs/accuracy/<date>-<set>.md`.

## tools and CI (Stage 0)

- `tools/identifiers.py`: the client-identifier search over tracked files, a directory,
  an exported image (tar) or stdin; identifiers from the CI secret and
  `~/billx-data/client-identifiers.txt`, reported by index only.
- `tools/check_copy.py`: CLAUDE.md and AGENTS.md equal sections 1-5 of the build prompt.
- `tools/watch/watch.py`: ruff, pytest, the copy check, the identifier search and the
  import-boundary test into `.status/checks.json`.
- `tools/mac/`: `doctor.sh`, `session.sh`, `mirror.sh` with its launchd job, the inactive
  nightly evaluation job, `install-jobs.sh`, and the local-OCR check (`ocr_check.sh`).
- `billx/reader/providers/ping.py`: the one-token call `doctor.sh` makes to each model id.
- `.gitlab-ci.yml` (D1 moved CI from GitHub to GitLab): the same checks plus gitleaks; the
  image jobs are below.

## docker and CI (Stage 2.5)

- `docker/engine.Dockerfile`: one CPU image for linux/amd64 and linux/arm64 from
  `python:3.12-slim`, with the system libraries the OCR runtimes load (libgl1, libglib2.0-0,
  libgomp1), paddlepaddle pinned (`PADDLEPADDLE_VERSION`, 3.3.1) from Paddle's own index with
  `--no-deps` (PyPI has no linux/arm64 wheel past 3.2.2; that index supplies nothing else),
  then `pip install --editable '.[ocr]'`, so paddleocr, rapidocr and
  onnxruntime are in both images and the package stays at `/app` (the label rule, the gate
  and the field map resolve `profiles/` and `config/` relative to the package, so a plain
  site-packages install would not find them). The build runs `docker/ocr_warmup.py` as the
  service user: it reads a tiny synthetic page through `billx.reader.ocr.read_words`, which
  downloads PaddleOCR's detection and recognition models into `PADDLE_PDX_CACHE_HOME`
  (`/home/billx/.paddlex`, inside the image) and proves one engine reads on that platform;
  RapidOCR's models ship in its wheel. At run time the container needs no network for OCR:
  `billx/reader/ocr` picks PaddleOCR where it initialises and RapidOCR otherwise (linux/amd64
  under emulation; a native amd64 runner is checked by the `ocr-check-amd64` job). Non-root
  user `billx` (uid 10001), `BILLX_DATA_DIR=/data` as the only writable path (`VOLUME`),
  `BILLX_OCR_CACHE=/data/cache/ocr`, `EXPOSE 8080`, `ENTRYPOINT ["billx"]`, `CMD ["serve"]`,
  and a `HEALTHCHECK` that calls `GET /v1/health` with the token from `BILLX_TOKEN` through
  Python's standard library (no curl in the image). No secret enters the file; the OCI
  `revision` label carries the commit CI passes as `VCS_REF`. The same warm-up script, run in
  the finished container with `--network none`, is the smoke check that records which engine a
  platform picks.
- `docker/compose.yaml`: the service `bill-engine` as esgOS runs it: the registry image
  (`BILLX_IMAGE` overrides), `BILLX_TOKEN` (required, from the `.env` beside the file),
  `BILLX_API_MODE` default `esgos-1.1`, `BILLX_MAX_JOBS` 4, `./data:/data`, port 8080 on the
  loopback, `read_only: true` with a tmpfs `/tmp`, `mem_limit: 2g`, no capabilities, no new
  privileges. Its header says how esgOS wires it (`BILL_ENGINE_URL=http://bill-engine:8080`,
  `BILL_ENGINE_TOKEN`).
- `.gitlab-ci.yml`, stages `checks`, `images`, `release`:
  `checks` and `gitleaks` (Stage 0); `ocr-check-amd64` (manual, default branch: the Stage 0
  OCR check built and run natively on the amd64 runner); `images` (docker:27 with
  docker-in-docker, QEMU through `tonistiigi/binfmt`, one `docker buildx build` for
  `linux/amd64,linux/arm64` pushed to `$CI_REGISTRY_IMAGE/billx` tagged with the commit sha
  and the branch or tag slug); `identifier-search-image` (the amd64 image's filesystem
  exported with `docker export` and searched by `tools/identifiers.py --require --tar`);
  `release-to-esgos` (on a tag, only when `ESGOS_REGISTRY` and `ESGOS_REGISTRY_KEY` exist:
  `docker login -u _json_key` over stdin, then `docker buildx imagetools create` copies the
  manifest by digest, so esgOS runs the bytes CI tested). Every secret reaches docker through
  `--password-stdin`; a test asserts no job echoes one.
- `tools/image/measure_memory.sh`: the memory figure a release states. It starts the image
  as compose does (read-only, tmpfs, a throwaway volume, `BILLX_MAX_JOBS=4`, a random token
  passed through the environment and a header file, never printed), writes the synthetic set
  with the image's own `billx synth`, submits the four digital electricity PDFs to
  `POST /v1/jobs` at once, samples `docker stats` every second until every job is `done` or
  `failed`, and prints baseline and peak in MiB (and JSON with `--json`). Before `billx serve`
  exists in an image it exits 2 with `status=api_unavailable` and what it sampled.
- `tests/unit/test_docker_files.py`: static assertions over these files (non-root user,
  the volume, the port, the entrypoint, the env names, read-only compose, the four CI jobs,
  no echoed or literal secret, the script parses).

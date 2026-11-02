# billx runbook

## Studio (confirmation mode)

Start it on the Mac (it listens on 127.0.0.1 only):

1. `cd ~/billx && .venv/bin/billx studio --workspace avvnl-sample --port 8750`
   (a bare name lives in `~/billx-data/workspaces/<name>/`; set `BILLX_DATA_DIR` to use
   another data folder).
2. Open `http://127.0.0.1:8750/` in a browser.
3. Type your name. The pre-fill is the engine's own reading: the PDF's text layer and local
   OCR always; Model A and Model B too when "Allow cloud model" is ticked and a key is in
   `~/billx/.env` (`BILLX_OPENAI_API_KEY`, `BILLX_ANTHROPIC_API_KEY`). Unticked, no file leaves
   the Mac.

Confirm the sample set (Stage 3.3; ten AVVNL and ten PVVNL bills first):

1. `cd ~/billx && .venv/bin/billx studio --workspace sample --port 8750`, then open
   `http://127.0.0.1:8750/` and type your name. Leave "Allow cloud model" ticked only if the
   keys are in `~/billx/.env`; otherwise untick it (the text layer and local OCR still pre-fill
   every digital PDF).
2. In "Add a folder of bills" paste `/Users/ventureaayuda.energy/billx-data/golden/unconfirmed/AVVNL`
   and press Add; then the same with `.../unconfirmed/PVVNL`. Files stay where they are.
3. Open the first bill. Wait for the engine's reading (about 25 s a page the first time; the
   OCR words are cached afterwards).
4. Read the "Engine" line: `passed` means every field below is `verified`; `needs_review`
   lists why. Check the `disputed` and `unverified` fields against the page image first, then
   glance at the `verified` ones.
5. Fill the three identity boxes once per discom: Discom (`AVVNL` or `PVVNL`), Layout id (for
   example `avvnl-ht-2025`), Input kind (digital PDF, scan or photo: correct the guess).
6. For every field: tick **Confirm** when the box matches the image, type the value exactly as
   printed when it does not, tick **Not printed** when the bill does not show it.
7. Press **Save**; the next unconfirmed bill opens. Stop after ten per discom. The entries are
   in `~/billx-data/golden/manifest.jsonl`; `billx eval --golden --report docs/accuracy/<date>-golden.md`
   then gives the first real figures (labelled unmeasured).

Confirm a bill:

1. On the front page, paste the full path of a folder of bills (PDF, JPEG, PNG) into
   "Add a folder of bills" and press Add. Files stay where they are.
2. Click a bill. Its pages are on the left, the fields on the right.
3. Pick the bill kind (electricity or gas) first; changing it reloads the fields.
4. Type the discom, a layout id (for example `avvnl-ht-2024`), and correct the input kind
   if the guess is wrong.
5. For each field, the pre-fill column shows the value the engine decided, a badge
   (`verified`: two readers agreed; `disputed`: they disagreed; `unverified`: one reading)
   and what each reader saw. The "Engine" line above the table gives the status, the review
   reasons and every check that failed or warned. If the value in the box matches the image,
   tick **Confirm**; if not, type the value exactly as printed (this ticks Confirm); if the
   bill does not print it, tick **Not printed**. Look hardest at `disputed` fields.
6. Press **Save**. The entry goes to `~/billx-data/golden/manifest.jsonl` with the seconds
   you spent on the bill, and the next unconfirmed bill opens. Saving a bill again appends
   a correction that supersedes the earlier entry.

Model usage for pre-fill is in `~/billx-data/workspaces/<name>/usage.jsonl` (no values).

## Local OCR

- One page takes about 20 s on this Mac (PaddleOCR, CPU). Results are cached by image hash
  under `~/billx-data/cache/ocr/` (`BILLX_OCR_CACHE` overrides the folder; `off` disables
  it), so a page is read once. `BILLX_OCR_THREADS` (default 4) limits one engine's threads;
  two engines on one machine thrash each other, which is why the OCR tests share one pytest
  worker (`--dist loadgroup`).
- `pytest -m "not ocr"` runs the suite without the engine in under a minute.

## The service

- `BILLX_TOKEN=<long random string> BILLX_API_MODE=esgos-1.1 BILLX_DATA_DIR=/data billx serve`
  (port 8080). `docs/api.md` lists the calls and settings; `docker/compose.yaml` the esgOS
  wiring.
- `billx examples --synthetic out/synth` rewrites `contract/examples/<mode>/` (nine cases
  per mode: the routes and every failure) from the synthetic set of seed 1; the contract
  test runs them against the app.
- `billx openapi` rewrites `contract/openapi.json` from the app; `billx openapi --check`
  exits 1 when it is stale (CI runs it).

## The command line

- `billx extract FILE... [--allow-cloud-model --max-cost-usd 1.00] [--out DIR]`: one result per
  file (the contract envelope as JSON); with `--out`, one `<stem>.billx.json` each and a one-line
  status per file.
- `billx validate RESULT.json...`: re-runs every check on a saved result's `data`.
- `billx eval --synthetic DIR [--report FILE]`: the engine over a `billx synth` folder, with the
  metrics of build prompt section 8; exit 1 on any silent error, false refusal or missed planted
  misread. `billx eval --golden` runs the confirmed manifest (a person runs it; no values in
  the report).

## The build Mac

- `tools/mac/doctor.sh`: pass or fail per item of section 3.1; never prints a secret.
- `tools/mac/session.sh N BRANCH "Run day D, session X of docs/build-prompt.md"`: a builder
  session in `~/billx-worktrees/BRANCH` in tmux window `billx:session-N`, beside the
  watcher and log windows (`tmux attach -t billx`). Logs in `~/billx-data/logs/`.
- `.venv/bin/python tools/watch/watch.py`: the watcher; results in `.status/checks.json`.
- `tools/mac/install-jobs.sh`: activates the nightly mirror (01:30) once `BILLX_MIRROR_VOLUME`
  in `.env` names a mounted drive. The mirror's log is `~/billx-data/logs/mirror.log`.
- `tools/mac/ocr_check.sh`: the local-OCR check on the three platforms (Docker running).

## The engine image

Build and check it on the Mac (Docker Desktop running; `linux/arm64` is native here,
`linux/amd64` runs under emulation and takes far longer):

1. `cd ~/billx && docker buildx build --platform linux/arm64 --load -f docker/engine.Dockerfile -t billx:local --build-arg HTTP_PROXY=http://http.docker.internal:3128 --build-arg HTTPS_PROXY=http://http.docker.internal:3128 .`
   The two proxy arguments are for this Mac only: Docker Desktop here throttles a container's
   own downloads to about 30 KB/s (apt and pip inside a build step) while its built-in proxy
   at `http.docker.internal:3128` runs at the host's speed. BuildKit hands `HTTP_PROXY` and
   `HTTPS_PROXY` to the build steps without writing them into the image; leave them out on a
   machine that does not need them (CI does not).
2. `docker run --rm billx:local --help` (the `billx` command inside the image).
3. `docker run --rm --network none --read-only --tmpfs /tmp --entrypoint python billx:local docker/ocr_warmup.py`
   prints `{"platform": "linux-arm64", "engine": "paddleocr", "words": N}`: the OCR models are
   inside the image and no download runs. On `linux/amd64` the engine is `rapidocr`
   (decisions.md, Stage 0).
4. `docker image inspect billx:local --format '{{.Size}}'` for the size that goes in the
   release notes.

Run it as esgOS does:

1. `cd ~/billx/docker && cp ../.env.example .env`, then set `BILLX_TOKEN=` to a long random
   string (for example `openssl rand -hex 32`). Model keys are optional (empty means not
   configured). The file is git-ignored.
2. `mkdir -p data` (on a Linux host also `chown 10001:10001 data`: the container's user).
3. `BILLX_IMAGE=billx:local docker compose up -d` (without `BILLX_IMAGE` the registry's
   `latest` is pulled).
4. `docker compose ps` shows `healthy` once `GET /v1/health` answers;
   `curl -H "Authorization: Bearer $BILLX_TOKEN" http://127.0.0.1:8080/v1/health`.
5. `docker compose down` stops it; `data/` keeps the job store (jobs older than 24 hours are
   swept by the service).

Measure the memory figure for a release (4 jobs at once):

1. `tools/image/measure_memory.sh billx:local --json out/memory.json`
2. The line `measure_memory: ... baseline_mib=... peak_mib=... status=ok` is the figure; the
   integrator records the peak in the release notes. `status=api_unavailable` means the image
   has no working `billx serve`; `timeout` means a job did not finish within `--timeout`
   seconds (default 900).

CI (GitLab, `.gitlab-ci.yml`):

- Variables under Settings > CI/CD > Variables: `CLIENT_IDENTIFIERS` (masked; the identifier
  search fails without it), `ESGOS_REGISTRY` and `ESGOS_REGISTRY_KEY` (protected, masked; the
  tag release only), optional `BILLX_IMAGE_PLATFORMS` (default `linux/amd64,linux/arm64`).
  GitLab's own `CI_REGISTRY_*` variables log the jobs into the project registry.
- Every pipeline: `checks`, `gitleaks`, then `images` (both platforms to
  `registry.gitlab.com/icac1/ocr-bill-extraction/billx:<sha>` and `:<branch-or-tag>`), then
  `identifier-search-image`. The arm64 half builds under QEMU on the amd64 runner and is slow
  (the job's timeout is 3 h); set `BILLX_IMAGE_PLATFORMS=linux/amd64` to skip it in a hurry.
- A tag (`git tag 0.1 && git push origin 0.1`) also runs `release-to-esgos` when the two esgOS
  variables exist: the manifest is copied by digest to `$ESGOS_REGISTRY/billx:<tag>`.
- `ocr-check-amd64` is manual on `main`: run it once from the pipeline page to record which OCR
  engine a native amd64 machine picks (its JSON line is a job artifact).

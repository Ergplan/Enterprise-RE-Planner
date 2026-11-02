# The billx API

One service, two modes, chosen by `BILLX_API_MODE`:

- `esgos-1.0`: exactly esgOS's bill engine contract 1.0 (`contract/esgos-1.0/contract.md`).
- `esgos-1.1` (default): contract 1.0 plus the optional additions of contract 1.1
  (`contract/esgos-1.1/contract.md`, explained in `docs/contract-1.1.md`).

`BILLX_STORAGE` is `ephemeral` (the only shipped value): files and results live under
`BILLX_DATA_DIR` for at most 24 hours.

## Running it

```bash
BILLX_TOKEN=<a long random string> BILLX_API_MODE=esgos-1.1 BILLX_DATA_DIR=/data billx serve
```

Settings: `BILLX_TOKEN` (required), `BILLX_API_MODE`, `BILLX_DATA_DIR`, `BILLX_MAX_JOBS`
(default 4), `BILLX_QUEUE_LIMIT` (default 32), `BILLX_RETENTION_HOURS` (default 24), and the
model keys `BILLX_OPENAI_API_KEY` / `BILLX_ANTHROPIC_API_KEY` (absent: no cloud reader, and
a scan whose job allows one ends `unreadable` with note `no_model_configured`). The image
(`docker/engine.Dockerfile`) listens on 8080; `docker/compose.yaml` shows the esgOS wiring.

## Calls

Exactly contract 1.0's five calls, with `Authorization: Bearer <BILLX_TOKEN>`:

| Call | Notes |
| --- | --- |
| `GET /v1/health` | `contract_version` says the mode; `ocr` and `cloud_model` say what is configured |
| `POST /v1/jobs` | multipart `file` + `options` (JSON). 202 with `job_id`. In 1.1 mode `wait: true` returns the finished job (200) within 50 s |
| `GET /v1/jobs/{job_id}` | `queued`, `reading`, `done` (with `result`) or `failed` (with `error`) |
| `DELETE /v1/jobs/{job_id}` | 204; the file, result and feedback go at once |
| `POST /v1/feedback` | 202; keeps the path and whether the engine was right, never the values beyond the job's life |
| `GET /metrics` | Prometheus text: request counts, jobs by status, job seconds, queue depth, running jobs. Same token |

Errors are contract section 8's table, always `{"error": {"code", "message"}}`; a 1.1
option sent in 1.0 mode is 400 `bad_request`. `X-Request-Id` is echoed; a `traceparent`
trace id is logged with it on every line. Logs are JSON lines with ids, hashes, counts,
timings and check ids only.

## What a result says

Each bill carries `profile.status` (`final`, `draft`, `none`) and, in 1.1, `audit_status`
(`not_audited` until the tariff engine exists) and `accepted`. A downstream report labels its
figures with both. Accuracy on real bills is `unmeasured` until the team's confirmed sample
exists; every value carries its `proof` and `readers` in 1.1 so a caller can see how it was
read.

## Examples and tests

`contract/examples/<mode>/` holds synthetic requests and responses, at least one per route
and one per failure; `tests/contract/` runs them against the app. `contract/openapi.json` is
generated from the app (`billx openapi`) and checked in CI.

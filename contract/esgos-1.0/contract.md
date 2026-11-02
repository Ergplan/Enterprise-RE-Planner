Copied word for word from esgOS's `docs/bill-engine-contract.md`. esgOS owns it; billx implements it. Never edit it here.

# Bill engine contract, version 1.0

This is the agreement between esgOS, or any other Joulewise product, and the bill engine. It covers what a product sends, what it gets back, and what each side is responsible for. The dev team builds the engine, and products build against this document. Change it only by agreement between the two, and version every change (section 9).

Decided on 7 Oct 2026 (B4 Bill scanning, B11 row 40).

## 1. What the engine is

- A headless HTTP service that reads electricity and gas bills. For each bill it returns the values, where on the page each value came from, and the result of checking the bill's own arithmetic.
- One copy runs inside each product's stack, on its private internal network, never exposed to the internet. A product's bills never leave that product's infrastructure, except to the cloud model, and only when the product allows it.
- It keeps a file and its result only until the product deletes the job, and never longer than 24 hours.
- It has no users, approves nothing and keeps no product data. What a value means for the product is the product's decision: which site, which month, whether to use it.

## 2. Who does what

| The engine | The calling product |
| --- | --- |
| Normalises each page (rotation, deskew, contrast), runs local OCR with word positions, and identifies the utility and the version of its profile | Stores the original file and refuses duplicates by sha256 |
| Reads known layouts by template, and others with a vision model. Transcribes every printed line; never calculates | Decides, per request, whether a cloud model may be used and the most it may spend |
| Places each value on its page and image region | Records every model call the engine reports, against the organisation's allowance |
| Checks each bill on its own: readings × multiplying factor, quantity × rate, section subtotals, current + arrears + adjustments = net payable, tariff rules, layout drift | Checks bills against each other: continuity of readings, period gaps and overlaps, duplicates, month-on-month change |
| Owns the utility profiles and their versions, the test bills and the accuracy figures | Maps accounts to sites, splits periods into months, uses the values, and shows the calculation trace |
| Reports its version, the profile version, the route and the cost with every result | Sends corrections back as feedback |

## 3. Connection

- **Address.** The base URL comes from the product's configuration (esgOS: `BILL_ENGINE_URL`, for example `http://bill-engine:8080`). Plain HTTP, on the internal network only.
- **Authentication.** Every request carries `Authorization: Bearer <token>` (esgOS: `BILL_ENGINE_TOKEN`, held in Secret Manager in production). Any request without it gets 401.
- **Format.** JSON in UTF-8, except the file upload, which is multipart. Times are UTC, in ISO 8601.
- **Tracing.** A request may carry `X-Request-Id` and a W3C `traceparent` header. The engine logs them and echoes `X-Request-Id`, so a bill can be followed through both services.
- **Network.** The engine calls nothing outside its own container except its configured model provider, and calls even that only when the request allows it.

## 4. Calls

### 4.1 `GET /v1/health`

Returns 200:

```json
{
  "status": "ok",
  "engine_version": "1.0.0",
  "contract_version": "1.0",
  "schema_version": "1.0",
  "profiles_version": "2026-10-07",
  "ocr": "ready",
  "cloud_model": "configured"
}
```

### 4.2 `POST /v1/jobs`

The body is `multipart/form-data` with two parts.

- **`file`:** one PDF (digital or scanned), JPG, PNG, HEIC, WebP or TIFF. At most 25 MB and 30 pages. One file may hold several bills.
- **`options`:** JSON.

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `request_id` | string, up to 64 characters | yes | The product's id for this file. Sending the same id again returns the same job. |
| `product` | string | yes | `"esgos"`, used only in the engine's logs and statistics |
| `kind` | `"bill"` or `"text"` | no, default `"bill"` | `"text"` returns page text with word positions only, for scanned documents that are not bills (section 5.3) |
| `bill_type` | `"electricity"`, `"gas"` or `"auto"` | no, default `"auto"` | |
| `allow_cloud_model` | boolean | yes | `false`: local OCR and templates only, with no call to a cloud model |
| `max_cost_usd` | decimal string | yes, when `allow_cloud_model` is true | The most this job may spend |
| `hints` | object: `utility_id`, `account_number`, `bill_month` | no | From earlier bills of the same account. The image always wins over a hint. |

Returns 202:

```json
{ "job_id": "0199b6c2-5f1e-7a3c-9d41-2b7e8f0a1c33", "status": "queued" }
```

### 4.3 `GET /v1/jobs/{job_id}`

```json
{
  "job_id": "0199b6c2-5f1e-7a3c-9d41-2b7e8f0a1c33",
  "request_id": "file_0199b6c1-…",
  "status": "done",
  "submitted_at": "2026-10-07T10:15:02Z",
  "finished_at": "2026-10-07T10:15:24Z",
  "error": null,
  "result": { "…": "section 5" }
}
```

`status` is `queued`, `reading`, `done` or `failed`. A failed job carries an `error` object (section 8) and no result. Products poll it: esgOS polls every 5 seconds with backoff, for at most 10 minutes.

### 4.4 `DELETE /v1/jobs/{job_id}`

Deletes the file, its page images and the result straight away, and returns 204. The product calls this once it has stored the result.

### 4.5 `POST /v1/feedback`

Sent when a person corrects a value the engine read:

```json
{
  "job_id": "0199b6c2-5f1e-7a3c-9d41-2b7e8f0a1c33",
  "file_sha256": "9f2c…",
  "bill_index": 0,
  "corrections": [
    { "path": "energy.kwh", "engine_value": "12400", "final_value": "12460" }
  ]
}
```

Returns 202. Feedback is used only for accuracy figures and to propose profile changes, which a person on the dev team approves. The engine keeps the path, the profile version and whether the value was right. It keeps no bill values beyond 24 hours.

## 5. The result

### 5.1 The envelope

```json
{
  "contract_version": "1.0",
  "engine_version": "1.0.0",
  "schema_version": "1.0",
  "file": { "sha256": "9f2c…", "pages": 2, "media_type": "application/pdf" },
  "bills": [ { "…": "section 5.2" } ],
  "usage": [
    { "provider": "openai", "model": "…", "purpose": "bill_read",
      "input_tokens": 9000, "output_tokens": 4000, "cost_usd": "0.0412" }
  ],
  "seconds": 21.4
}
```

`usage` lists every model call made for this job, so the product can record each one. It is empty when no model was called.

### 5.2 Each bill

| Field | Meaning |
| --- | --- |
| `index` | the bill's position in the file, from 0 |
| `pages` | the pages it covers, for example `[1, 2]` |
| `bill_type` | `electricity` or `gas` |
| `utility` | `id`, `name_as_printed`, `state`; `id` is null when the utility is unknown |
| `profile` | `id`, `version`, `status` (`final`, `draft` or `none`) |
| `route` | `template`, `local_model`, `cloud_model`, or `none` when the bill could not be read |
| `fields` | the guaranteed fields (section 6), each a field object |
| `data` | the full transcription in the engine's own schema (every printed line, with its section, kind and stage), for products that want it |
| `checks` | each with `id`, `description`, `status` (`pass`, `fail`, `warn` or `skip`), `expected`, `actual`, `tolerance` and `paths` |
| `passed` | true only when no check failed and every required field (section 6) is present |
| `unread_reason` | null, or `model_not_allowed`, `budget_exceeded`, `unreadable` or `not_a_bill` |
| `notes` | the engine's notes on unreadable or ambiguous readings |

A field object:

```json
{
  "value": "12400",
  "unit": "kWh",
  "printed": "12,400",
  "page": 1,
  "region": { "x": 0.512, "y": 0.341, "w": 0.120, "h": 0.018 },
  "source": "template"
}
```

- **`value`:** numbers are exact decimal strings, with no floating point and no digit grouping. Dates are `YYYY-MM-DD`, months `YYYY-MM`, and text is as printed. Null when the bill doesn't show it.
- **`printed`:** the text exactly as it appears on the bill.
- **`region`:** the area on the page, as fractions of the page's width and height, measured from the top left. Null when the engine cannot place it.
- **`unit`:** one of `kWh`, `kVAh`, `kVArh`, `kW`, `kVA`, `SCM`, `MMBtu`, `kcal/SCM`, `INR`, `%`, `days`.
- **`source`:** `template`, `ocr` or `model`.

### 5.3 A `text` job

For `kind: "text"`, each entry in `bills` is replaced by `pages`. Each page has its `page` number, its `text`, and its `words`, each word with `text` and `region`. Nothing is extracted or checked.

## 6. The guaranteed fields

Every bill result carries these paths, with null where the bill doesn't print the value. Fields marked "required" must be present for `passed` to be true.

**Electricity**

| Path | Unit | Required |
| --- | --- | --- |
| `utility.name` | | |
| `consumer.account_number` | | required |
| `meter.number` | | |
| `connection.tariff_category` | | |
| `period.from`, `period.to` | date | required |
| `period.bill_date` | date | |
| `period.bill_month` | month | required |
| `readings[]`: `register`, `previous`, `current`, `multiplying_factor`, `tod_slot` | kWh, kVAh | |
| `energy.kwh` | kWh | required |
| `energy.kvah` | kVAh | |
| `energy.tod[]`: `slot`, `kwh` | kWh | |
| `demand.max_kva`, `demand.contract_kva` | kVA | |
| `energy.power_factor` | | |
| `net_metering.export_kwh`, `net_metering.import_kwh` | kWh | |
| `charges.energy`, `charges.demand` | INR | |
| `totals.net_payable` | INR | required |

**Gas**

| Path | Unit | Required |
| --- | --- | --- |
| `utility.name` | | |
| `consumer.customer_id` | | required |
| `meter.number` | | |
| `period.from`, `period.to` | date | required |
| `readings.previous`, `readings.current` | SCM | |
| `volume.scm` | SCM | required, unless `energy.mmbtu` is present |
| `gas.gcv_kcal_per_scm` | kcal/SCM | |
| `energy.mmbtu` | MMBtu | required, unless `volume.scm` is present |
| `totals.amount` | INR | required |

## 7. Behaviour products rely on

- **The model transcribes and never calculates.** Every value is printed on the bill; all arithmetic happens in the checks.
- **A check whose inputs are missing reports `skip`, never `pass`.**
- **`passed` is false whenever any check fails.** A product never receives a passed bill with a failing check.
- **With `allow_cloud_model` false, no cloud call is made.** A bill that would need one comes back with `passed: false`, `route: "none"` and `unread_reason: "model_not_allowed"`.
- **The engine never spends more than `max_cost_usd`.** When the cap is reached it stops and returns `unread_reason: "budget_exceeded"`.
- **Results are repeatable** for a given file, engine version and profile version, as far as the model allows: temperature 0 where the model accepts it.
- **Logs carry ids, sha256, timings and check ids, never bill values or names.**

## 8. Errors

The error body is always `{ "error": { "code": "…", "message": "…" } }`.

| HTTP | `code` | When |
| --- | --- | --- |
| 400 | `bad_request` | malformed body or options |
| 401 | `unauthorised` | missing or wrong token |
| 404 | `not_found` | unknown job |
| 409 | `conflict` | a `request_id` reused with a different file |
| 413 | `too_large` | over 25 MB or 30 pages |
| 415 | `unsupported_type` | not one of the file types in 4.2 |
| 422 | `invalid_options` | for example `allow_cloud_model` true without `max_cost_usd` |
| 429 | `busy` | the queue is full; a `Retry-After` header says when to try again |
| 500 | `internal` | anything else, logged with the request id |

## 9. Versions and delivery

- **Contract versions are `major.minor`.** A minor version only adds optional fields or calls, and products ignore fields they don't know. A major version may break things; it gets a new path (`/v2`), and the engine keeps serving the previous major for at least three months. Each product pins the major version it uses.
- **Every result carries `engine_version`, the profile id and version, and `schema_version`.** The product stores them with the values it uses.
- **The dev team delivers, for each release:**
  - the image, which products pin by digest
  - release notes
  - the container's memory need
  - an `examples/` folder of synthetic bills with their expected results, at least one per route and one per failure. Products use these for their contract tests and their mock. Real bills are never in `examples/`.
- **Performance targets:** a one-page bill in under 60 seconds at the 95th percentile with a cloud model, and at least 4 jobs at once, with the rest queued.

## 10. Still to agree between the teams

- The container's name, port and memory.
- The date of the first image. esgOS needs it for Stage 6, and builds against a mock made from `examples/` until it arrives.

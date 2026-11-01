# Stage 8 report — breadth and launch

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**Sign-in and access (`platform/auth.py`, `platform/mail.py`, `routers/auth.py`; migration 0009).**
- Sign-in is by email link. The link works once and lasts 15 minutes. The session cookie lasts 30 days and is HttpOnly. Only SHA-256 digests of the link and the cookie are stored.
- Two roles. Emails at `ERGPLAN_ANALYST_DOMAIN` (joulewise.in) or listed in `ERGPLAN_ANALYST_EMAILS` are analysts; everyone else is a client.
- One app-wide guard applies the policy:
  - public routes: the shared plan, documents, sign-in, health, shapes, the price vintage a market citation opens, and voice/chat (which check the plan token or sign-in themselves);
  - every other route needs sign-in;
  - any route carrying a connection, site, bill, scenario or run id is checked for ownership, and ids sent in a request body are checked too.
- Bills are read by billx once per file but owned per uploader: a second uploader of the same PDF gets their own rows and cannot reach the first uploader's.
- In production the development headers are ignored. Without a mail server, production refuses to issue a link (503); a mail server that refuses answers 502.
- Security headers come from both the API and Caddy, with CORS limited to the public URL. `tools/dev/secrets-check.py` runs in the watcher and in CI.
- The web app has `/login`, `/login/verify`, a signed-in bar with sign-out, and redirects to sign-in in production.

**Breadth.** Rulebooks approved through `rulebook.service`, with golden tests, from the orders on the Mac mini:

| State | Jurisdiction | Families approved | Golden tests |
| --- | --- | --- | --- |
| Karnataka | `ka_escoms` (BESCOM, MESCOM, CESC, HESCOM, GESCOM) | tariff_schedule (HT-2(a)), tod_slots | 12 |
| Telangana | `tg_discoms` (TGSPDCL, TGNPDCL) | tariff_schedule (HT-I(A), kVAh by voltage), tod_slots | 11 |
| Punjab | `pspcl` | tariff_schedule (LS general industry, two contract-demand bands, 80 % floor) | 7 |

Gujarat, Rajasthan, Haryana, Tamil Nadu and Andhra Pradesh are registered but **not yet sourced**; the reasons are below. `GET /rulebooks/coverage` gives the honest map per state, the `/rulebooks` page shows it, and the options board and the live plan say "not yet sourced" where a state has no approved rule. Eighteen DISCOMs were added to the jurisdictions and to the intake defaults (names, billx aliases, printed categories, usual voltages), each named once (a test checks this).

**Performance.**
- The worker runs several processes (`--concurrency`, `ERGPLAN_WORKER_CONCURRENCY`), each claiming runs with `FOR UPDATE SKIP LOCKED`.
- Approved rules are cached per process. The cache is dropped whenever the approved set changes; the stamp is a hash of the approved version ids and their effective windows, read in the caller's transaction.
- A settled plan answers in about 30 ms from the API and about 220 ms for the page. The suite checks it stays under 1 s.

**Deployment, prepared but not done.** `docker/compose.prod.yaml`: only Caddy is exposed, with automatic TLS for `SITE_ADDRESS`, `ERGPLAN_ENV=prod` and worker concurrency. The API image installs Chromium for PDF export. `tools/dev/backup.sh` takes a nightly pg_dump and a data/ archive, keeps 14 days and can copy to a bucket. `docs/deploy.md` is the VM runbook.

**Release note.** `docs/release-notes/2026-11-01-ergplan-1.0.md`.

## Definition of done

| Check | State |
| --- | --- |
| Eight states approved | **Not met: 5 of the 10 states the plan names have approved rules** (UP, MH from Stage 1; KA, TS, PB now). Rule rows sourced over rows present: 100 %. States attempted over states in the prompt: 8 of 8, of which 3 approved and 5 recorded as not yet sourced with a reason. "Not yet sourced" is the correct answer where the document is missing or the schema cannot hold it (section 9). |
| Login and roles | Met (`tests/platform/test_auth.py`: sign-in, roles, logout, expiry, development headers ignored in production, ownership across clients, mail refusal) |
| Deployed with TLS | **Not met: needs the VM, the hostname and SMTP** (open question 1). The production compose, Caddy TLS, backup and runbook are ready. |
| Final full pass green | Met. Watcher green (295 tests plus web typecheck and tests, rulebooks, field-trace, secrets). Slow suite: the 5 MW UP and MH sites at 15 minutes and the Stage 6 end-to-end, 3 passed in 5 min 38 s; the two Stage 7 journey tests skip there by design. Browser journey (`tools/dev/e2e-journey.sh`, NPCL and MSEDCL real bills): 2 passed in 4 min 46 s. Stage 8 states end-to-end (KA, TS, PB avoided cost; coverage): passed. |
| Release note | Met |

## Why five states are not yet sourced

- **Gujarat (GERC).** The HTP-I demand charge is in slabs of billing demand; `tariff_schedule` has no slab table. Needs a schema change.
- **Rajasthan.** The file on the mini is an HTML/JS page, not the RERC order.
- **Haryana.** A 7-page scanned notice, not the HERC schedule.
- **Tamil Nadu.** The order holds FY 2025-26 rates indexed by CPI from July 2026; the indexed FY 2026-27 schedule is not in the corpus.
- **Andhra Pradesh.** The schedule pages have a garbled text layer, and page 230 has none, so the grounding check cannot pass.

In the approved states, open-access charges, losses and banking are not yet sourced, and Punjab's ToD (mid-month seasons, a Rs 5.50 cap) cannot be expressed by `tod_slots`. All of this is in `docs/known-gaps.md`.

## Skipped, and why

- **Deployment**, for the reason above. The Mac mini session reaches only a Linux sandbox with no Docker, so Compose has still not been run on real Docker. That is the first step on the VM.
- **Rate limiting on sign-in requests.** Links are single-use and expire in 15 minutes, but repeated requests are not throttled. Listed as a launch gap.

## Deviations

These are dated in `docs/decisions.md` (1 Nov 2026, Stage 8):
- **Three states approved instead of eight**, as above.
- **Reader drafts corrected by the analyst.** The reader read KERC's ToD paise as rupees, and its TGERC 33/132 kV and −50 paise quotes failed grounding. Those drafts were rejected and the rows typed from the same pages with verbatim quotes, then golden-tested and approved. The review notes say so.
- **Access policy lives in one guard,** not on each route.
- **Ops scripts stay in `tools/dev/`** to keep the section 5 layout.
- **The Stage 3 real-bill replay is scoped to UP and MH.** This is a test change, recorded in the commit message: a cached PSPCL bill entered it once PSPCL became a known DISCOM, and its printed "nature of industry" is not a tariff category.

## Reviewer findings and fixes

Nine rounds; the ninth reported no code defect (its by-design and unprovable items are the ones below). The last round is in `docs/stage-reports/stage-8-review.md` (kept locally, like earlier stages' reviews).

| Round | Finding | Fix |
| --- | --- | --- |
| 1 | `ERGPLAN_SECRET` had a code default | The setting was read by nothing (sessions are random tokens stored as digests), so it was removed from settings, `.env.example`, compose and the runbook. The line in your local `.env` is now unused and can be deleted. |
| 1 | DISCOMs listed twice in `jurisdictions.yaml` | Deduplicated (TANGEDCO folded into TNPDCL); a test asserts unique ids and that parents exist |
| 2 | Without SMTP, the page said "we sent a link" | Production answers 503 naming the setting; the page says mail is not set up; the runbook marks SMTP mandatory |
| 3 | Coverage endpoint had no direct test | `tests/platform/test_api_coverage.py` |
| 3 | Development sign-in untested; SMTP failure gave a 500 | Tests added; a refusing mail server answers 502 |
| 3 | HSTS set by both the API and Caddy | By design (defence in depth); the Caddyfile says so, and Caddy replaces rather than duplicates |
| 4 | `backup.sh` assumed `gsutil` | Checked before any work, with a clear message |
| 5 | New DISCOM aliases may not match billx's profile ids | Checked against billx's 11 DISCOM profiles; a test pins each to its DISCOM and state |
| 5 | Rule cache ignores the evaluation date | No defect: the date is part of the cache key `(family, jurisdictions, on)`; the stamp only says when the approved set changed. Unchanged |
| 5 | Coverage lists group ids (e.g. `ka_escoms`), not each DISCOM | By design: the list names the jurisdictions that hold the approved rows; the DISCOMs under a group are in `/rulebooks/jurisdictions` |

| 6 | Secrets check missed database passwords | `POSTGRES_PASSWORD` and a password inside `DATABASE_URL` in a committed env file now fail the check (probed with a throwaway file) |
| 6 | `backup.sh` assumes the production compose | By design (VM only); the header says so |
| 6 | Ownership of ids sent in a request body relies on each route calling `owned_bills` / `owned_connection` | By design for now: every current body-id route calls them and is tested; a central check would need a resource-kind map per body model. Listed in known gaps |
| 6 | Public routes matched by template | No defect: the guard compares FastAPI's matched route template (`/p/{token}`), and the production tests reach the public routes logged out |
| 6 | Fewer than eight states | Not resolvable by code; see the definition of done |
| 7 | Logout revocation and headers on a private route untested | Tested: a revoked session's cookie replayed gets 401; a signed-in route carries the security headers |
| 8 | Bearer use of the session token untested | Tested (a non-browser client sends the token as a bearer) |
| 8 | A plain-http public URL in production breaks the Secure cookie silently | The API logs a warning at start (tested) |
| 7 | An anonymous uploader could own a bill | No defect: `/bills` needs sign-in in production, and the router stores `uploaded_by` only for a signed-in caller |

Round 5's other four "code defects" are confirmations that the auth and coverage endpoints are tested and that the worker is not an endpoint.

Not changed, because a diff cannot prove them:
- the approvals themselves (they are in the exported `packages/rulebooks/states/`, which the reviewer does not see, and are asserted by `tests/e2e/test_stage8_states.py`);
- the `stage-8-done` tag named in the release note (recorded with this report);
- the deployment statement.

## Open questions

1. **Deployment.** Which Google Cloud project and VM (asia-south2), and which jouleWise hostname? Which SMTP account should send sign-in links?
2. **Missing documents.**
   - Rajasthan: the RERC tariff order PDF.
   - Haryana: the HERC order with its schedule.
   - Tamil Nadu: the CPI-indexed FY 2026-27 rates.
   - Andhra Pradesh: a copy with a text layer.
   - The OA-charge and banking orders for KA, TS and PB.
3. **Gujarat and Punjab schema changes.** Should demand slabs (Gujarat) and mid-month ToD seasons with a cap (Punjab) be added to the rule schemas in the next round?
4. **Analyst emails.** Besides @joulewise.in, which addresses should sign in as analysts?
5. **Re-approval.** The seeded rulebooks are approved by `build-agent@ergplan`. Should a jouleWise analyst re-approve each under their own name before client use?

## Cost

- Regulation reader: 5 gpt-5.1 calls, 20,948 tokens in and 6,276 out, USD 0.089 (from `model_calls`).
- Reviewer: nine gpt-5.1 rounds of about 37,000–40,000 tokens in each, about USD 0.50 in all.
- No billx reads (stored readings were reused).
- Builder: Claude subscription.

## Addendum, 1 Nov 2026 — the Mac mini as the server

You chose the mini as the server, so deployment now targets it instead of a VM.

- **Built:** `docker/compose.mini.yaml` (production mode, Caddy on LAN port 80), `tools/dev/mini.sh`, and `tools/dev/mini-install.sh`, delivered with a git bundle to `~/Downloads/ergplan-server/`. The installer sets up the code, settings, documents, rulebooks, prices, nightly backup and the first sign-in link. Supporting changes: operator-issued sign-in links, an IEX loader that reads from disk, a session cookie that is Secure only on https, the UP CRE Regulations added to the corpus index, and unreadable bill readings retried.
- **First real Docker run** (in the build workspace):
  - postgres, api, worker, web, billx and caddy are all healthy;
  - the 12 documents registered with the same ids as in development;
  - the rulebooks restored and the DAM and RTM prices loaded;
  - sign-in works through Caddy;
  - a client built three settled scenarios, shared the plan (opens logged out in 30 ms for the data, 130 ms for the page) and printed the PDF (3 pages, 1.6 s);
  - billx read the real NPCL bill (it needs its model key; without it the bill came back unreadable, which is now retried).
- **Fixed on the way:** there was no `.dockerignore`, so the build context carried `data/`, the virtualenvs and `node_modules`; the API image had no tesseract; pnpm was unpinned.
- **Not done by me:** the installer has to be run on the mini by you. I can only click in terminals there, not type, and the mini's sandbox shell cannot host a server. On Linux the script was dry-run with stand-ins for Docker and launchd; the macOS run itself is untested.
- **Still open:**
  - https and a public hostname (Cloudflare Tunnel, or a port forward);
  - an SMTP account, so sign-in links are mailed instead of issued by hand;
  - a DHCP reservation for the mini's address.
- **Reviewer:** three more rounds on the deployment work. Fixed: a logout test that checks the database (revoked rows, cleared cookie), and a test that pins the public routes to real routes. The reviewer also said `/voice/tool` was not a route; it is, and the new test confirms it.

## Addendum, 1 Nov 2026 afternoon — the VM, open access, Gujarat and Andhra Pradesh

**Deployed** on the Google Cloud VM `replanner` at https://34-131-62-161.sslip.io, with a Let's Encrypt certificate. The flow you chose is in place: commit here → push to GitHub → SSH from the Mac mini → `tools/dev/vm-install.sh`.
- The first install carried billx, the 24 indexed regulation files, the IEX files and the settings. The OpenAI key was read from Keys.rtf on the mini and never printed; the payload was deleted from the VM and the mini afterwards.
- Updates send a git bundle of `main` only.
- Console steps you did: the project SSH key, the web firewall rule and the 50 GB disk.
- The API image now installs its dependencies before copying the code, so code-only updates build quickly.

**Open access sourced from the tariff orders already in the corpus:**

| State | Approved | Golden tests |
| --- | --- | --- |
| Telangana | CSS per DISCOM and voltage; the aggregate T&D charge | 15 |
| Karnataka | CSS common to all ESCOMs; additional surcharge not levied; each ESCOM's HT wheeling charge and HT loss | 25 |
| Punjab | Wheeling per MW; 2 % in kind for renewable power within the State; T&D losses by voltage; CSS | 8 |

A charge levied in kind is applied as a loss and named "Losses and charges in kind".

**Two more states with approved tariffs:**
- **Gujarat** (HTP-I, common to the four state DISCOMs). The schemas grew to hold telescopic demand slabs, an excess-over-contract rate, a least billing demand, energy and ToD bands by billing demand, and an energy rebate by voltage. The evaluator, avoided cost, optimizer inputs and the judge use them.
- **Andhra Pradesh** (Category III(A) HT), from Table 11, which has a readable text layer.

States with approved tariffs: **7 of the 10** the plan names (UP, MH, KA, TS, PB, GJ, AP). Still not yet sourced:
- **Rajasthan:** the stored file is an HTML page.
- **Haryana:** the file is a UHBVN sales circular implementing the HERC order, with scanned tables whose OCR is too uncertain to quote. It was not seeded, on purpose (traceability beats speed).
- **Tamil Nadu:** the indexed FY 2026-27 rates are missing.

**Reviewer** (two rounds on the afternoon's diff):
- Fixed: the in-kind charge line label; explicit coverage assertions per state.
- By design: the VM forces `ERGPLAN_ENV=prod` through `compose.prod.yaml`; approvals live in `packages/rulebooks/states/`, which the reviewer does not see.

**Model cost:** none this afternoon. Every rule was authored from the page text with verbatim quotes, without the reader. Reviewer: four gpt-5.1 rounds, about USD 0.20.


## Addendum, 1 Nov 2026 evening — bill reading upgraded, the reading view, search

**Asked:** make bill extraction as exact as possible with Docling, LlamaParse and Haystack; show the bill on the left and the extracted values on the right, placed exactly where they are printed; hand the useful values to the planning screens. The person chose to put the new readers in billx (invariant 7 unchanged).

**Built in billx** (branch `readers-docling-llamaparse`, seven commits on `f84fa95`; `main` untouched): page sorting of multi-bill files; slot-wise open-access and net units (prompt `read_bill_v5`); the `docling` reader (docling-serve: tables, cells and boxes; a local layout reader, proof rule 3); the `llamaparse` reader (LlamaExtract v2 beside Model A, family `llamaindex`); every reader's reading in contract 1.1. billx's unit suite is green; its OCR-marked contract-example test fails on linux on `main` too and is regenerated on the Mac at merge (billx known gaps).

**Built in ergPLAN:** `docling` compose service; background bill reads (`bill_reads`, migration 0011, the worker's bill thread); the reading view (`/plan/intake/bill/[id]`: page and read page side by side, values in their printed boxes, zoom with synced scrolling, replay of the stored reading reader by reader, slots, values to confirm with each reader's reading, the bill's checks); the hand-off (`/plan-inputs`, every figure a SourcedValue); accepting a bill whose planning values are verified; reading a file again; search and analytics with Haystack BM25 (`/bills`).

**Measured on the person's PVVNL open-access file (live, on the server):** two bills found in the four pages; on each, all twelve slot figures (consumption, open access, billed for four slots) verified by Docling and Model A, each with its box; tariff category, demand, energy and billed totals, current charges, rebate and net payable verified; nothing outstanding for planning. Still for the client: the March power factor (both local readers dropped the decimal point), the names as printed, one due date. Model spend about US$0.24 per two-bill file. LlamaParse did not run: LlamaIndex refused the key (401, both regions).

**Reviewer** (gpt-5.1, diff fc233eb..working tree): 12 findings, 0 code defects. Acted on: a test that the search path imports no model SDK and switches Haystack's telemetry off; a test for analytics with no bills. The API rows for search it asked for are present. By design or later: optional unverified values left out of planning (recorded in decisions); ownership of `bill-reads` pages follows the per-route pattern already in known gaps.

**Open:** a working LlamaParse key; the billx team's merge of the branch (and a profile change for the PVVNL open-access G08/G09/G21 lines, measured on their golden set).

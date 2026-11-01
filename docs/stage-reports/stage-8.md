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

Five rounds; the last is in `docs/stage-reports/stage-8-review.md`.

| Round | Finding | Fix |
| --- | --- | --- |
| 1 | `ERGPLAN_SECRET` had a code default | The setting was read by nothing (sessions are random tokens stored as digests), so it was removed from settings, `.env.example`, compose and the runbook. The line in your local `.env` is now unused and can be deleted. |
| 1 | DISCOMs listed twice in `jurisdictions.yaml` | Deduplicated (TANGEDCO folded into TNPDCL); a test asserts unique ids and that parents exist |
| 2 | Without SMTP, the page said "we sent a link" | Production answers 503 naming the setting; the page says mail is not set up; the runbook marks SMTP mandatory |
| 3 | Coverage endpoint had no direct test | `tests/platform/test_api_coverage.py` |
| 3 | Development sign-in untested; SMTP failure gave a 500 | Tests added; a refusing mail server answers 502 |
| 3 | HSTS set by both the API and Caddy | By design (defence in depth); the Caddyfile says so, and Caddy replaces rather than duplicates |
| 4 | `backup.sh` assumed `gsutil` | Checked before any work, with a clear message |

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
- Reviewer: four gpt-5.1 rounds of about 37,000–40,000 tokens in each, about USD 0.25 in all.
- No billx reads (stored readings were reused).
- Builder: Claude subscription.

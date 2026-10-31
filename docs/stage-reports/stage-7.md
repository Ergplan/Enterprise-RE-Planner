# Stage 7 report — journey, voice, live plan

Date: 1 Nov 2026 · Builder: Claude (subscription), cloud build workspace · Reviewer: gpt-5.1 (OpenAI), fresh context

## Built

**Journey.** The six steps are one flow:
- The left rail remembers the site (`?c=` → browser storage), so every step opens it.
- On a phone the rail becomes a scrolling step bar, and every journey page fits 390 px (checked on steps 1–6 and the live plan).
- Step 6 (`/plan/report`) lets a client build the standard plan, watch it settle, and share it — no analyst at any point.

**Live plan (`report/`, `/p/[token]`).** A share token opens the plan logged out. The page shows:
- the recommended option, with every number cited;
- the three options compared;
- each source's landed-cost waterfall, with an "Explain" button;
- the constraints that hold the answer where it is;
- what-if chips for PPA prices and contract demand, which re-dispatch and re-settle the plan;
- voice and text what-if;
- the documents appendix, with the stored copy and the regulator's link.

The jouleWise view adds every assumption, rule version, run pin, solver gap and the judge's margin. The API refuses it (403) to anyone but an analyst. The PDF comes from Playwright's Chromium printing `?print=1`: citations become numbered notes (document, page, quote) and the documents become an appendix.

**What-if (`report/whatif.py`).** Applies one change at a time: price, capacity, contract demand, a source switched off, or the rules in force on a date. The plan's sizes are held. The year is dispatched and settled hourly, and the judge settles it again. The one-sentence answer is filled in from the engines' numbers. Each what-if takes about 8 s on the NPCL site.

**Voice (`voice/tools.py`, `/voice/*`, `components/voice/VoicePanel.tsx`).**
- **Session:** the API mints an ephemeral OpenAI Realtime secret through `providers/`, with prompt `voice_v1` and the session's tools. The browser connects by WebRTC, and the model's function calls are relayed to `/voice/tool`.
- **Intake tools:** the SiteIntake setters — client, site, state, DISCOM, category, voltage, contract demand, pattern, weekly off, roof, land, months, check.
- **Plan tools:** price, capacity, contract demand, source on or off, rules date, reset.
- **Text chat (`/chat`)** runs the same tools server-side.
- The prompt forbids computing, saying a number no tool returned, or stating a regulation.

**Explanations (`report/explain.py`).** Two to four sentences drafted from the SourcedValues only (prompt `explain_v1`), shown as "explanation" beside the numbers and cached per input.

**Tests.**
- Voice tools: schemas; a voice-only intake equals the typed `SiteIntake`; refusals; what-if accumulation.
- The Realtime session minted with the transport mocked (no network), plus one real call marked `external`.
- Live-plan API: a client builds the plan with nothing duplicated; a logged-out visitor reads `/p/{token}`; the jouleWise view is refused to clients; what-if; PDF endpoint; explanation drafted once and cached; voice session and plan tool; text chat with the same tools.
- Report units and web unit tests.
- The Playwright end-to-end (`tools/dev/e2e-journey.sh`) on two real bills (NPCL July–August, MSEDCL April 2026). It runs an isolated API, worker and Next, with a billx stub that answers with billx's stored readings. Each run goes from bill drop to a shared plan with no analyst; then a logged-out visitor opens the plan, the PDF is checked for every cited page and every document, and the jouleWise view is refused.

## Definition of done

| Check | State |
| --- | --- |
| The end-to-end passes on two real bills | Met: NPCL July–August and MSEDCL April 2026, 2 passed in 4 min 36 s. In each run a new client goes from bill drop to a shared plan in the browser with no analyst. The PDF carries every cited document and page. |
| A voice-only intake produces the same SiteIntake as the typed form | Met (`tests/voice/test_tools.py`) |
| `/p/{token}` works for a logged-out visitor | Met (API test and the browser end-to-end) |
| Reviewer clean | See below |

## Skipped, and why

- A live voice conversation was not tried end to end: this workspace has no microphone. Minting, the tool relay and the tools are all tested. First use with a microphone is on the Mac mini.
- Editable chips cover PPA prices and contract demand. Capex, CUF and the grid factor are listed in the jouleWise view but cannot yet be edited by the client.

## Deviations

These are dated in `docs/decisions.md` (1 Nov 2026, Stage 7):
- **OpenAI, not Anthropic, drafts explanations.** This conflicts with the stage prompt; the locked decision of 31 Oct wins.
- **"Rule version" becomes "rules in force on a date",** so clients only ever see approved rules.
- **What-if holds the plan's sizes.**
- **The PDF uses Playwright, not the Chrome command line.**
- **Clients can build the standard plan themselves.**
- **The end-to-end runs isolated, with a billx stub.**

## Reviewer findings

One round (`docs/stage-reports/stage-7-review.md`). Its four "code defects" are not changed, for these reasons:
- **Voice session and chat open without login.** By design until Stage 8 (rule 12: no login, roles or rate limits before Stage 8). Plan mode already needs a valid share token. Intake mode is open because the journey has no login yet. The cost exposure is a named gap fixed in Stage 8.
- **`/p/{token}` with an anonymous caller.** Already handled: an anonymous or client caller gets the client view, and `view=analyst` needs role analyst with a named actor (403 otherwise). Tests cover no headers, a client and an analyst.
- **The PDF URL test and the default `kind` field.** The reviewer itself says these are consistent; no defect.

Nothing else was raised: every new endpoint has a test, there are no writes to rules or runs without audit, and there are no model imports outside `providers/`.

## Open questions

1. Voice: is OpenAI's `marin` voice right for jouleWise? Should the voice also speak Hindi by default for UP clients?
2. Should a client be able to edit capex, CUF and the grid factor on the live plan, or only an analyst?
3. Should share links expire (for example after 90 days), or stay valid until withdrawn?

## Cost

No billx reads: the end-to-end uses stored readings. No app model calls in this stage; the Realtime and chat calls are mocked in the suite, and the one real Realtime call is marked external and was not run. Reviewer: one gpt-5.1 call, about 60,000 tokens in, about USD 0.10. Builder: Claude subscription.

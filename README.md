# ergPLAN — Enterprise RE Planner

jouleWise | ergPLAN sizes renewable energy for industrial consumers in India: from a dropped electricity bill (read by billx) it rebuilds today's cost under the DISCOM tariff, computes the landed cost of every green source at the meter under the state's open-access, banking and settlement rules, and optimises the mix (rooftop, BESS, open-access solar/wind/BESS, pumped storage, IEX) against grid and captive thermal power. Every number carries its regulation, page and a link to the PDF.

## How this repository is built

The build is driven stage by stage by Claude Code from one document:

- `docs/MASTER-PROMPT.md` — operating rules, invariants, locked decisions, folder layout, the nine stage prompts, reference data and the definition of done.
- `CLAUDE.md` — sections 2–5 of the master prompt, verbatim, read in every session (`tools/dev/sync-claude-md.sh` regenerates it).
- `docs/development-plan.md` — the approved plan this prompt implements.

One stage per session, on the build machine inside `tmux`:

```
claude
> Run Stage 0 of docs/MASTER-PROMPT.md
```

Read the stage report in `docs/stage-reports/`, spot-check one invariant by hand, answer the open questions numbered in one message, then start the next stage.

## Layout

See section 5.1 of `docs/MASTER-PROMPT.md`. In short: `apps/web` (Next.js, ergOS Harmony), `apps/api` (FastAPI engines, Pyomo + HiGHS optimizer), `packages/rulebooks` (JSON Schemas, exported state rulebooks, golden tests), `packages/profiles` (load shapes, CUF curves), `docker/`, `tools/`, `docs/`.

## Rulebook schemas

`packages/rulebooks/schemas/` holds the seven rule families (`tod_slots`, `tariff_schedule`, `oa_charge`, `settlement`, `regulatory_limit`, `ists_waiver`, `net_metering`) and `source_ref.schema.json`. `packages/rulebooks/golden/up/example-settlement.yaml` shows a rule row as an analyst sees it. Values in that file are illustrative, not a state's actual rule.

## Run it on the Mac mini

```bash
git clone https://github.com/Ergplan/Enterprise-RE-Planner.git && cd Enterprise-RE-Planner
cp .env.example .env                       # add OPENAI_API_KEY and BILLX_TOKEN
docker compose -f docker/compose.yaml up --build   # billx builds from billx/ in this repo
# register the regulation corpus (PDFs from ~/Downloads/India_DISCOM_Tariff_Orders_Final_2026)
mkdir -p data/corpus && cp -R ~/Downloads/India_DISCOM_Tariff_Orders_Final_2026 data/corpus/
docker compose -f docker/compose.yaml exec api python -m ergplan.documents.corpus --root /data/corpus/India_DISCOM_Tariff_Orders_Final_2026
```

Web http://localhost:3000 · API http://localhost:8000/docs.

Without Docker: Postgres 16 on :5432 with role/db `ergplan`, then `cd apps/api && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/playwright install chromium && .venv/bin/alembic upgrade head && .venv/bin/uvicorn ergplan.platform.app:app`, the run worker `.venv/bin/python -m ergplan.platform.worker`, and `cd apps/web && pnpm install && pnpm dev`.

Checks: `python3 tools/watch/watch.py` (watch) or `--once`. Review: `tools/review/run.sh N`. 15-minute site solves: `cd apps/api && .venv/bin/pytest -m slow`. Browser end-to-end on real bills: `tools/dev/e2e-journey.sh`.

## Status

Stages 0–6 done; each has a report in `docs/stage-reports/`. The journey runs from a dropped bill to a shared live plan (`/p/{token}`) with voice what-if; every client-visible number cites the order page it comes from.

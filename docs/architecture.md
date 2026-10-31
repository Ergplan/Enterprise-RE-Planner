# ergPLAN architecture

Living document. Updated in the same commit as any code that changes it (rule 14). Stage 0 fills the first real content.

## Components

Web (Next.js, ergOS Harmony) → API (FastAPI) → engines (`engine/`, `settlement/`, `optimizer/`, pure Python) → PostgreSQL (rulebook versions, price series, clients, bills, profiles, runs, audit). External feeds: billx sidecar (bills), OpenAI Realtime (voice), IEX CSV uploads (prices), regulation PDFs read through `providers/` into draft rules.

## Data model

| Table | Writer | Audited by | Since stage |
| --- | --- | --- | --- |
| source_documents | documents.service | — | 0 |
| model_calls | providers | — | 0 |

## Critical path

bill → `intake.site_intake.build()` → `engine.tariff_eval.replay()` → `engine.landed_cost.evaluate()` → `settlement.simulate()` → `optimizer.solve()` → `optimizer.resettle()` → `report.plan.build()` (functions are created from Stage 2 onward).

## API surface

Stage 0: `GET /health`, `POST /documents`, `GET /documents/{id}`, `GET /documents/{id}/pages/{n}.png`.

## Deployment

Docker Compose: web, api, worker, postgres, billx, caddy. Laptop to Stage 4; Google Cloud VM (asia-south2) from Stage 5.

## What changed

- Stage 0: (pending)

# Known gaps

What is not yet right, and the stage that fixes it.

| Gap | Fixed in |
| --- | --- |
| `docker/compose.yaml` has not been run (no Docker daemon in the build workspace); first run happens on the Mac mini | Before Stage 5 |
| The independent reviewer is a tool script that imports `openai` directly (outside `ergplan/providers`); it is not app code and logs no `model_calls` row | By design |
| Only 5 of the 19 indexed orders are in the build workspace (UP ×2, MSEDCL ×3); the rest are on the Mac mini and register with the same command | Stage 8 |
| `MSEDCL MYT order` has no schedule page range in the index notes; its schedule pages are found during Stage 1 | Stage 1 |
| Two real anonymised bills per DISCOM needed in `data/bills/` | Stage 2 |
| IEX CSV samples per segment needed in `data/iex/` | Stage 2 |
| Hand-built landed-cost spreadsheet for six test consumers needed as `tests/fixtures/landed_cost_<state>.csv` | Stage 4 |
| A year of real OA settlement statements (anonymised) needed in `data/settlements/` | Stage 5 |

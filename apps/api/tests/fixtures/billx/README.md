# billx contract fixtures

Copied from billx `contract/examples/esgos-1.1` (engine 0.2.1, contract 1.1), synthetic bills only:

- `pvvnl_passed.json`, `pvvnl_synth.pdf` — `route-cloud-model-passed-pvvnl` (response and its PDF).
- `avvnl_flagged.json` — `printed-inconsistency` (passed with a flag).
- `pvvnl_needs_review.json` — `pvvnl_passed.json` with the bill set to `needs_review`, `energy.kwh`
  disputed, `demand.max_kva` and the first ToD slot unverified (made here, for the confirmation round trip).

Real bills never enter git (they live in the gitignored `data/bills/`).

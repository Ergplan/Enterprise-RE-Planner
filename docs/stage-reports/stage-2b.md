# Stage 2b report: generic gas reading

14 Oct 2026, on branch `stage-3` (2b and 3 share it; both start from `main` at
`stage-3-start`).

## Done-when status

| Item | Status |
| --- | --- |
| Every synthetic gas bill passes or is refused for a stated reason | **Yes**: both gas layouts' digital PDFs pass (text layer and OCR agree on every gas field; GG02 to GG05 give arithmetic); the photo variants are refused honestly without a model (`model_not_allowed`, or `unreadable` with `no_model_configured` when cloud use is allowed) |
| A gas bill never returns `not_a_bill` | **Yes**: the gate's gas signals (SCM, MMBtu, GCV, the supplier's name) classify both layouts as `gas_bill`; the pipeline test asserts it |
| Every GG planted misread is caught | **Yes**: GG02, GG03, GG04 and GG05 variants for both layouts, each reported `fail` by its check |
| Lint and tests green | **Yes** (the Stage 2 gate run) |

## What changed

Nothing new in this stage: every item of 2b landed with Stages 1 and 2 (the gas section of
the schema and GG01 to GG05 in Stage 1.4, the gas label rule in Stage 1.2, the gate's gas
signals in Stage 1.6, the gas truth files on the contract's paths and the planted GG
variants in Stage 1's synthetic package, the `gas-bill` example in Stage 2.4). The
`gas_not_yet_supported` note never existed: gas was read from Stage 1 (`docs/decisions.md`,
Stage 1). This report records the verification.

## Decision

**No 0.2 tag.** Release 0.1 already contains generic gas reading, so a 0.2 image would be
byte for byte the same; `docs/release-notes/0.1.md` says gas is included. Supplier profiles,
anchors and real gas sample bills stay in 4.2 Stage 10.4.

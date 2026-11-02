# Known gaps

Built in Stage 12 (section 11): row-level security and separate database roles,
append-only enforced by grants, HMAC-signed webhooks, KMS-encrypted saved passwords,
SPF/DKIM on email-in, OAuth 2.1 for MCP, rate limiting, WAF, container and dependency
scanning gates, penetration test, audit logs, customer-managed encryption, SOC 2 or ISO
27001, data-processing agreement templates, per-tenant BI access. mypy strict is Stage 11.

Stage 0:
- The identifier search reads files as bytes; it cannot see inside compressed PDF streams
  or images. Rule 10 is kept by never adding real bills at all; the search is the backstop.
- The amd64 image's identifier search scans the exported filesystem of one platform only.

## Branch readers-docling-llamaparse (1 Nov 2026)

- **The stored contract examples must be regenerated on the Mac before merging.** The 1.1
  examples gain `readings[]`, slot `open_access`/`net` and kVAh `energy.tod[]` items, so
  `contract/examples/` changes. They are written by `billx examples --synthetic out/synth`
  and compared with PaddleOCR's regions; on linux/amd64 (RapidOCR) the stored examples never
  match, on `main` as well, so this branch was built on linux and could not regenerate them.
  Until then `test_contract_examples` (marked `ocr`) fails on this branch on the Mac.
- **Live Docling and LlamaParse runs** are measured on ergPLAN's server (the keys and the
  docling service live there); `billx eval` on the golden set with both readers is the next
  measurement on the Mac.

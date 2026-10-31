# Decisions log

Dated entries. Every deviation from `docs/MASTER-PROMPT.md` is one.

## 2026-10-31 — Plan approved, repository seeded

- Product name ergPLAN under jouleWise; a separate product, not part of House of Rama.
- Every client-visible number carries regulation, page and a link opening the stored PDF at that page (invariant 1).
- First states: Uttar Pradesh (NPCL, PVVNL) and Maharashtra (MSEDCL). Then Karnataka, Gujarat, Rajasthan, Tamil Nadu, Telangana, Andhra Pradesh, Punjab, Haryana at Stage 8.
- Most clients have only bills: profile synthesis from 12 bills is a Stage 2 deliverable.
- IEX prices come from CSVs uploaded by jouleWise in the application.
- The regulation reader (tariff orders → draft rule rows with citations) is built in Stage 1, not later.
- Deliverable is a live shareable plan link with voice what-if and a jouleWise analyst view; PDF export of the same page.
- Thermal: captive coal and gas with waste heat as must-run; station fixed cost treated as sunk.
- Build machine: laptop Compose to Stage 4, then a Google Cloud VM in asia-south2.
- Stack and tooling as section 4 of the master prompt.

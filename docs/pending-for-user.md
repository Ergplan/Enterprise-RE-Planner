# Pending for the team

**Status on 27 Oct 2026** (`main` carries release 0.2.1, `docs/release-notes/0.2.1.md`): 48
real bills confirmed in the studio; the engine reads digital PDFs, scans and photos with both
models, and open-access bills end to end. What unblocks the most now: item 9 (GitLab runners,
which build the image) and item 11 (esgOS's registry).

What only a person can give. Nothing here blocks a session (rule 11); each item says what
waits on it. Steps for the Mac are in the Stage 0 report.

## Documents
1. ~~"billx Developer Guide: super billx" (version 2)~~: **supplied 12 Oct**, saved as
   `docs/developer-guide.md` and `contract/esgos-1.0/contract.md` (Stage 0.6).
2. **The original esgOS change list of 11 Oct 2026.** The file supplied on 12 Oct is a
   rebuild from the build prompt's summary (its own note says so) and is saved as
   `docs/esgos-changes-2026-10-11.md`. Its numbering disagrees with the build prompt's in one
   place (unverified layouts are its item 5; section 12.4 calls them "change 4"). If the
   original exists, send it; it replaces the file. *Waits on it:* nothing; decisions.md uses
   the rebuild's numbers.
3. **The terms text** (a paragraph is enough; counsel's version in Stage 12). By day 2.

## The Mac (needs an admin, or the person at the Mac)
4. FileVault on; system sleep off and "start up automatically after a power failure" on.
5. Homebrew, then `gh`, `tmux`, `tesseract`, `cloudflared` (this account has no admin rights).
6. The Claude Code command-line tool on PATH (`claude`), for `tools/mac/session.sh`.
7. Docker Desktop: at least 8 CPUs (has 14) and half the Mac's memory, 24 GB (has about 8 GB).
8. An external drive, mounted, and its path in `.env` as `BILLX_MIRROR_VOLUME`; then
   `tools/mac/install-jobs.sh` activates the nightly mirror.

## Accounts and access
9. **GitLab** (`icac1/ocr-bill-extraction`, set up 12 Oct): enable shared runners for the
   project and add the masked CI variable `CLIENT_IDENTIFIERS` (the same list as
   `~/billx-data/client-identifiers.txt`). *Waits on it:* CI runs, the images in the GitLab
   registry (Stage 2).
10. Read access for the agent to `git@github.com:Ergplan/esgOS.git`. *Waits on it:* the
    exact `esgos` field set (day 1, session C).
11. From esgOS: the registry image path (CI variable `ESGOS_REGISTRY`) and a
    service-account key for project `esgos-510707` (`ESGOS_REGISTRY_KEY`). *Waits on it:*
    the copy of `billx:0.1` to esgOS's registry.
12. A Cloudflare account with a domain and a tunnel token (`CLOUDFLARE_TUNNEL_TOKEN`), or
    Tailscale. *Waits on it:* staging (day 10).
13. Keys in `~/billx/.env`: `BILLX_OPENAI_API_KEY`, `BILLX_ANTHROPIC_API_KEY`,
    `ANTHROPIC_CONSOLE_KEY`, later `OPENAI_BUILD_REVIEW_KEY` (Stage 11) and
    `LLAMA_CLOUD_API_KEY` (Stage 9), each with a monthly budget.

## Bills
14. **The sample set: 10 confirmed AVVNL and 10 confirmed PVVNL bills**. The survey of 14 Oct
    (`docs/accuracy/2026-10-14-unconfirmed-survey.md`) shows the engine identifies the discom
    on 47 of the 65 files and reads some fields locally, but no real layout verifies without a
    model or a profile: confirming these bills is what makes the first profiles possible. (6 digital PDFs, 2
    scans, 2 phone photos each), confirmed in the studio. Supplied so far (12 Oct): AVVNL 6
    (all scans, of one account); PVVNL 16 (4 digital, 11 scans, 1 photo). Still needed for
    the 6/2/2 mix: AVVNL 6 digital PDFs and 2 phone photos (at least 4 more bills in all);
    PVVNL 2 more digital PDFs and 1 more phone photo.
    The other 39 files (MVVNL 16, MSEDCL 6, GESCOM 4, APCPDCL 3, NPCL 3, PSPCL 3, TANGEDCO 2,
    DVVNL 1, TGSPDCL 1) wait for Stage 10.
15. Client identifiers: consumer names and the account numbers printed on scans and photos,
    added to `~/billx-data/client-identifiers.txt` (a draft is there) and to the CI secret.

## Later (dates from section 14)
16. By day 7: the discoms of esgOS's first clients' plants (sets O4), the CRM webhook
    (`LEADS_WEBHOOK_URL`) and `LEADS_EMAIL`, and esgOS's agreement to consume `accepted`.
17. For esgOS: `schema_version` reports 2.0 after Stage 1 while contract 1.0's example
    shows "1.0" (6.2).
18. For Joulewise and esgOS: **`profile.status` values.** Contract 1.0 (section 5.2) gives
    `final`, `draft` or `none` on every bill; build prompt 6.2 gives `verified`, `draft` or
    `none` and only from contract 1.1. Default (decisions.md, Stage 0.6 and 0.7): the esgOS
    modes keep 1.0's `final` and always send `profile`; only `full` mode says `verified`.
    *Waits on it:* nothing until Stage 2.
19. **Studio confirmations made before Stage 1.1** cover the provisional field list, not
    contract 1.0's (decisions.md). They are kept and mapped; the fields the contract adds
    (meter number, tariff category, bill date, readings, TOD, power factor, net metering,
    energy and demand charges) will need a second, shorter pass per bill after Stage 1.1.

## From the 27 Oct review (release 0.2)
20. ~~**Net payable on open-access bills.**~~ **Answered 27 Oct: after the due-date
    rebate, on every bill** (release 0.2.1, decisions.md). The six PVVNL monthly bills
    confirmed with 'Payable Amount' were corrected the same day to the printed 'Payable by
    Due date', with the printed 'Due Date Rebate (₹)' (corrections in the manifest).
24. ~~One PVVNL scan was confirmed with an amount in `period.bill_month`~~: **fixed by the
    team in the studio, 27 Oct.**
21. Two PVVNL adjustment bills were confirmed with `demand.max_kva` "not printed" while the
    bill prints 'Actual MD (KVA)', confirmed on the others of the layout: recheck in the studio.
22. MSEDCL open-access bills: `energy.kvah` is now the total consumption before the
    open-access set-off (decisions.md, 26 Oct); recheck the earlier confirmations.
23. Optional: measure 0.2 on all 48 confirmed bills (`billx eval --golden
    --allow-cloud-model`, about $19 at placeholder prices).

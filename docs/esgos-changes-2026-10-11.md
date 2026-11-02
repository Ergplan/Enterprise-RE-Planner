# esgOS change list, 11 Oct 2026 (from Joulewise)

**Note:** this file was rebuilt from the summary in build prompt 4.2 (its header and its answered decisions O10, O16, O17, O20, O21). If the team has the original change list, replace this file with it.

Each item overrides anything in build prompt 4.1 that conflicts, and is not reopened.

1. **First customer.** esgOS (`Ergplan/esgOS`) is billx's first customer and goes live within days.
2. **Model providers.** esgOS accepts OpenAI and Anthropic as configured providers for bill reading (O17).
3. **Contract 1.1.** esgOS accepts contract 1.1. It is written and served, not proposed (sections 6.1 and 6.5).
4. **How esgOS calls billx.** It calls the hosted service on the `esgos` product key, in `esgos-1.1` mode with permanent storage. Until hosting is live, esgOS runs the embedded image from its own registry. The switch is a URL and token change, and esgOS then resubmits every stored bill once (O21).
5. **Unverified layouts pass for esgOS.** The `esgos` key and the embedded image pass any layout under the 5.2 rules, with `profile.status` on every bill saying the layout's state (O10).
6. **What esgOS consumes.** The bill's status is `passed`. See the build prompt's section 6.5, item 7, for the follow-up on `accepted`.
7. **Gas.** Gas bills are read generically right after Stage 2.
8. **Insights and leads.** esgOS gets insights on every passed bill and owns its own leads.
9. **Terms.** esgOS's sign-up terms include billx's. The `esgos` tenant's acceptance at key issue covers its users (O16).
10. **Local OCR timing.** Stage 4, as planned (O20).
11. **esgOS's repository.** billx never creates branches in `Ergplan/esgOS`.

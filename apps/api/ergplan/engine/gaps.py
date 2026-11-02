"""Named rule gaps (master prompt Stage 3): a bill line the engine does not compute yet is
"explained" only when one of these covers it. Every id here is listed in docs/known-gaps.md
(a test checks), with the stage or document that closes it."""

from __future__ import annotations

GAPS: dict[str, str] = {
    "fppca_monthly": (
        "Fuel and power purchase cost adjustment (FAC/FPPAS) is notified monthly by the "
        "DISCOM, not in the tariff order; no monthly FPPCA rulebook yet"
    ),
    "electricity_duty": (
        "Electricity duty is levied under the state's Electricity Duty Act, not the "
        "tariff order; the Acts are not in the corpus yet"
    ),
    "tax_on_sale": (
        "Maharashtra tax on sale of electricity (paise per unit) is a state levy outside the tariff order"
    ),
    "load_factor_incentive": (
        "Load-factor incentive bands are in the tariff order but not yet read into the rulebook"
    ),
    "prompt_payment_rebate": (
        "Prompt-payment rebate terms are in the order's general conditions but not yet read"
    ),
    "bulk_consumption_rebate": ("Bulk / incremental consumption rebates are not yet read into the rulebook"),
    "state_subsidy": (
        "State industrial subsidies (e.g. Maharashtra textile, region-based) are "
        "government schemes outside the tariff order"
    ),
    "regulatory_discount": (
        "A regulatory discount or surplus pass-through ordered for the period is not in the rulebook"
    ),
    "settlement_rule": (
        "No approved settlement rule for this source's ownership in the state: energy is set off "
        "in the 15-minute block it arrives in, with no banking, until the regulation is read"
    ),
    "tod_split_unknown": (
        "The bill does not give energy by ToD slot, so the ToD adjustment cannot be recomputed"
    ),
    "billing_demand_rule": (
        "The schedule row does not state the billing-demand floor or proration the DISCOM applied"
    ),
    "demand_proration": (
        "The DISCOM prorates the monthly demand charge by the days in the billing period "
        "(days / (365/12)); the order's provision for it is not yet located"
    ),
    "ists_charges": (
        "ISTS transmission charges (CERC Sharing Regulations) are not in the corpus; ISTS "
        "sources carry no ISTS charge line yet"
    ),
    "ists_waiver": (
        "The CERC ISTS charge and loss waiver schedule by commissioning date is not in the corpus"
    ),
    "oa_wheeling": ("No approved open-access wheeling charge for this DISCOM and voltage"),
    "oa_losses": ("No approved open-access distribution (wheeling) loss for this DISCOM and voltage"),
    "oa_css": ("No approved cross-subsidy surcharge for this category and voltage"),
    "oa_additional_surcharge": ("No approved additional surcharge for this DISCOM"),
    "iex_fees": ("IEX transaction fees and trader margin (CERC) are not in the corpus"),
    "scheduled_energy": (
        "A capacity charge needs the source's capacity and CUF to spread it over scheduled energy"
    ),
    "green_tariff": ("The DISCOM's green-tariff premium is not in the approved tariff schedule"),
    "iex_prices": ("No IEX prices are loaded for this market segment"),
    "regulatory_limits": (
        "No regulatory-limit rulebook (RE cap, storage mandate, minimum OA size and contract "
        "demand) is approved for this jurisdiction"
    ),
    "tariff_period": (
        "No approved tariff schedule covers the bill's date: the tariff order in force then "
        "(e.g. UPERC FY 2025-26) is not in the corpus"
    ),
    "unmodelled_line": (
        "A bill line ergPLAN does not model (miscellaneous charge or credit printed on the bill)"
    ),
}

# Bill labels (upper-cased substrings) that identify a gap when billx codes the line `other`.
LABEL_GAPS: list[tuple[str, str]] = [
    ("FUEL", "fppca_monthly"),
    ("FPPA", "fppca_monthly"),
    ("FAC", "fppca_monthly"),
    ("TAX ON SALE", "tax_on_sale"),
    ("REGULATORY DISCOUNT", "regulatory_discount"),
    ("BULK CONSUMPTION", "bulk_consumption_rebate"),
    ("INCREMENTAL CONSUM", "bulk_consumption_rebate"),
    ("SUBSIDY", "state_subsidy"),
]

CODE_GAPS: dict[str, str] = {
    "fppca": "fppca_monthly",
    "electricity_duty": "electricity_duty",
    "load_factor_rebate": "load_factor_incentive",
    "prompt_payment_rebate": "prompt_payment_rebate",
    "subsidy": "state_subsidy",
    "other_rebate": "bulk_consumption_rebate",
}

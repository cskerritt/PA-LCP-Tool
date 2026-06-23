"""Narrative content embedded in the workbook (Methodology and Data Sources).

This text is paraphrased from public professional standards and case law; it is
intended as a transparent statement of method, not legal advice.  Edit freely to
match the specific engagement -- nothing here substitutes for the planner's own
documented methodology section.
"""

from __future__ import annotations

# (heading, [paragraphs]) -- rendered on the "Methodology & Standards" tab.
METHODOLOGY_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "1. Definition and Governing Standards",
        [
            "A life care plan is a dynamic document based on published standards of practice, "
            "comprehensive assessment, data analysis, and research, providing an organized plan "
            "for an individual's current and future care needs and associated costs.",
            "This projection is prepared consistent with the International Academy of Life Care "
            "Planners (IALCP) Standards of Practice (4th ed., 2022) and applicable Consensus and "
            "Majority Statements adopted at the Life Care Planning Summits, which function as the "
            "field's peer-reviewed best practices.",
        ],
    ),
    (
        "2. Cost Research Methodology (UCR)",
        [
            "Costs are stated at Usual, Customary, and Reasonable (UCR) value — the amount usually "
            "charged for a service by similarly-trained providers in the relevant geographic area "
            "— rather than at billed-charge extremes or government-reimbursement floors.",
            "Consistent with Consensus Statements 69, 71, and 85, pricing is verifiable, "
            "geographically specific to the claimant's locality where data permit, and drawn from "
            "documented sources. A single reasonable-value percentile is applied consistently "
            "across sources to avoid selective ('cherry-picked') pricing.",
            "Where the jurisdiction's collateral-source rule controls the billed-versus-paid "
            "question, the chosen basis is stated on the Assumptions tab; future insurance and "
            "Affordable Care Act coverage are generally treated as speculative and excluded.",
        ],
    ),
    (
        "3. Economic Projection: Growth and Present Value",
        [
            "Each item's current cost is grown to the year the cost is incurred using a published "
            "medical-price series appropriate to that item class (e.g., medical-care services, "
            "prescription drugs, durable medical equipment, facility services, or wage-based "
            "attendant care), then discounted to present value at the cited discount rate.",
            "Growth and discounting use a single, internally consistent cash-flow timing "
            "convention (documented on the Assumptions tab), so the present-value figure is fully "
            "reproducible from the stated inputs.",
            "The duration of care is governed by life expectancy taken from a published life table "
            "or, where the injury affects lifespan, from a qualified medical/mortality opinion. "
            "The planner does not independently adjust life expectancy.",
        ],
    ),
    (
        "4. Medical Foundation",
        [
            "Every recommended good or service is tied to a treating-provider recommendation or "
            "the medical record (Consensus Statement 64; IALCP Standard 3.3). A non-physician "
            "planner does not supply independent medical opinions.",
            "This requirement reflects the controlling case law: plans built on templates or the "
            "planner's own unsupported beliefs have been excluded (Gunn v. Atchison), as has care "
            "not recommended by the treating providers (Anderson-Moody v. Wilson). The Medical "
            "Foundation tab documents the basis for each item and flags any gaps.",
        ],
    ),
    (
        "5. Transparency and Reproducibility",
        [
            "Consistent methodology is applied across similar items so results are reproducible "
            "(Consensus Statement 63). All cost sources, percentiles, retrieval dates, growth "
            "rates, the discount rate, and life expectancy are disclosed on the Assumptions & "
            "Rates and Data Sources tabs.",
            "The plan is structured to support the six peer-review domains: jurisdiction/system "
            "rules, best practices, ethical guidelines, standards of practice, transparency, and "
            "findings/conclusions.",
        ],
    ),
    (
        "6. Admissibility under Daubert / FRE 702",
        [
            "Tested methodology: the assess–consult–cost process is standard in the field. "
            "Peer review and publication: the IALCP Standards and Consensus Statements supply the "
            "supporting literature. Known standards and general acceptance: UCR pricing, published "
            "medical-inflation indices, and present-value discounting are generally accepted "
            "methods in forensic economics and life care planning.",
            "The Validation tab records a pre-flight check against the most common grounds for "
            "exclusion (missing medical foundation, inconsistent percentile selection, un-sourced "
            "or undated pricing, and speculative durations).",
        ],
    ),
    (
        "7. Scope and Limitations",
        [
            "This workbook quantifies the cost of care items provided as inputs; it does not "
            "establish medical necessity, causation, or life expectancy, which rest on the "
            "clinical record and qualified expert opinion.",
            "Figures are only as current as the cited retrieval dates; rates should be refreshed "
            "to the report date before reliance. Placeholder rates are flagged on the Validation "
            "tab until replaced with cited figures.",
        ],
    ),
]


# name -> {"desc": ..., "url": ...} -- rendered on the "Data Sources" tab and
# used to attach a citation URL to sources actually used in a plan.
SOURCE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "Medical Fees in the United States (Context4/PMIC)": {
        "desc": "UCR fee-percentile database for physician and facility services; "
                "apply a geographic adjustment factor (GAF) for ZIP specificity.",
        "url": "https://www.pmiconline.com/",
    },
    "Yale Wasserman": {
        "desc": "Commercial physician fee analyzer providing charge estimates by "
                "CPT code; useful as a secondary cross-check.",
        "url": "",
    },
    "VA Reasonable Charges": {
        "desc": "Charge tables published by the U.S. Department of Veterans Affairs "
                "(community-care reasonable charges); useful as a published fallback.",
        "url": "https://www.va.gov/COMMUNITYCARE/revenue_ops/Reasonable_Charges.asp",
    },
    "CMS DMEPOS Fee Schedule": {
        "desc": "Medicare fee schedule for durable medical equipment, prosthetics, "
                "orthotics, and supplies; a conservative allowed-amount benchmark.",
        "url": "https://www.cms.gov/medicare/payment/fee-schedules/dmepos-fee-schedule",
    },
    "Genworth Cost of Care Survey": {
        "desc": "Annual survey of median private-pay long-term-care rates "
                "(home health aide, assisted living, nursing facility); filter by region.",
        "url": "https://www.genworth.com/aging-and-you/finances/cost-of-care.html",
    },
    "American Hospital Directory (AHD)": {
        "desc": "Hospital-specific utilization and charge data; used for "
                "facility-specific pricing where a local hospital is likely.",
        "url": "https://www.ahd.com/",
    },
    "GoodRx": {
        "desc": "Retail prescription cash-price tracker; document pharmacy, dosage, "
                "and retrieval date due to price volatility.",
        "url": "https://www.goodrx.com/",
    },
    "FAIR Health": {
        "desc": "Independent UCR benchmarking database from billed-charge data, "
                "reported by geozip.",
        "url": "https://www.fairhealth.org/",
    },
    "CDC/NCHS United States Life Tables": {
        "desc": "National period life tables used for unimpaired life expectancy.",
        "url": "https://www.cdc.gov/nchs/products/life_tables.htm",
    },
    "BLS CPI-U, Medical Care": {
        "desc": "Consumer Price Index medical-care series used to source historical "
                "medical price growth.",
        "url": "https://www.bls.gov/cpi/",
    },
    "U.S. Treasury Constant Maturity (H.15)": {
        "desc": "Treasury yields used to source the discount rate as of the report date.",
        "url": "https://www.federalreserve.gov/releases/h15/",
    },
}

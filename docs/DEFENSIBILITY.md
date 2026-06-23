# Defensibility: Daubert / FRE 702 and peer-review mapping

This tool is organized so that its output can withstand a *Daubert* challenge and
satisfy Federal Rule of Evidence 702. This document maps the tool's features to
(a) the *Daubert* reliability factors, (b) the life-care-plan **Consensus and
Majority Statements**, (c) the six **peer-review domains**, and (d) the recurring
grounds for exclusion in the case law — and shows where each is enforced.

> Nothing here is legal advice. Admissibility is decided by the court on the full
> record; the tool's job is to make the methodology transparent, consistent, and
> reproducible, and to surface defects before they reach a deposition.

## A. Daubert reliability factors

| Factor | How the tool supports it |
| --- | --- |
| Tested / testable method | The projection is a deterministic function of disclosed inputs; the formulas are printed on the Assumptions tab and any figure can be reproduced by hand. |
| Known/standard technique | UCR pricing, published medical-inflation indices, and present-value discounting are standard forensic-economic methods. |
| Peer review & publication | The Methodology tab cites the IALCP Standards (4th ed., 2022) and the Consensus/Majority Statements that function as the field's peer-reviewed best practices. |
| Standards controlling operation | A single reasonable-value percentile and one timing convention are applied consistently; deviations are flagged. |
| General acceptance | The data-source hierarchy and consistent-methodology requirement track generally-accepted practice. |

## B. Consensus / Majority Statements

| Statement | Mandate | Where enforced |
| --- | --- | --- |
| 63 | Consistent methodology across similar items (reproducibility) | One engine, one timing convention, deterministic output |
| 64 | Rely on medical/allied-health opinions; no independent medical speculation | `medical_foundation` field; Medical Foundation tab; validator warning |
| 69 | Specific cost-research protocols (no arbitrary pricing) | Each item records source, code, percentile, retrieval date |
| 71 | Local vs. national resource protocols (geographic specificity) | `geographic_basis`; validator note when absent |
| 85 | Verifiable, geographically specific, market-rate costs | Pricing schema + provenance on the Data Sources tab |

## C. Six peer-review domains

The tool organizes findings under six peer-review domains drawn from the
life-care-plan peer-review literature and consistent with the IALCP Standards
and Summit Consensus/Majority Statements. The validator tags each finding with
the domain it implicates:

1. **Jurisdiction/System Rules** — `collateral_source_note`, jurisdiction field.
2. **Best Practices** — geographic specificity, defined growth series.
3. **Ethical Guidelines** — consistent percentile (no cherry-picking).
4. **Standards of Practice** — IALCP-aligned structure and disclosures.
5. **Transparency** — sourced/dated rates and prices; reproducible formulas.
6. **Findings/Conclusions** — positive durations, resolved costs, valid timing.

## D. Grounds for exclusion the validator checks

The published critiques of excluded life care plans are consistent. The
**Validation** tab and `palcp validate` check for the same defects *before* a
workbook is built:

| Exclusion ground | Basis | Validator check |
| --- | --- | --- |
| Care not founded in the treating record; template/"own beliefs" plans | Medical-foundation case law (e.g. *Anderson-Moody v. Wilson*, Fla. 1st DCA 2023, disallowing a life-care planner's projection of care not recommended by a treating physician or medical expert); practitioner case reviews | Warns on any item lacking `medical_foundation` |
| Inconsistent / cherry-picked cost percentiles | UCR best-practice critiques | Warns when one source is used at multiple percentiles; notes deviations from the percentile policy |
| Un-sourced or undated pricing | Transparency requirement | Warns on missing pricing source or retrieval date |
| Speculative / unspecified durations and frequencies | *Daubert* reliability / costing best practices | Warns on items with no timing pattern; errors on inverted age bands; warns on one-time events outside the life window; warns on non-integer replacement cadences |
| Un-sourced economic assumptions | *Daubert* reliability | Warns on un-sourced/placeholder life expectancy, discount rate, or growth rate (a source beginning with `PLACEHOLDER` is treated as missing) |

> **Verify your citations.** The named case above is provided as illustrative
> authority; controlling law varies by jurisdiction and changes over time.
> Counsel and the testifying expert are responsible for citing the governing
> authority in the report. The generated workbook deliberately states these
> grounds as general principles rather than embedding specific case citations.

Severity levels:
- **ERROR** — would make a figure meaningless (zero/unresolved cost, unknown
  growth key, inverted age band). `palcp build` refuses unless `--force`.
- **WARN** — a likely defensibility gap to address or document.
- **INFO** — a methodological note (e.g. percentile deviation, real-basis pairing).

## E. What the tool does **not** decide

Medical necessity, causation, and life expectancy are clinical/expert
determinations and are inputs to the tool, not outputs of it. The tool quantifies
the cost of the care it is given, on disclosed assumptions, in a reproducible way.

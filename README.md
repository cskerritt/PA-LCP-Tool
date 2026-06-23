# PA-LCP-Tool

A transparent, reproducible **Life Care Plan cost-projection engine** and
**court-ready Excel report generator**, built for admissibility under
*Daubert v. Merrell Dow Pharmaceuticals* and **Federal Rule of Evidence 702**.

Given a set of recommended care items and documented economic assumptions, the
tool produces a multi-tab Excel workbook that presents future medical-care costs
in three measures — **current (base-year) dollars**, **future (nominal) dollars**,
and **present value** — with every rate, source, percentile, and retrieval date
disclosed, and a built-in *Daubert pre-flight* that flags the defects courts most
often cite when excluding life care plans.

> **Phase 1 (this repository): the Python engine + CLI + Excel generator.**
> A web application (the project's connected Supabase stack) is planned as a
> follow-up that will wrap this engine — the engine is the Daubert-critical,
> reusable core and is intentionally UI-agnostic.

---

## What it produces

A single `.xlsx` workbook with ten tabs, each able to stand alone as an exhibit:

| Tab | Contents |
| --- | --- |
| **Cover** | Caption, claimant, evaluator, dates, headline totals, disclaimer |
| **Summary** | Totals by category in all three measures + key assumptions |
| **Current-Cost Tables** | Itemized current-dollar LCP tables (no growth/discount) |
| **PV Projection** | Itemized lifetime nominal & present value, with net discount rates |
| **Annual Schedule** | Year-by-year nominal cost by category, discount factor, PV, cumulative PV |
| **Assumptions & Rates** | Every rate, its basis/source/date, and the exact formulas used |
| **Data Sources** | Provenance of each pricing source actually used + standard source notes |
| **Methodology & Standards** | IALCP standards, consensus statements, *Daubert* factors |
| **Medical Foundation** | Per-item basis in the treating record (flags any gaps) |
| **Validation** | The Daubert pre-flight findings (errors / warnings / notes) |

The **current-cost** tables and the **growth + present-value** projection are
presented as **separate, clearly-labeled tabs** in the same workbook.

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

Requires Python ≥ 3.10. Runtime dependencies: `openpyxl`, `PyYAML`.

## Quick start

```bash
# 1. See a complete, working example (synthetic data):
palcp sample --out sample.xlsx

# 2. Scaffold blank input templates to edit:
palcp init --dir lcp_inputs

# 3. Build from your own inputs:
palcp build \
  --assumptions lcp_inputs/assumptions.yaml \
  --items       lcp_inputs/plan_items.csv \
  --pricing     va_reasonable_charges.xlsx:va_reasonable_charges \
  --out         life_care_plan.xlsx

# 4. Run only the Daubert pre-flight (no workbook):
palcp validate --assumptions lcp_inputs/assumptions.yaml --items lcp_inputs/plan_items.csv
```

`--pricing` accepts one or more files, each optionally tagged with a loader
preset as `path:preset` (presets: `va_reasonable_charges`, `cms_dmepos`, `mfus`).
Items with a code but no `unit_cost` are priced from these tables; items with a
direct `unit_cost` (e.g. a vendor survey) keep it.

## Library use

```python
from palcp import load_plan, project, validate_plan, save_workbook

plan   = load_plan("assumptions.yaml", "plan_items.csv")
report = validate_plan(plan)        # Daubert pre-flight
result = project(plan)              # the cost projection
save_workbook(result, report, "life_care_plan.xlsx")
```

---

## How the projection works (in one paragraph)

Each care item's current cost is grown to the year it is incurred using a
**published medical-price series** chosen for that item class (medical services,
prescription drugs, DME, facility, or wage-based attendant care), then
**discounted to present value** at a cited discount rate. Growth and discounting
use a single, consistent cash-flow **timing** convention (mid-year by default),
so the present value is exactly reproducible from the disclosed inputs. Life
expectancy sets the horizon; the final partial year is prorated. The full
formulas appear on the workbook's Assumptions tab and in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Defensibility

The tool is organized around the six life-care-plan peer-review domains and the
*Daubert* factors. The **Validation** tab/command checks for the specific
failures that recur in exclusion case law — missing medical foundation
(*Gunn v. Atchison*; *Anderson-Moody v. Wilson*), inconsistent ("cherry-picked")
cost percentiles, un-sourced or undated pricing, and speculative durations. See
[`docs/DEFENSIBILITY.md`](docs/DEFENSIBILITY.md).

## Bringing your own pricing data

The tool does **not** ship proprietary fee schedules. It defines a single
canonical pricing schema and flexible loaders so your **VA Reasonable Charges**,
MFUS/Context4, CMS DMEPOS, Genworth, or vendor-survey exports map in cleanly.
See [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md). The bundled sample uses
**synthetic, clearly-labeled** data only.

## Important limitations

- **Not legal or medical advice.** The tool quantifies costs from the inputs you
  provide; it does not establish medical necessity, causation, or life
  expectancy, which rest on the clinical record and qualified expert opinion.
- **Replace placeholder rates.** Built-in default growth/discount rates are
  tagged `PLACEHOLDER` and flagged by the validator until you substitute current,
  cited figures as of your report date.
- Figures are only as current as the cited retrieval dates.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Project layout

```
src/palcp/
  models.py            # dataclasses: Plan, CareItem, rates, life expectancy
  config.py            # load assumptions (YAML) + items (CSV/XLSX) -> Plan
  validate.py          # Daubert / FRE 702 pre-flight checks
  economics/           # projection engine, timing, life table
  pricing/             # canonical schema, vendor loaders, code resolution
  workbook/            # openpyxl styles, multi-tab builder, narrative content
  cli.py               # `palcp` command-line interface
  data/                # templates + synthetic sample inputs
docs/                  # METHODOLOGY, DATA_SCHEMA, DEFENSIBILITY
tests/                 # pytest suite
```

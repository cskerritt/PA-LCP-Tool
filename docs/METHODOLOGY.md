# Methodology

This document states the methodology the engine implements. It is written to be
quoted in a report's methodology section and defended on cross-examination. It is
a statement of method, not legal advice.

## 1. Measures produced

For every care item the engine computes three lifetime figures:

1. **Current cost** — the item's cost in base-year (today's) dollars, summed over
   every year it is active. No growth, no discounting. This is the classic life
   care plan "current cost" table and answers *"what would this care cost at
   today's prices?"*
2. **Future (nominal) cost** — the current cost grown to the year each cost is
   incurred, using the published medical-price series assigned to that item.
3. **Present value** — the nominal cost discounted back to the valuation
   (report) date at the cited discount rate.

The current-cost tables and the growth-plus-present-value projection are
presented on separate tabs of the same workbook.

## 2. Timing convention

Let `y = 0, 1, 2, …` index projection years (Year 1 is `y = 0`). The claimant's
age at the start of year `y` is `age_at_report + y`. A single **time exponent**
`m(y)` — the time in years from the valuation date to the assumed cash-flow date —
is used for **both** growth and discounting, so the two are perfectly consistent:

| `timing` | `m(y)` | interpretation |
| --- | --- | --- |
| `begin_year` | `y` | cash flows at the start of the year (annuity-due) |
| `mid_year` (default) | `y + 0.5` | cash flows at mid-year |
| `end_year` | `y + 1` | cash flows at year-end (ordinary annuity) |

The mid-year convention is the default because recurring care is spread through
the year; it is a standard, defensible choice in forensic economics. The
convention actually used is printed on the Assumptions tab.

## 3. Growth and present-value formulas

For an item with current annual cost `C(y)` in year `y`, growth rate `g`, and a
portfolio discount rate `d`:

```
nominal(y) = C(y) · (1 + g)^m(y)
pv(y)      = nominal(y) / (1 + d)^m(y)
           = C(y) / (1 + r)^m(y),   where  r = (1 + d)/(1 + g) − 1
```

`r` is the **net discount rate** for that item — reported per item on the PV
Projection tab and per series on the Assumptions tab. Because growth is
item-specific but discounting is uniform, the present value of an entire year
equals that year's total nominal cost times one discount factor `1 / (1+d)^m(y)`.

### Nominal vs. real basis

- **`basis: nominal`** — pair a nominal discount rate (e.g. a nominal Treasury
  yield) with nominal medical-price growth. This is the default and the most
  transparent for a fact-finder.
- **`basis: real`** — pair a real discount rate (e.g. a TIPS yield) with growth
  expressed as the medical *excess* over general inflation. The validator emits a
  note when `basis: real` is selected, because applying full nominal medical
  growth to a real discount rate overstates present value.

## 4. Duration of care (life expectancy)

Life expectancy sets the projection horizon. It is supplied as the number of
additional years (and its source). Per IALCP methodology and the controlling case
law, **the planner does not independently reduce life expectancy**: an unimpaired
figure comes from a published life table (e.g. CDC/NCHS *United States Life
Tables*); a reduced figure must come from a qualified medical or mortality
opinion. The optional `LifeTable` loader reads a published table you provide — it
ships **no** embedded mortality numbers, to keep transcription errors out of
evidence.

The final partial year of life expectancy is **prorated** by its fractional part
(e.g. 38.5 years = 38 full years weighted 1.0 plus a final year weighted 0.5).

## 5. Cost research (UCR)

Costs are stated at **Usual, Customary, and Reasonable (UCR)** value — the amount
usually charged for a service by similarly-trained providers in the relevant
geographic area — rather than at billed-charge extremes or government
reimbursement floors. Consistent with Consensus Statements 69, 71, and 85:

- pricing is **verifiable** (each item records its source, code, percentile, and
  retrieval/effective date);
- pricing is **geographically specific** to the claimant's locality where the
  data permit;
- a **single reasonable-value percentile** (default 80th) is applied
  **consistently** across sources — the validator flags any source used at more
  than one percentile to head off a cherry-picking critique.

A documented **hierarchy** of sources is supported (direct vendor survey →
geographically specific databases such as MFUS/Context4, FAIR Health, AHD →
published fallbacks such as VA Reasonable Charges and CMS DMEPOS). Items priced by
a direct survey carry their own `unit_cost`; items priced from a fee schedule are
resolved by code.

## 6. Medical foundation

Every item should tie to a treating-provider recommendation or the medical record
(`medical_foundation`). A non-physician planner does not supply independent
medical opinions. The Medical Foundation tab documents the basis for each item and
flags gaps; the rationale and case law are in [DEFENSIBILITY.md](DEFENSIBILITY.md).

## 7. Reproducibility

Given identical inputs, the engine produces identical output. All assumptions are
disclosed on the workbook tabs, and the formulas above are printed on the
Assumptions tab, so a reviewer can reproduce every figure by hand.

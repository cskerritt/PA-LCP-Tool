# Data schema

Three inputs drive the tool: **assumptions** (YAML), **care items** (CSV/XLSX),
and optional **pricing tables** (CSV/XLSX). Run `palcp init --dir lcp_inputs` to
get blank templates of each.

---

## 1. Assumptions (YAML)

See `src/palcp/data/templates/assumptions.template.yaml`. Top-level keys:

| Key | Meaning |
| --- | --- |
| `report_date`, `base_year` | Valuation date and first projection (calendar) year |
| `matter`, `jurisdiction` | Caption and court/evidentiary standard |
| `evaluator`, `evaluator_credentials` | Appear on the Cover tab |
| `percentile_policy` | Reasonable-value percentile applied consistently (default 80) |
| `collateral_source_note` | Billed-vs-paid / collateral-source treatment relied upon |
| `claimant` | `name, dob, sex, age_at_report, residence` |
| `life_expectancy` | `additional_years, source, citation_url, as_of, note` |
| `discount_rate` | `annual_rate, basis (nominal\|real), timing (begin_year\|mid_year\|end_year), source, citation_url, as_of` |
| `growth_rates` | Map of `key -> {label, annual_rate, source, citation_url, as_of}` |

Built-in growth keys (extend or rename freely): `medical_services`, `rx`, `dme`,
`facility`, `attendant_care_wage`, `general`. Each care item references one of
these via its `growth_key` column.

> Rates left empty (or carrying a `PLACEHOLDER` source) are flagged by the
> validator until you supply the cited figure used as of the report date.

---

## 2. Care items (CSV or XLSX)

One row per recommended good or service. Header row required; column order is
free (matched by name, case-insensitive). See
`src/palcp/data/templates/plan_items.template.csv`.

| Column | Type | Notes |
| --- | --- | --- |
| `category` | text | Grouping on every tab (e.g. "Physician Services") |
| `item` | text | Short name |
| `description` | text | Longer description |
| `code` | text | CPT / HCPCS / APC / MS-DRG (used for table pricing) |
| `code_type` | text | `CPT`, `HCPCS`, … |
| `pricing_source` | text | e.g. `MFUS 80th %ile`, `VA Reasonable Charges` |
| `percentile` | number | e.g. `80` |
| `geographic_basis` | text | ZIP / locality / GAF / national |
| `retrieval_date` | text | When the price was obtained / its effective date |
| `unit_cost` | number | Current $ for **one occurrence**. Leave `0` to price by `code` |
| `units_per_occurrence` | number | Default `1` |
| `frequency_per_year` | number | Recurring annual care (e.g. `2` = twice/yr) |
| `every_n_years` | number | Periodic replacement (e.g. wheelchair every `5`) |
| `one_time` | bool | `TRUE` for a single future event |
| `one_time_age` | number | Age at which the one-time event occurs |
| `start_age` | number | Care begins at this age (blank = at report age) |
| `end_age` | number | Care ends at this age, exclusive (blank = to terminal age) |
| `growth_key` | text | Which growth series applies (default `medical_services`) |
| `medical_foundation` | text | Citation to the treating record (e.g. "Dr. X, note 2/10/26") |
| `notes` | text | Free text |

**Choose exactly one timing pattern per item:** `frequency_per_year` *or*
`every_n_years` *or* `one_time` + `one_time_age`.

**Cost conventions**
- `unit_cost` is the cost of one occurrence; annual cost = `unit_cost ×
  units_per_occurrence × frequency_per_year`.
- For attendant care, enter the **annual** cost as `unit_cost` with
  `frequency_per_year = 1` (e.g. `$30/hr × 6 hr/day × 365`).
- Misaligned columns (a missing comma) are caught with an error naming the
  offending column and row number.

---

## 3. Pricing tables (CSV or XLSX) — optional

Used to price items by `code`. Canonical columns (case-insensitive):

```
source, code, code_type, description, amount, percentile,
geographic_area, effective_date, citation_url
```

Only `code` and `amount` are strictly required. For vendor exports with different
headers, use a **preset** or an explicit `column_map`:

```python
from palcp.pricing import load_pricing
table = load_pricing("va_export.xlsx", preset="va_reasonable_charges")
table = load_pricing("vendor.csv", column_map={"code": "CPT/HCPCS", "amount": "Charge"})
```

Built-in presets: `va_reasonable_charges`, `cms_dmepos`, `mfus`. On the CLI:

```bash
palcp build ... --pricing va_export.xlsx:va_reasonable_charges dmepos.csv:cms_dmepos
```

### Resolution order

For an item with a `code` but no direct `unit_cost`, the best record is chosen by:
matching `pricing_source` → matching `percentile` → matching `geographic_basis` →
having a defined percentile → highest amount. The chosen source, percentile,
geography, and effective date are back-filled onto the item for the audit trail.

---

## 4. Life table (CSV) — optional

For looking up unimpaired life expectancy by age/sex from a published table you
provide. Columns: `age, sex, ex, source, citation_url, as_of` where `sex` is
`total | male | female` and `ex` is remaining-life expectancy in years. No
mortality data is bundled.

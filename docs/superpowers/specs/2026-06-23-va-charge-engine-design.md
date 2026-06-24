# VA charge engine (localized, all codes) — design

**Date:** 2026-06-23
**Status:** Approved (methodology + architecture)
**Goal:** Cost out **any** CPT/HCPCS code from the full VA Reasonable Charges
v5.26 tables, **localized to the case's 3-digit ZIP**, computed on demand.

## Source data

`~/Downloads/VA UCR TABLES/` — 19 official v5.26 workbooks:

| Kind | Tables | Charge = |
| --- | --- | --- |
| **Direct charge** | F (Outpatient Facility), K (DME), C (Observation hourly), D (Partial Hosp.), E (Ambulance), I (Dental), A (Inpatient MS-DRG), B (SNF) | `Charge × GAAF[zip3]` |
| **RVU-based** | G (Physician/Professional), J (Path/Lab), H (Anesthesia) | `RVU × CF[category] × GAAF[zip3, category]` |
| **GAAF (per 3-digit ZIP)** | L (professional, per-category), P (outpatient facility), Q (DME drug/non-drug), N (inpatient), O (SNF), R | — |
| **Reference** | S (conversion factors by category), M (modifier factors) | — |

**Validated against real data (ZIP 191, Philadelphia):**
- 72148 MRI (Table F) $1,627.17 × 1.26 = **$2,050.23**
- K0005 wheelchair (Table K) $4,705.80 × 1.10 = **$5,176.38**
- 99214 office visit (Table G, non-facility) (1.92 + 1.80) × 101.17 × 0.95 = **$357.53**
- 97110 PT (Table G, non-facility) (0.45 + 0.43) × 96.07 × 0.85 = **$71.86**

## Methodology (the formula the engine encodes)

For a code, gather every **basis** (a code can appear in multiple tables = the
"combinations", e.g. MRI has a facility charge in F and a professional read in G):

- **Direct charge** (F/K/C/D/E/I/A/B): `amount = charge × gaaf(table, zip3, gaaf_category)`.
  - F → Table P single factor; K → Table Q (Non-Drug vs Drug per the row's GAAF Category).
- **RVU-based** (G/J/H): `rvu = work_rvu + pe_rvu` (or `total_expense_rvu` when that
  is the populated total), `amount = rvu × CF[cf_category] × gaaf('L', zip3, cf_category)`.
  - **Professional setting (DECISION):** store **both** facility & non-facility PE;
    `pe_rvu` defaults to **non-facility** (community/office care) and is flippable
    per care item.
  - J (lab) → category "Pathology"; H (anesthesia) → "Anesthesia".
- **Modifier** (Table M): if a modifier is supplied, multiply by its charge factor.
- National charge = the same with all GAAFs = 1.0 (Table "Nationwide Average" row).

No fabrication: a code with no VA basis returns nothing (caller flags it). A basis
whose GAAF category can't be resolved falls back to national (gaaf 1.0) and says so.

## Architecture

**`palcp/pricing/va_charges.py`** — pure engine, no I/O:
- `VAChargeBasis` (frozen): code, table, charge_type, description, charge, work_rvu,
  facility_pe_rvu, nonfacility_pe_rvu, total_expense_rvu, cf_category, gaaf_table,
  gaaf_category, methodology, status_indicator, modifier.
- `VADataset`: holds dicts — `bases[code] -> [VAChargeBasis]`, `cf[category] -> float`,
  `gaaf[(table, zip3, category)] -> float`, `modifier[m] -> float`, plus `version`,
  `effective_date`. Constructible directly (tests) or `from_sqlite(path)`.
- `VACharge` (frozen): code, table, charge_type, description, **amount** (localized),
  national, zip3, gaaf, setting, breakdown (human formula string).
- `compute_charge(ds, code, zip3, *, setting="non_facility", modifier=None) -> [VACharge]`
  — one result per basis; deterministic; pure.
- `best_charge(...)` — pick the LCP-relevant basis for a bare code lookup
  (professional G for E/M & therapy codes; otherwise the single available basis;
  ties surfaced, never silently dropped).

**`palcp/pricing/va_ingest.py`** + **`scripts/build_va_dataset.py`** — read the 19
workbooks (config-driven per-table column map + GAAF mapping) → `VADataset` →
`to_sqlite(path)`. Output `data/va_charges.sqlite` is **gitignored** (CPT©/AMA).
LCP-critical tables (F, G, J, K + GAAF L, P, Q + S, M) first; A/B/C/D/E/H/I best-effort.

## Phase 2 (web integration — next)

Per-case ZIP3 drives `compute_charge`; care item gains a `va_setting`
(facility|non_facility) toggle; the system "VA Reasonable Charges" library becomes a
**computed** source (build a `PricingTable` on the fly for the case's items at its
ZIP, reusing existing `apply_pricing`/auto-fill); `/lookup-code` and the catalog
price from it. Falls back to the labeled SAMPLE seed when the dataset is absent.

## Testing

- Hermetic formula tests on a hand-built `VADataset` fixture (direct + RVU + modifier
  + national + missing-GAAF fallback + facility/non-facility settings).
- A real-data validation test (skipped unless `~/Downloads/VA UCR TABLES` exists)
  asserting the four validated numbers above to the cent.
- Ingestion test on a tiny fixture workbook set.

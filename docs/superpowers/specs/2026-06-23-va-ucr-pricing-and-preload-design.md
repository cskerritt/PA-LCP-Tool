# VA-UCR pricing + maximal preload — design

**Date:** 2026-06-23
**Status:** Approved (design), pending spec review
**Goal:** Make the tool price life-care-plan line items from the **VA Reasonable
Charges** (UCR) tables by default, and **preload/predict as much as possible** so
the user enters the minimum data per item — ideally just a code (or one-click
catalog pick) plus a frequency/timing.

---

## 1. Background & current state

The engine (`palcp`) already supports pricing-by-code:

- `pricing/schema.py` — `PriceRecord` / `PricingTable` (`by_code`).
- `pricing/loaders.py` — `load_pricing(path, preset=…)` with a
  `va_reasonable_charges` column preset.
- `pricing/lookup.py` — `resolve_item` / `apply_pricing`: matches a `CareItem.code`
  to the best `PriceRecord` and back-fills `unit_cost`, `pricing_source`,
  `code_type`, `geographic_basis`, `percentile`, `retrieval_date`.

The web app (`palcp_web`) lets a user upload pricing libraries
(`routers/pricing.py`), link them to a case (`CasePricingLink`), and prices are
applied **only at compute time** (`services.compute_case → apply_pricing`).

**Gaps vs. the goal**

1. **No real VA data.** The repo ships 4 synthetic rows (`data/sample_pricing.csv`).
2. **No geographic locality model.** Cases have a free-text `residence`; there is
   no structured 3-digit ZIP and no locality-aware price resolution.
3. **No auto-fill at entry.** Typing a CPT into the add/edit item form fills
   nothing; the user hand-enters source, percentile, geo, growth class, cost.
4. **`apply_pricing` stops short** of filling `description`, `category`,
   `growth_key`.
5. **No system-wide default library** — every pricing table is user-scoped and
   must be manually linked per case.
6. **No common-item catalog** — every item is typed from scratch.

## 2. Constraint discovered during research (shapes the data path)

The official VA Reasonable Charges (current **V5.26, effective 01/01/2026**) split as:

- **Directly downloadable (public, static URLs):** inpatient **MS-DRG** per-diem
  tables (Table A/B) and the **"Data Sources"** methodology workbook (gives exact
  citations, effective dates, and source-of-truth per charge type).
- **Behind the AMA CPT-Code disclaimer (one-click license acceptance):** the
  **outpatient / professional CPT-HCPCS charge tables** — the part an LCP needs
  most. Not at a clean URL; and the CPT *descriptions* are AMA-copyrighted, so the
  full table must **not** be committed into the repo.

**Consequence — hybrid data path (approved):**
- Auto-fetch the public pieces (inpatient + data-sources metadata) via a script.
- The license-gated **outpatient/professional .xlsx** is downloaded once by the
  user (a click they are entitled to make) — or supplied from a VA export they
  already keep — and **ingested locally** as the default library.
- The full VA table is stored locally and **gitignored**. A small,
  **clearly-labeled synthetic seed** ships in-repo so tests/demo are hermetic and
  nothing fabricated ever reaches a real report.

## 3. Non-goals (YAGNI)

- No scraping/automation that defeats the CPT license click-through.
- No bundling AMA CPT descriptions or the full VA table into git.
- No Rx retail pricing engine (VA UCR doesn't cover retail Rx well). Rx items are
  recognized and routed to the `rx` growth class and flagged "needs Rx source
  (e.g. RED BOOK/GoodRx)" — pricing them is out of scope here.
- No change to the projection math, discount/growth methodology, or workbook tabs
  beyond added disclosure of the VA version + locality.

## 4. Architecture

Seven components. Each is independently testable.

### 4.1 VA charge ingestion (`palcp/pricing/va.py` + `scripts/fetch_va_charges.py`)

- A canonical **VA charge schema** is just the existing `PriceRecord`
  (`source, code, code_type, description, amount, percentile, geographic_area,
  effective_date, citation_url`) — no new engine schema needed.
- `load_va_outpatient(path, *, version, effective_date, sheet=None)` — a flexible
  loader (built on the existing preset machinery) that normalizes the official VA
  outpatient/professional workbook into `PriceRecord`s. It tolerates the
  real-world quirks the existing `_to_float` already handles ("BR"/by-report,
  "N/A", `$`/`,`/space). `source = "VA Reasonable Charges {version}"`,
  `citation_url` = the VA page, `effective_date` = the version's effective date.
- `scripts/fetch_va_charges.py` (CLI):
  - `--fetch-public` → downloads inpatient Table A/B + the data-sources workbook
    to a local cache (real, public).
  - `--outpatient PATH` → ingests the user's downloaded outpatient .xlsx.
  - `--out DIR` → writes a normalized `va_charges_{version}.csv` (gitignored) and
    refreshes the in-repo labeled seed schema (not the real amounts).
  - Idempotent; prints a provenance summary (version, effective date, row count,
    code-type breakdown).

### 4.2 Geographic locality (per-case 3-digit ZIP; GAAF-aware, no fabrication)

- **`Case.geo_zip3`** (new column, 3 chars) + optional `geo_locality_name`.
  Required at compute time when VA pricing is used; **no default** (per decision).
- Resolution order in `lookup.resolve_item` becomes locality-aware:
  1. exact `geographic_area` match to the case ZIP3,
  2. else the VA **national base** record,
  3. else unresolved (flagged, never guessed).
- **GAAF:** if the VA file is national-base, a separately-loaded, **cited**
  GAAF-by-ZIP3 table may be applied: `locality_charge = national × GAAF`, and the
  factor + its source are recorded on the resolution and disclosed on the
  workbook. If no GAAF table is loaded, the **national** charge is used and the
  workbook **discloses** "national; GAAF for ZIP nnn not applied." Honest by
  construction — we never invent a locality amount.

### 4.3 Extend engine auto-fill (`palcp/pricing/lookup.py`)

`apply_pricing` additionally fills, **only when the item leaves them blank**:
`description`, `category` (from a code→category hint), and `growth_key` (via 4.4).
Existing behavior (cost/source/code_type/geo/percentile/retrieval) is unchanged.
Resolution gains a `geo_note`/`gaaf` field for disclosure.

### 4.4 Growth-class mapper (`palcp/pricing/growth_map.py`)

Deterministic `growth_key_for(code, code_type) -> str` over the six existing keys
(`medical_services, rx, dme, facility, attendant_care_wage, general`):
- HCPCS `E####`/`K####`/`A####` (DME/supply) → `dme`
- HCPCS `J####` / NDC → `rx`
- CPT facility/APC ranges and revenue codes → `facility`
- CPT professional ranges (E/M, therapy, imaging, surgery) → `medical_services`
- attendant/home-health (`S9122`, `T1019`, `99509`, …) → `attendant_care_wage`
- unknown → `medical_services` (current default), never errors.
Pure function, fully unit-tested with a table of representative codes.

### 4.5 System-wide default VA library (`palcp_web`)

- `PricingTable` gains **`is_system`** (bool) and `user_id` becomes **nullable**
  (system tables belong to no user). Plus `version`/`effective_date` metadata.
- A seeding routine (`services.ensure_default_va_library`, run on app startup and
  by the ingest script) creates/refreshes the system table
  **"VA Reasonable Charges v5.26"** from the normalized CSV (or the labeled seed
  if the real file is absent — clearly named "VA Reasonable Charges (SAMPLE — load
  official data)").
- **Auto-link on case creation:** `create_case` links the active system VA table
  via `CasePricingLink`, so every new case is VA-priced with zero setup.
- The pricing list/detail UI marks system tables read-only (no delete).

### 4.6 Auto-price + auto-fill on entry (`palcp_web`)

- **`GET /lookup/code`** (`routers/lookup.py`): params `code`, `code_type?`,
  `case_id` (→ ZIP3 + percentile policy). Returns an **HTMX partial** of the
  resolved fields (unit cost, description, code type, source, percentile, geo
  basis, retrieval/effective date, growth key, category hint) + a provenance line,
  or a "no VA match — enter manually / flag for direct survey" message.
- Wire HTMX `hx-get` on the **code** input (`hx-trigger="change, blur"`,
  `hx-target` the surrounding fieldset, `hx-swap` the inputs' values via OOB
  swaps) in both `_items_section.html` (add) and `item_form.html` (edit).
- Server-side, `add_item`/`update_item` already persist whatever the form posts —
  so a confirmed auto-fill simply submits. No silent server-side magic the user
  can't see/override (Daubert-friendly: the planner reviews every value).

### 4.7 Common-LCP-items catalog (`palcp/catalog/` + `palcp_web`)

- Bundled data `palcp/catalog/common_items.yaml`: curated entries
  `{key, label, category, code, code_type, growth_key, default_timing,
  typical_frequency, note}` for frequent LCP lines (PM&R/ortho/neuro follow-ups,
  PT/OT/SLP eval+treat, EMG/NCS, MRI/CT/X-ray, injections, common DME by HCPCS,
  home health). **Codes/categories built using the `lcp-cpt-coding` skill** so the
  mappings are defensible. No prices in the catalog — prices come from the VA
  table at the case's locality.
- `palcp/catalog/__init__.py`: `load_catalog()`, `search(query)`.
- Web: `GET /cases/{id}/catalog` (searchable list, grouped by category) and
  `POST /cases/{id}/catalog/add` (creates a `CareItemRow` pre-filled from the
  catalog entry, then auto-prices from the linked VA table for the case ZIP3).
  User then sets frequency/timing + medical foundation. One click ≈ a coded,
  priced line.

## 5. Data flow (happy path, web)

1. User creates a case → default **VA Reasonable Charges v5.26** auto-linked;
   user sets case **ZIP3** in assumptions.
2. User clicks a catalog item *or* types a CPT → `/lookup/code` returns the VA
   record for that ZIP3 → fields auto-fill (cost/desc/source/percentile/geo/
   retrieval/growth class/category).
3. User confirms frequency/timing + medical foundation → save.
4. `compute_case` re-resolves through the same engine path → totals + Daubert
   validation → workbook discloses VA version, effective date, locality, GAAF.

## 6. Defensibility (unchanged philosophy, strengthened)

- Every auto-filled value carries VA source + version + effective date + locality;
  the **Data Sources** and **Assumptions** tabs state them. The 80th-percentile
  (or case-policy) value is applied **consistently** (existing percentile policy).
- The Daubert validator is unchanged and still flags placeholders, missing medical
  foundation, and percentile inconsistency. New, additive checks: VA-priced item
  with no case ZIP3; code with no VA match left unpriced (flagged, not guessed);
  Rx item lacking an Rx pricing source.
- **Nothing is invented.** Unmatched codes stay `unresolved` (cost 0, flagged).
  The shipped seed is labeled SAMPLE; real amounts require the official file.

## 7. Licensing

- `.gitignore`: the normalized `va_charges_*.csv` and any official VA workbook.
- In-repo seed clearly labeled SAMPLE; `docs/` + README note that the user must
  load the official VA outpatient table (CPT-disclaimer click) and that CPT is
  AMA-copyrighted (the firm's existing CPT license governs internal use).

## 8. Testing (TDD)

- **Engine unit tests:** `va.load_va_outpatient` (quirks, version/citation
  stamping), `growth_map` (representative code table), extended `apply_pricing`
  (fills desc/category/growth_key only when blank; geo/GAAF resolution + national
  fallback + unresolved), catalog load/search.
- **Web tests:** default VA library seeded + auto-linked on case create; `/lookup/
  code` returns correct fields incl. ZIP3 locality; catalog add creates a priced
  row; ZIP3 persists; system table is read-only.
- **Golden test:** a fixture case priced from the labeled seed projects to a known
  workbook (extends the existing golden-test approach).
- All tests hermetic via the in-repo seed (no network, no real VA file).

## 9. Migrations

One Alembic revision: `cases.geo_zip3`, `cases.geo_locality_name`;
`pricing_tables.is_system` (+ nullable `user_id`, `version`, `effective_date`).
Backfill: existing cases `geo_zip3=NULL`; existing tables `is_system=false`.

## 10. Build order (high level — detailed plan follows)

1. Engine: `growth_map`, extended `apply_pricing`, `va.load_va_outpatient`
   (+ tests).
2. Geo resolution + GAAF disclosure in `lookup` (+ tests).
3. Catalog data + loader (+ tests).
4. Migration + `is_system` default library + auto-link on case create (+ tests).
5. `/lookup/code` endpoint + HTMX wiring in add/edit forms (+ tests).
6. Catalog UI endpoints (+ tests).
7. `scripts/fetch_va_charges.py` + gitignore + docs/README + workbook disclosure.
8. End-to-end run, golden test, manual smoke in the browser.

## 11. Open items confirmed at build time (not blockers)

- **Exact official outpatient file layout** (national-base vs per-locality, sheet
  names, column headers) — `load_va_outpatient` is written to detect/handle both;
  finalized against the real file when supplied.
- **GAAF-by-ZIP3 source** — applied only if a cited table is loaded; otherwise
  national charge is used and disclosed. No fabrication either way.

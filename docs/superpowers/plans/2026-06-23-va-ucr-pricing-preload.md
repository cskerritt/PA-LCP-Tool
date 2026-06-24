# VA-UCR Pricing + Maximal Preload — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Price life-care-plan line items from the VA Reasonable Charges (UCR) tables by default and preload/predict as much per-item data as possible, so the user enters the minimum (typically a code or a catalog pick, plus frequency/timing).

**Architecture:** Engine-side pure helpers (growth-class mapper, VA loader, geo/GAAF-aware resolution, extended auto-fill, catalog) build on the existing `palcp.pricing` dataclasses with no new schema. Web-side adds a per-case 3-digit ZIP, a system-wide default VA pricing library auto-linked on case creation, an HTMX `/lookup-code` auto-fill endpoint, and a curated common-items catalog. Daubert integrity is preserved: nothing is fabricated; unmatched codes are flagged, not guessed.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Jinja2 + HTMX, openpyxl, pytest.

**Spec:** `docs/superpowers/specs/2026-06-23-va-ucr-pricing-and-preload-design.md`

---

## File structure

**Engine (`src/palcp/`)**
- Create `pricing/growth_map.py` — `growth_key_for(code, code_type)`, `category_hint(code, code_type)`. Pure.
- Modify `pricing/lookup.py` — extend `apply_pricing` auto-fill; add geo/GAAF-aware `resolve_item`.
- Create `pricing/va.py` — `load_va_outpatient(...)` normalizing the official VA workbook to `PriceRecord`s.
- Create `catalog/__init__.py`, `catalog/common_items.py`, `data/common_items.yaml` — curated common LCP items (codes/categories/growth keys, no prices).
- Create `data/va_charges_seed.csv` — small, clearly-labeled SAMPLE VA rows for hermetic tests/demo.
- Modify `pricing/__init__.py`, `palcp/__init__.py` — export new helpers.

**Web (`src/palcp_web/`)**
- Modify `models.py` — `Case.geo_zip3`, `Case.geo_locality_name`; `PricingTable.is_system` (+ nullable `user_id`, `version`, `effective_date`).
- Create `alembic/versions/20260623_0002_va_pricing.py` — additive migration.
- Modify `services.py` — `ensure_default_va_library`, geo wiring in `plan_from_case`, ZIP into `_care_item`.
- Modify `routers/cases.py` — auto-link default VA library on create; persist ZIP3.
- Create `routers/lookup.py` — `GET /cases/{id}/lookup-code` HTMX auto-fill.
- Create `routers/catalog.py` — catalog browse + one-click add.
- Modify `main.py` — register routers; seed default library on startup.
- Modify templates: `cases/_items_section.html`, `cases/item_form.html` (HTMX + field ids), `cases/form.html` (ZIP3), new `cases/_item_autofill.html`, new `catalog/list.html`, `cases/detail.html` (catalog link + system-table marking).
- Modify `workbook/builder.py`/`content.py` — disclose VA version + locality on Data Sources tab.

**Scripts/docs**
- Create `scripts/fetch_va_charges.py` — fetch public pieces; ingest user's outpatient xlsx; emit normalized CSV.
- Modify `.gitignore`, `README.md`, `docs/DATA_SCHEMA.md`.

**Tests (`tests/`)** — `test_growth_map.py`, `test_apply_pricing.py`, `test_va_loader.py`, `test_geo_resolution.py`, `test_catalog.py`, `test_web_va_pricing.py` (extends `test_web.py` patterns).

---

## Task 1: Growth-class mapper

**Files:**
- Create: `src/palcp/pricing/growth_map.py`
- Test: `tests/test_growth_map.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_growth_map.py
from palcp.pricing.growth_map import growth_key_for, category_hint


def test_growth_key_for_codes():
    assert growth_key_for("99214", "CPT") == "medical_services"     # E/M visit
    assert growth_key_for("97110", "CPT") == "medical_services"     # PT
    assert growth_key_for("72148", "CPT") == "medical_services"     # MRI
    assert growth_key_for("E1130", "HCPCS") == "dme"                # wheelchair
    assert growth_key_for("K0005", "HCPCS") == "dme"                # wheelchair
    assert growth_key_for("L1846", "HCPCS") == "dme"                # orthotic
    assert growth_key_for("A4595", "HCPCS") == "dme"                # supplies
    assert growth_key_for("J2270", "HCPCS") == "rx"                 # injectable drug
    assert growth_key_for("S9122", "HCPCS") == "attendant_care_wage"  # home health aide
    assert growth_key_for("T1019", "HCPCS") == "attendant_care_wage"  # personal care
    assert growth_key_for("99600", "CPT") == "attendant_care_wage"  # home visit NOS
    assert growth_key_for("470", "MS-DRG") == "facility"
    assert growth_key_for("0345", "APC") == "facility"
    assert growth_key_for("", "") == "medical_services"            # unknown -> default
    assert growth_key_for("zzz", "") == "medical_services"


def test_category_hint():
    assert category_hint("99214", "CPT") == "Physician Services"
    assert category_hint("97110", "CPT") == "Therapies"
    assert category_hint("72148", "CPT") == "Diagnostics & Imaging"
    assert category_hint("E1130", "HCPCS") == "DME & Supplies"
    assert category_hint("J2270", "HCPCS") == "Medications"
    assert category_hint("S9122", "HCPCS") == "Attendant / Home Care"
    assert category_hint("470", "MS-DRG") == "Facility / Hospital"
    assert category_hint("zzz", "") == "Uncategorized"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_growth_map.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'palcp.pricing.growth_map'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/palcp/pricing/growth_map.py
"""Map a procedure code to its growth series and a category hint.

Pure, deterministic helpers used to preload a care item's growth class and
grouping from its code, so the user does not pick them by hand. Rules are
conservative; unknown codes fall back to the engine's existing default
(``medical_services`` / ``Uncategorized``) and never raise.
"""

from __future__ import annotations

from .schema import normalize_code

# HCPCS Level II codes that denote home-health / personal / attendant care.
_ATTENDANT_HCPCS = {
    "S9122", "S9123", "S9124", "S5125", "S5126", "S5130", "S5131",
    "T1019", "T1020", "T1021", "T1004", "T1005", "G0156", "G0299", "G0300",
}
# CPT home-visit / care-in-residence range (99500-99602) is attendant/home care.
def _is_attendant_cpt(num: int) -> bool:
    return 99500 <= num <= 99602


def _digits(code: str) -> int | None:
    body = "".join(ch for ch in code if ch.isdigit())
    return int(body) if body else None


def growth_key_for(code: str, code_type: str = "") -> str:
    """Return one of the engine's growth keys for ``code``.

    Keys: medical_services | rx | dme | facility | attendant_care_wage | general.
    """
    c = normalize_code(code)
    t = (code_type or "").strip().upper()

    if t in ("MS-DRG", "DRG", "APC", "REV", "REVENUE"):
        return "facility"
    if t == "NDC":
        return "rx"

    if c in _ATTENDANT_HCPCS:
        return "attendant_care_wage"

    if c[:1].isalpha():  # HCPCS Level II
        head = c[0]
        if head == "J":          # drugs administered other than oral
            return "rx"
        if head in ("E", "K", "L"):  # DME, additions, orthotics/prosthetics
            return "dme"
        if head == "A":          # transport + medical/surgical supplies
            return "dme"
        # B/G/Q/S/T and others: fall through to default unless matched above
        return "medical_services"

    num = _digits(c)
    if num is not None and _is_attendant_cpt(num):
        return "attendant_care_wage"
    return "medical_services"


def category_hint(code: str, code_type: str = "") -> str:
    """Return a human grouping label for ``code`` (best-effort, never raises)."""
    c = normalize_code(code)
    t = (code_type or "").strip().upper()
    key = growth_key_for(c, t)
    if key == "dme":
        return "DME & Supplies"
    if key == "rx":
        return "Medications"
    if key == "attendant_care_wage":
        return "Attendant / Home Care"
    if key == "facility":
        return "Facility / Hospital"
    # medical_services: split by CPT range when possible
    num = _digits(c)
    if num is not None:
        if 70000 <= num <= 79999:
            return "Diagnostics & Imaging"
        if 97000 <= num <= 97799:
            return "Therapies"
        if 99000 <= num <= 99499:
            return "Physician Services"
        if 10000 <= num <= 69999:
            return "Procedures & Surgery"
        return "Physician Services"
    return "Uncategorized"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_growth_map.py -v`
Expected: PASS (10+ assertions)

- [ ] **Step 5: Commit**

```bash
git add src/palcp/pricing/growth_map.py tests/test_growth_map.py
git commit -m "feat(pricing): add code -> growth-class + category mapper"
```

---

## Task 2: Extend `apply_pricing` auto-fill (description/category/growth_key)

**Files:**
- Modify: `src/palcp/pricing/lookup.py`
- Test: `tests/test_apply_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_apply_pricing.py
from palcp.models import CareItem
from palcp.pricing import PriceRecord, PricingTable, apply_pricing


def _table():
    return PricingTable(records=[
        PriceRecord(source="VA Reasonable Charges v5.26", code="99214",
                    amount=198.0, code_type="CPT",
                    description="Office/outpatient visit, established patient",
                    percentile=None, geographic_area="191",
                    effective_date="2026-01-01",
                    citation_url="https://www.va.gov/x"),
    ])


def test_apply_pricing_fills_blank_desc_category_growth():
    item = CareItem(category="Uncategorized", item="Follow-up", unit_cost=0.0,
                    code="99214")
    res = apply_pricing([item], _table())[0]
    assert res.method == "matched"
    assert item.unit_cost == 198.0
    assert item.description == "Office/outpatient visit, established patient"
    assert item.category == "Physician Services"      # from category_hint
    assert item.growth_key == "medical_services"       # from growth_map
    assert item.pricing_source == "VA Reasonable Charges v5.26"


def test_apply_pricing_does_not_overwrite_user_values():
    item = CareItem(category="My Category", item="Visit", unit_cost=0.0,
                    code="99214", description="my desc", growth_key="general")
    apply_pricing([item], _table())
    assert item.description == "my desc"
    assert item.category == "My Category"
    assert item.growth_key == "general"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_apply_pricing.py -v`
Expected: FAIL — `item.category` stays "Uncategorized", `description` stays "", growth unchanged.

- [ ] **Step 3: Write minimal implementation**

In `src/palcp/pricing/lookup.py`, add the import near the top:

```python
from .growth_map import category_hint, growth_key_for
```

In `apply_pricing`, inside the `if res.method == "matched" and res.record is not None:` block, after the existing back-fill lines (after `item.retrieval_date = ...`), add:

```python
            if not item.description and best_desc := res.record.description:
                item.description = best_desc
            if (not item.category) or item.category == "Uncategorized":
                hint = category_hint(item.code, item.code_type or res.record.code_type)
                if hint != "Uncategorized":
                    item.category = hint
            if (not item.growth_key) or item.growth_key == "medical_services":
                item.growth_key = growth_key_for(
                    item.code, item.code_type or res.record.code_type)
```

(Note: the walrus on `best_desc` keeps it one statement; if your linter dislikes it, expand to two lines.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_apply_pricing.py -v`
Expected: PASS

- [ ] **Step 5: Run the full engine suite for regressions**

Run: `pytest tests/ -q -k "not web"`
Expected: PASS (no regressions in existing pricing/projection tests)

- [ ] **Step 6: Commit**

```bash
git add src/palcp/pricing/lookup.py tests/test_apply_pricing.py
git commit -m "feat(pricing): auto-fill description/category/growth_key on match"
```

---

## Task 3: VA outpatient/professional loader

**Files:**
- Create: `src/palcp/pricing/va.py`
- Create: `src/palcp/data/va_charges_seed.csv`
- Test: `tests/test_va_loader.py`

- [ ] **Step 1: Create the labeled SAMPLE seed file**

```csv
# src/palcp/data/va_charges_seed.csv
# SAMPLE — synthetic, clearly-labeled placeholder data ONLY. Replace by loading
# the official VA Reasonable Charges outpatient/professional workbook via
# scripts/fetch_va_charges.py. Amounts here are NOT real VA charges.
source,code,code_type,description,amount,percentile,geographic_area,effective_date,citation_url
VA Reasonable Charges (SAMPLE — load official data),99214,CPT,Office/outpatient visit established patient,200,,National,2026-01-01,https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp
VA Reasonable Charges (SAMPLE — load official data),97110,CPT,Therapeutic exercise per 15 min,40,,National,2026-01-01,https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp
VA Reasonable Charges (SAMPLE — load official data),72148,CPT,MRI lumbar spine without contrast,1200,,National,2026-01-01,https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp
VA Reasonable Charges (SAMPLE — load official data),E1130,HCPCS,Standard wheelchair,500,,National,2026-01-01,https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_va_loader.py
from pathlib import Path

from palcp.pricing.va import load_va_outpatient, SEED_PATH


def test_seed_file_loads_and_is_labeled():
    table = load_va_outpatient(SEED_PATH, version="SAMPLE", effective_date="2026-01-01")
    assert len(table) == 4
    rec = table.by_code("99214")[0]
    assert rec.amount == 200.0
    assert "SAMPLE" in rec.source           # never mistaken for real data
    assert rec.effective_date == "2026-01-01"


def test_load_va_outpatient_stamps_version(tmp_path: Path):
    f = tmp_path / "va.csv"
    f.write_text(
        "CPT/HCPCS,Description,Charge,Geographic Area\n"
        "99213,Office visit est. patient,150,191\n"
        "BR99,By report item,BR,191\n",  # 'BR' (by report) row must be skipped
        encoding="utf-8")
    table = load_va_outpatient(f, version="v5.26", effective_date="2026-01-01")
    assert len(table) == 1
    rec = table.by_code("99213")[0]
    assert rec.amount == 150.0
    assert rec.source == "VA Reasonable Charges v5.26"
    assert rec.geographic_area == "191"
    assert rec.citation_url.startswith("https://www.va.gov")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_va_loader.py -v`
Expected: FAIL — `No module named 'palcp.pricing.va'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/palcp/pricing/va.py
"""Load the official VA Reasonable Charges outpatient/professional workbook.

The VA publishes outpatient & professional charges keyed by CPT/HCPCS, with a
geographic component (3-digit ZIP / GAAF). The exact column layout varies by
release, so this loader builds on the flexible ``load_pricing`` preset machinery
and stamps every row with the VA source + version + effective date + citation.

It tolerates real-world quirks already handled by ``load_pricing`` ('BR'/by
report, 'N/A', '$'/','/space) by skipping non-numeric charge rows rather than
aborting. The SAMPLE seed (``SEED_PATH``) is synthetic and clearly labeled.
"""

from __future__ import annotations

from pathlib import Path

from .loaders import load_pricing
from .schema import PriceRecord, PricingTable

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "va_charges_seed.csv"
VA_CITATION = "https://www.va.gov/COMMUNITYCARE/revenue-ops/payer-rates.asp"


def load_va_outpatient(
    path: str | Path,
    *,
    version: str,
    effective_date: str,
    sheet: str | None = None,
) -> PricingTable:
    """Normalize a VA outpatient/professional workbook into a PricingTable.

    ``version`` (e.g. "v5.26") names the release; ``effective_date`` its start.
    The seed CSV already uses canonical columns; official files map via the
    ``va_reasonable_charges`` preset (code=CPT/HCPCS, description, amount=Charge,
    geographic_area=Geographic Area).
    """
    raw = load_pricing(path, preset="va_reasonable_charges", sheet=sheet)
    source = f"VA Reasonable Charges {version}"
    out = PricingTable()
    for r in raw.records:
        out.add(PriceRecord(
            source=(r.source if "SAMPLE" in (r.source or "") else source),
            code=r.code,
            amount=r.amount,
            code_type=r.code_type or "CPT/HCPCS",
            description=r.description,
            percentile=r.percentile,
            geographic_area=r.geographic_area,
            effective_date=r.effective_date or effective_date,
            citation_url=r.citation_url or VA_CITATION,
        ))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_va_loader.py -v`
Expected: PASS

- [ ] **Step 6: Ensure the seed ships in the package**

In `pyproject.toml`, the `[tool.setuptools.package-data]` already includes `palcp = ["data/*.csv", ...]`, so `va_charges_seed.csv` is packaged. Verify:

Run: `python -c "from palcp.pricing.va import SEED_PATH; print(SEED_PATH.exists())"`
Expected: `True`

- [ ] **Step 7: Commit**

```bash
git add src/palcp/pricing/va.py src/palcp/data/va_charges_seed.csv tests/test_va_loader.py
git commit -m "feat(pricing): VA outpatient loader + labeled SAMPLE seed"
```

---

## Task 4: Geo/GAAF-aware resolution

**Files:**
- Modify: `src/palcp/pricing/lookup.py`
- Test: `tests/test_geo_resolution.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_geo_resolution.py
from palcp.models import CareItem
from palcp.pricing import PriceRecord, PricingTable
from palcp.pricing.lookup import resolve_item


def _table():
    return PricingTable(records=[
        PriceRecord(source="VA v5.26", code="99214", amount=210.0, code_type="CPT",
                    geographic_area="191", effective_date="2026-01-01"),
        PriceRecord(source="VA v5.26", code="99214", amount=190.0, code_type="CPT",
                    geographic_area="National", effective_date="2026-01-01"),
    ])


def test_prefers_zip3_locality_match():
    item = CareItem(category="", item="Visit", unit_cost=0.0, code="99214",
                    geographic_basis="191")
    res = resolve_item(item, _table())
    assert res.unit_cost == 210.0
    assert res.record.geographic_area == "191"


def test_falls_back_to_national_when_no_locality_match():
    item = CareItem(category="", item="Visit", unit_cost=0.0, code="99214",
                    geographic_basis="999")  # no 999 locality in table
    res = resolve_item(item, _table())
    assert res.unit_cost == 190.0
    assert res.record.geographic_area == "National"


def test_unmatched_code_is_unresolved_not_guessed():
    item = CareItem(category="", item="X", unit_cost=0.0, code="00000",
                    geographic_basis="191")
    res = resolve_item(item, _table())
    assert res.method == "unresolved"
    assert res.unit_cost == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_geo_resolution.py -v`
Expected: FAIL — current `_score` ranks by `record.amount` (prefers higher), so the 191 vs National tie-breaks wrong and national fallback isn't explicit.

- [ ] **Step 3: Update `resolve_item` scoring in `src/palcp/pricing/lookup.py`**

Replace the `_score` function body with locality-first logic:

```python
def _score(record: PriceRecord, item: CareItem) -> tuple:
    """Higher tuples sort first. Locality (exact ZIP3) beats National; an exact
    source/percentile match still matters; amount is the final, weakest tiebreak
    (kept only for determinism, never to prefer a pricier row)."""
    geo = (record.geographic_area or "").strip().lower()
    want_geo = (item.geographic_basis or "").strip().lower()
    exact_geo = int(bool(want_geo) and want_geo == geo)
    is_national = int(geo in ("national", "nation", "us", ""))
    src_match = int(
        bool(item.pricing_source)
        and item.pricing_source.lower() in (record.source or "").lower()
    )
    pct_match = int(
        item.percentile is not None
        and record.percentile is not None
        and abs(record.percentile - item.percentile) < 1e-6
    )
    # exact locality first, then a national fallback, then source/pct, then a
    # *lower* amount (negated) so ties are stable and never bias upward.
    return (exact_geo, is_national, src_match, pct_match, -record.amount)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_geo_resolution.py -v`
Expected: PASS

- [ ] **Step 5: Run the full engine suite for regressions**

Run: `pytest tests/ -q -k "not web"`
Expected: PASS. (If `test_apply_pricing.py` relied on the old amount-preference tie-break, confirm it still passes — its table has a single record per code, so it is unaffected.)

- [ ] **Step 6: Commit**

```bash
git add src/palcp/pricing/lookup.py tests/test_geo_resolution.py
git commit -m "feat(pricing): locality-first resolution with national fallback"
```

---

## Task 5: Common-LCP-items catalog

**Files:**
- Create: `src/palcp/data/common_items.yaml`
- Create: `src/palcp/catalog/__init__.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Create the catalog data (no prices — codes/categories/growth keys only)**

```yaml
# src/palcp/data/common_items.yaml
# Curated common life-care-plan line items. Codes assigned per CPT/HCPCS using
# the lcp-cpt-coding methodology. NO prices here — prices come from the linked
# VA pricing table at the case's locality. default_timing is a hint only.
- key: pmr_followup
  label: "Physiatry (PM&R) follow-up visit"
  category: "Physician Services"
  code: "99214"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 4
  note: "Established-patient office visit, moderate complexity."
- key: ortho_followup
  label: "Orthopedic follow-up visit"
  category: "Physician Services"
  code: "99214"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 2
  note: "Established-patient office visit."
- key: pt_therapeutic_exercise
  label: "Physical therapy — therapeutic exercise (per 15 min)"
  category: "Therapies"
  code: "97110"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 24
  note: "One unit = 15 minutes; set units_per_occurrence for longer sessions."
- key: ot_eval
  label: "Occupational therapy evaluation (low complexity)"
  category: "Therapies"
  code: "97165"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 1
- key: emg_ncs
  label: "EMG / nerve conduction study"
  category: "Diagnostics & Imaging"
  code: "95910"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 1
- key: mri_lumbar
  label: "MRI lumbar spine without contrast"
  category: "Diagnostics & Imaging"
  code: "72148"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 1
- key: esi_injection
  label: "Epidural steroid injection (lumbar/sacral)"
  category: "Procedures & Surgery"
  code: "62323"
  code_type: "CPT"
  growth_key: "medical_services"
  typical_frequency: 2
- key: manual_wheelchair
  label: "Manual wheelchair (ultralightweight)"
  category: "DME & Supplies"
  code: "K0005"
  code_type: "HCPCS"
  growth_key: "dme"
  every_n_years: 5
- key: home_health_aide
  label: "Home health aide (per hour)"
  category: "Attendant / Home Care"
  code: "S9122"
  code_type: "HCPCS"
  growth_key: "attendant_care_wage"
  note: "Enter annual cost via units/frequency (e.g. hours/day × 365)."
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_catalog.py
from palcp.catalog import load_catalog, search


def test_load_catalog_has_entries():
    items = load_catalog()
    assert len(items) >= 8
    pmr = next(i for i in items if i["key"] == "pmr_followup")
    assert pmr["code"] == "99214"
    assert pmr["growth_key"] == "medical_services"
    assert "amount" not in pmr and "price" not in pmr  # never carries a price


def test_search_matches_label_and_code():
    assert any(i["key"] == "mri_lumbar" for i in search("mri"))
    assert any(i["key"] == "pt_therapeutic_exercise" for i in search("97110"))
    assert any(i["key"] == "home_health_aide" for i in search("aide"))
    assert search("") == load_catalog()          # empty query -> all
    assert search("zzzzz") == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_catalog.py -v`
Expected: FAIL — `No module named 'palcp.catalog'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/palcp/catalog/__init__.py
"""Curated catalog of common life-care-plan items (codes/categories/growth keys).

Carries NO prices — prices come from the linked VA pricing table at the case's
locality. Used to let the user add a fully-coded line in one click.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_DATA = Path(__file__).resolve().parent.parent / "data" / "common_items.yaml"


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    with open(_DATA, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    return list(data)


def search(query: str) -> list[dict]:
    """Case-insensitive match on label, code, category, or key. Empty -> all."""
    q = (query or "").strip().lower()
    items = load_catalog()
    if not q:
        return items
    out = []
    for it in items:
        hay = " ".join(str(it.get(k, "")) for k in
                       ("label", "code", "category", "key", "note")).lower()
        if q in hay:
            out.append(it)
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_catalog.py -v`
Expected: PASS

- [ ] **Step 6: Package the data + export**

Add `data/*.yaml` to `[tool.setuptools.package-data]` `palcp` in `pyproject.toml` (currently lists `data/templates/*.yaml` but not `data/*.yaml`):

```toml
palcp = ["data/*.csv", "data/*.yaml", "data/templates/*.csv", "data/templates/*.yaml"]
```

Run: `python -c "from palcp.catalog import load_catalog; print(len(load_catalog()))"`
Expected: a number ≥ 8

- [ ] **Step 7: Commit**

```bash
git add src/palcp/catalog/__init__.py src/palcp/data/common_items.yaml tests/test_catalog.py pyproject.toml
git commit -m "feat(catalog): curated common LCP items (codes, no prices)"
```

---

## Task 6: DB model changes + migration

**Files:**
- Modify: `src/palcp_web/models.py`
- Create: `alembic/versions/20260623_0002_va_pricing.py`
- Test: `tests/test_web_va_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_va_pricing.py
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.NamedTemporaryFile(
    suffix=".db", delete=False).name
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_HTTPS_ONLY"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from palcp_web.db import init_db  # noqa: E402
from palcp_web.main import app  # noqa: E402

init_db()


def test_models_have_new_columns():
    from palcp_web.models import Case, PricingTable
    assert hasattr(Case, "geo_zip3")
    assert hasattr(Case, "geo_locality_name")
    assert hasattr(PricingTable, "is_system")
    assert hasattr(PricingTable, "version")
    assert hasattr(PricingTable, "effective_date")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_va_pricing.py::test_models_have_new_columns -v`
Expected: FAIL — `AssertionError` (attributes absent).

- [ ] **Step 3: Add columns in `src/palcp_web/models.py`**

In `class Case`, after the `residence` line, add:

```python
    geo_zip3: Mapped[str] = mapped_column(String(3), default="")
    geo_locality_name: Mapped[str] = mapped_column(String(128), default="")
```

In `class PricingTable`, change `user_id` to nullable and add the system/version fields:

```python
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[str] = mapped_column(String(32), default="")
    effective_date: Mapped[str] = mapped_column(String(32), default="")
```

(Leave the `name`, `description`, relationships as-is.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_va_pricing.py::test_models_have_new_columns -v`
Expected: PASS (tests use `init_db()`/`create_all`, which reads the current models)

- [ ] **Step 5: Write the Alembic migration for real databases**

```python
# alembic/versions/20260623_0002_va_pricing.py
"""Add per-case ZIP3 + system VA pricing-library columns.

Revision ID: 0002_va_pricing
Revises: 0001_initial
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_va_pricing"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("geo_zip3", sa.String(3),
                                     nullable=False, server_default=""))
    op.add_column("cases", sa.Column("geo_locality_name", sa.String(128),
                                     nullable=False, server_default=""))
    op.add_column("pricing_tables", sa.Column("is_system", sa.Boolean(),
                                              nullable=False, server_default=sa.false()))
    op.add_column("pricing_tables", sa.Column("version", sa.String(32),
                                              nullable=False, server_default=""))
    op.add_column("pricing_tables", sa.Column("effective_date", sa.String(32),
                                              nullable=False, server_default=""))
    op.create_index("ix_pricing_tables_is_system", "pricing_tables", ["is_system"])
    # Make user_id nullable (system tables have no owner).
    with op.batch_alter_table("pricing_tables") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("pricing_tables") as batch:
        batch.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_pricing_tables_is_system", table_name="pricing_tables")
    op.drop_column("pricing_tables", "effective_date")
    op.drop_column("pricing_tables", "version")
    op.drop_column("pricing_tables", "is_system")
    op.drop_column("cases", "geo_locality_name")
    op.drop_column("cases", "geo_zip3")
```

- [ ] **Step 6: Verify the migration applies on a throwaway DB**

Run: `cd "$PWD" && DATABASE_URL="sqlite:////tmp/palcp_mig_test.db" .venv/bin/alembic upgrade head && rm -f /tmp/palcp_mig_test.db`
Expected: `Running upgrade 0001_initial -> 0002_va_pricing` with no error.

- [ ] **Step 7: Commit**

```bash
git add src/palcp_web/models.py alembic/versions/20260623_0002_va_pricing.py tests/test_web_va_pricing.py
git commit -m "feat(web): add case ZIP3 + system VA pricing-library columns + migration"
```

---

## Task 7: Default VA system library + auto-link on case create

**Files:**
- Modify: `src/palcp_web/services.py`
- Modify: `src/palcp_web/routers/cases.py`
- Modify: `src/palcp_web/main.py`
- Modify: `src/palcp_web/routers/pricing.py` (surface system tables read-only)
- Test: `tests/test_web_va_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_web_va_pricing.py
def _register(c, email):
    r = c.post("/register", data={"email": email, "password": "password1",
                                  "full_name": "Eval", "credentials": "CLCP"})
    assert r.status_code == 200


def test_default_va_library_seeded_and_autolinked():
    from palcp_web.db import SessionLocal
    from palcp_web.services import ensure_default_va_library
    from palcp_web.models import PricingTable, Case, CasePricingLink
    db = SessionLocal()
    table = ensure_default_va_library(db)
    assert table.is_system is True
    assert "VA Reasonable Charges" in table.name
    assert len(table.records) >= 4          # from the SAMPLE seed
    db.close()

    c = TestClient(app)
    _register(c, "va@example.com")
    r = c.post("/cases", data={"name": "VA Case"})
    cid = int(str(r.url).rstrip("/").split("/")[-1])
    db = SessionLocal()
    links = db.query(CasePricingLink).filter(CasePricingLink.case_id == cid).all()
    linked_tables = [db.get(PricingTable, l.pricing_table_id) for l in links]
    assert any(t.is_system for t in linked_tables)   # VA auto-linked
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_va_pricing.py::test_default_va_library_seeded_and_autolinked -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_default_va_library'`

- [ ] **Step 3: Implement `ensure_default_va_library` in `src/palcp_web/services.py`**

Add imports at the top:

```python
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from palcp.pricing.va import SEED_PATH, load_va_outpatient
from .models import PriceRecordRow, PricingTable
```

Add the function (constants at module level):

```python
VA_DEFAULT_VERSION = "v5.26"
VA_DEFAULT_EFFECTIVE = "2026-01-01"


def _va_source_path() -> Path:
    """Prefer a normalized official CSV if present (gitignored), else the seed."""
    official = Path("data/va_charges_normalized.csv")  # produced by fetch script
    return official if official.exists() else SEED_PATH


def ensure_default_va_library(db: Session) -> PricingTable:
    """Create or return the system-wide default VA pricing library (idempotent)."""
    existing = db.scalar(
        select(PricingTable).where(PricingTable.is_system.is_(True))
        .order_by(PricingTable.id.desc()))
    if existing is not None and existing.records:
        return existing

    src = _va_source_path()
    loaded = load_va_outpatient(src, version=VA_DEFAULT_VERSION,
                                effective_date=VA_DEFAULT_EFFECTIVE)
    label = "VA Reasonable Charges " + VA_DEFAULT_VERSION
    if "SAMPLE" in (loaded.records[0].source if loaded.records else ""):
        label += " (SAMPLE — load official data)"
    table = existing or PricingTable(user_id=None, is_system=True, name=label,
                                     version=VA_DEFAULT_VERSION,
                                     effective_date=VA_DEFAULT_EFFECTIVE,
                                     description="Auto-loaded default. Public VA "
                                     "outpatient/professional reasonable charges.")
    if existing is None:
        db.add(table)
        db.flush()
    for r in loaded.records:
        db.add(PriceRecordRow(
            table_id=table.id, source=r.source, code=r.code, code_type=r.code_type,
            description=r.description, amount=r.amount, percentile=r.percentile,
            geographic_area=r.geographic_area, effective_date=r.effective_date,
            citation_url=r.citation_url))
    db.commit()
    return table
```

- [ ] **Step 4: Auto-link on case create — modify `src/palcp_web/routers/cases.py`**

Add import: `from ..services import GROWTH_KEYS, compute_case, seed_growth_rate_rows, ensure_default_va_library` and `from ..models import CasePricingLink` (already imported). In `create_case`, after `db.flush()` and before `record_audit`, add:

```python
    va = ensure_default_va_library(db)
    db.add(CasePricingLink(case_id=case.id, pricing_table_id=va.id))
    db.flush()
```

- [ ] **Step 5: Seed on startup — modify `src/palcp_web/main.py` lifespan**

In the `lifespan` function, after the SECRET_KEY warning block, add:

```python
    try:
        from .db import SessionLocal
        from .services import ensure_default_va_library
        with SessionLocal() as db:
            ensure_default_va_library(db)
    except Exception:  # pragma: no cover - never block startup on seeding
        logger.exception("Could not seed default VA pricing library")
```

- [ ] **Step 6: Surface system tables (read-only) — modify `src/palcp_web/routers/pricing.py`**

Change `list_pricing`'s query to include system tables, and guard `delete_pricing`/`_owned_table` so system tables can't be deleted by a user:

```python
# in list_pricing:
    from sqlalchemy import or_
    tables = db.scalars(
        select(PricingTable).where(
            or_(PricingTable.user_id == user.id, PricingTable.is_system.is_(True)))
        .order_by(PricingTable.is_system.desc(), PricingTable.updated_at.desc())).all()
```

```python
# in _owned_table, after fetching pt:
    if pt is None or (pt.user_id != user.id and not pt.is_system):
        raise HTTPException(status_code=404)
    return pt
```

```python
# at the top of delete_pricing, after _owned_table(...):
    if table.is_system:
        flash(request, "The default VA library is read-only.", "error")
        return RedirectResponse("/pricing", status_code=303)
```

Also update `case_detail` in `cases.py` so the linkable list includes system tables (same `or_` filter as above) — replace the `all_pricing` query accordingly.

- [ ] **Step 7: Run the tests**

Run: `pytest tests/test_web_va_pricing.py -v`
Expected: PASS. Then `pytest tests/test_web.py -q` — Expected: PASS (no regressions).

- [ ] **Step 8: Commit**

```bash
git add src/palcp_web/services.py src/palcp_web/routers/cases.py src/palcp_web/main.py src/palcp_web/routers/pricing.py tests/test_web_va_pricing.py
git commit -m "feat(web): default VA system library, seeded on startup, auto-linked to new cases"
```

---

## Task 8: `/lookup-code` HTMX auto-fill endpoint

**Files:**
- Create: `src/palcp_web/routers/lookup.py`
- Create: `src/palcp_web/templates/cases/_item_autofill.html`
- Modify: `src/palcp_web/main.py` (register router)
- Test: `tests/test_web_va_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_web_va_pricing.py
def test_lookup_code_autofills_from_va():
    c = TestClient(app)
    _register(c, "lookup@example.com")
    r = c.post("/cases", data={"name": "Lookup Case"})
    cid = int(str(r.url).rstrip("/").split("/")[-1])
    # set ZIP3 via assumptions update
    c.post(f"/cases/{cid}", data={"name": "Lookup Case", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": "191"})
    res = c.get(f"/cases/{cid}/lookup-code", params={"code": "99214"})
    assert res.status_code == 200
    body = res.text
    assert 'name="unit_cost"' in body and "200" in body   # SAMPLE price
    assert "Office/outpatient visit" in body               # description
    assert "medical_services" in body                      # growth key
    assert "VA Reasonable Charges" in body                 # source


def test_lookup_unknown_code_reports_no_match():
    c = TestClient(app)
    _register(c, "lookup2@example.com")
    r = c.post("/cases", data={"name": "Lookup2"})
    cid = int(str(r.url).rstrip("/").split("/")[-1])
    res = c.get(f"/cases/{cid}/lookup-code", params={"code": "00000"})
    assert res.status_code == 200
    assert "No VA match" in res.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_va_pricing.py::test_lookup_code_autofills_from_va -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Implement the endpoint**

```python
# src/palcp_web/routers/lookup.py
"""HTMX endpoint that resolves a procedure code against the case's linked VA
pricing table and returns out-of-band input swaps that preload the item form.

Nothing is persisted here; the planner reviews the auto-filled values and submits
the form. Unmatched codes return a visible 'no match' notice (never a guess)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CareItemRow, User
from ..security import current_user
from ..services import GROWTH_KEYS, _care_item, pricing_table_from_case
from ..templating import render_partial
from palcp.pricing.lookup import resolve_item
from .cases import get_owned_case

router = APIRouter()


@router.get("/cases/{case_id}/lookup-code")
def lookup_code(case_id: int, request: Request, code: str, code_type: str = "",
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    table = pricing_table_from_case(case)
    probe = _care_item(CareItemRow(
        category="", item="probe", code=code, code_type=code_type,
        geographic_basis=case.geo_zip3 or "", unit_cost=0.0,
        percentile=case.percentile_policy))
    res = resolve_item(probe, table)
    # The resolution mutates nothing; build display values for the form.
    matched = res.method == "matched" and res.record is not None
    return render_partial(request, "cases/_item_autofill.html",
                          matched=matched, res=res, rec=res.record,
                          growth_keys=GROWTH_KEYS, code=code)
```

Note: `_care_item` needs the growth/description auto-fill, so call `apply_pricing` instead to fill the probe. Adjust the body to:

```python
    from palcp.pricing import apply_pricing
    apply_pricing([probe], table)
    matched = bool(probe.unit_cost and probe.unit_cost > 0)
    return render_partial(request, "cases/_item_autofill.html",
                          matched=matched, item=probe,
                          growth_keys=GROWTH_KEYS, code=code)
```

- [ ] **Step 4: Create the OOB-swap fragment**

```html
<!-- src/palcp_web/templates/cases/_item_autofill.html -->
{% if matched %}
<input id="f_unit_cost" name="unit_cost" value="{{ '%.2f'|format(item.unit_cost) }}" hx-swap-oob="true">
<input id="f_description" name="description" value="{{ item.description }}" hx-swap-oob="true">
<input id="f_code_type" name="code_type" value="{{ item.code_type }}" hx-swap-oob="true">
<input id="f_pricing_source" name="pricing_source" value="{{ item.pricing_source }}" hx-swap-oob="true">
<input id="f_percentile" name="percentile" value="{{ item.percentile if item.percentile is not none else '' }}" hx-swap-oob="true">
<input id="f_geographic_basis" name="geographic_basis" value="{{ item.geographic_basis }}" hx-swap-oob="true">
<input id="f_retrieval_date" name="retrieval_date" value="{{ item.retrieval_date }}" hx-swap-oob="true">
<input id="f_category" name="category" value="{{ item.category }}" hx-swap-oob="true">
<select id="f_growth_key" name="growth_key" hx-swap-oob="true">
  {% for k in growth_keys %}<option value="{{ k }}" {{ "selected" if item.growth_key == k }}>{{ k }}</option>{% endfor %}
</select>
<span id="lookup-status" class="small" hx-swap-oob="true">✓ Priced from {{ item.pricing_source }} ({{ item.geographic_basis or "national" }}) — {{ item.unit_cost | money }}</span>
{% else %}
<span id="lookup-status" class="small b-warn" hx-swap-oob="true">No VA match for code “{{ code }}”. Enter a direct cost/source, or flag for a vendor survey.</span>
{% endif %}
```

- [ ] **Step 5: Register the router in `src/palcp_web/main.py`**

```python
from .routers import auth, cases, items, lookup, pricing, rates, reports
# ...
for r in (auth.router, cases.router, items.router, lookup.router, pricing.router,
          rates.router, reports.router):
    app.include_router(r)
```

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_web_va_pricing.py -k lookup -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/palcp_web/routers/lookup.py src/palcp_web/templates/cases/_item_autofill.html src/palcp_web/main.py tests/test_web_va_pricing.py
git commit -m "feat(web): /lookup-code HTMX auto-fill from VA table at case locality"
```

---

## Task 9: Wire HTMX into the item forms + ZIP3 in the case form

**Files:**
- Modify: `src/palcp_web/templates/cases/_items_section.html`
- Modify: `src/palcp_web/templates/cases/item_form.html`
- Modify: `src/palcp_web/templates/cases/form.html`
- Modify: `src/palcp_web/services.py` (geo into `_care_item`)
- Modify: `src/palcp_web/routers/cases.py` (persist ZIP3 in `_apply_assumptions`)
- Test: manual + existing web tests

- [ ] **Step 1: Add ZIP3 to the case form**

In `src/palcp_web/templates/cases/form.html`, in the claimant/residence area, add:

```html
<div><label>Claimant residence ZIP (3-digit)</label>
  <input name="geo_zip3" maxlength="3" value="{{ case.geo_zip3 if case else '' }}"
         placeholder="e.g. 191 (Philadelphia)"></div>
<div><label>Locality name (optional)</label>
  <input name="geo_locality_name" value="{{ case.geo_locality_name if case else '' }}"></div>
```

- [ ] **Step 2: Persist ZIP3 — modify `_apply_assumptions` in `cases.py`**

After the `case.residence = clean(form.get("residence"))` line, add:

```python
    case.geo_zip3 = clean(form.get("geo_zip3"))[:3]
    case.geo_locality_name = clean(form.get("geo_locality_name"))
```

- [ ] **Step 3: Default the item's geographic basis from the case ZIP3 — modify `_care_item`**

`_care_item(row)` builds a `CareItem`. Change `geographic_basis=row.geographic_basis` to fall back to the case ZIP3. Since `_care_item` only sees the row, pass the case ZIP3 through `plan_from_case` (which builds items): in `plan_from_case`, replace `items=[_care_item(r) for r in case.items]` with `items=[_care_item(r, case.geo_zip3) for r in case.items]` and update the signature:

```python
def _care_item(row: CareItemRow, geo_zip3: str = "") -> CareItem:
    return CareItem(
        ...
        geographic_basis=row.geographic_basis or geo_zip3,
        ...
    )
```

Update the `lookup.py` call (`_care_item(...)` probe) to pass `case.geo_zip3` if it uses `_care_item` directly. (In Task 8 final body we used `apply_pricing` on a probe whose `geographic_basis` we set explicitly to `case.geo_zip3`, so no change needed there.)

- [ ] **Step 4: Add field ids + HTMX trigger to the add-item form**

In `src/palcp_web/templates/cases/_items_section.html`, give the relevant inputs the ids referenced by the OOB fragment and wire the code input. Replace the add-form fields with id-bearing versions, and on the code input add:

```html
<div><label>Code (CPT/HCPCS)</label>
  <input name="code" id="f_code"
         hx-get="/cases/{{ case.id }}/lookup-code"
         hx-trigger="change, keyup changed delay:600ms"
         hx-include="this" hx-target="#lookup-sink" hx-swap="innerHTML"></div>
```

Add ids `f_unit_cost`, `f_description`, `f_code_type`, `f_pricing_source`, `f_percentile`, `f_geographic_basis`, `f_retrieval_date`, `f_category`, and make the growth select `id="f_growth_key"`. Add a status span and an empty sink for the swap response:

```html
<span id="lookup-status" class="small muted"></span>
<div id="lookup-sink" style="display:none"></div>
```

(The OOB swaps in `_item_autofill.html` target the `f_*` ids directly; `#lookup-sink` just absorbs the non-OOB part of the response.)

- [ ] **Step 5: Mirror the wiring in the edit form**

Apply the same ids + `hx-get` on the code input in `src/palcp_web/templates/cases/item_form.html` (using `/cases/{{ case.id }}/lookup-code`), so editing an item can re-pull the VA price.

- [ ] **Step 6: Verify nothing broke server-side**

Run: `pytest tests/test_web.py tests/test_web_va_pricing.py -q`
Expected: PASS (templates render; add/edit still post all fields).

- [ ] **Step 7: Commit**

```bash
git add src/palcp_web/templates/cases/_items_section.html src/palcp_web/templates/cases/item_form.html src/palcp_web/templates/cases/form.html src/palcp_web/services.py src/palcp_web/routers/cases.py
git commit -m "feat(web): HTMX code lookup in item forms + per-case ZIP3"
```

---

## Task 10: Catalog browse + one-click add

**Files:**
- Create: `src/palcp_web/routers/catalog.py`
- Create: `src/palcp_web/templates/catalog/list.html`
- Modify: `src/palcp_web/main.py` (register router)
- Modify: `src/palcp_web/templates/cases/detail.html` (link to catalog)
- Test: `tests/test_web_va_pricing.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_web_va_pricing.py
def test_catalog_add_creates_priced_row():
    c = TestClient(app)
    _register(c, "cat@example.com")
    r = c.post("/cases", data={"name": "Cat Case"})
    cid = int(str(r.url).rstrip("/").split("/")[-1])
    c.post(f"/cases/{cid}", data={"name": "Cat Case", "age_at_report": "40",
                                  "le_additional_years": "30", "geo_zip3": "191"})
    # browse
    assert "Physiatry" in c.get(f"/cases/{cid}/catalog").text
    # add the PM&R follow-up
    r = c.post(f"/cases/{cid}/catalog/add", data={"key": "pmr_followup"})
    assert r.status_code in (200, 303)
    detail = c.get(f"/cases/{cid}").text
    assert "99214" in detail            # code carried in
    assert "$200" in detail or "200.00" in detail  # auto-priced from VA SAMPLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_va_pricing.py::test_catalog_add_creates_priced_row -v`
Expected: FAIL — 404 on `/cases/{id}/catalog`.

- [ ] **Step 3: Implement the router**

```python
# src/palcp_web/routers/catalog.py
"""Browse the curated common-items catalog and add a fully-coded, auto-priced
care item to a case in one click."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from palcp.catalog import load_catalog, search
from ..db import get_db
from ..forms import clean
from ..models import CareItemRow, User
from ..security import current_user, record_audit
from ..services import compute_case
from ..templating import flash, render
from .cases import get_owned_case
from .items import _items_section  # reuse the items-table partial renderer

router = APIRouter()


@router.get("/cases/{case_id}/catalog")
def browse_catalog(case_id: int, request: Request, q: str = "",
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    return render(request, "catalog/list.html", user=user, case=case,
                  entries=search(q), q=q)


@router.post("/cases/{case_id}/catalog/add")
def add_from_catalog(case_id: int, request: Request, key: str = Form(...),
                     user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    case = get_owned_case(db, user, case_id)
    entry = next((e for e in load_catalog() if e["key"] == key), None)
    if entry is None:
        flash(request, "Unknown catalog item.", "error")
        return RedirectResponse(f"/cases/{case.id}/catalog", status_code=303)
    sort_order = max((i.sort_order for i in case.items), default=0) + 1
    row = CareItemRow(
        case_id=case.id, sort_order=sort_order,
        category=entry.get("category", "Uncategorized"),
        item=entry["label"], code=entry.get("code", ""),
        code_type=entry.get("code_type", ""),
        growth_key=entry.get("growth_key", "medical_services"),
        frequency_per_year=entry.get("typical_frequency"),
        every_n_years=entry.get("every_n_years"),
        notes=entry.get("note", ""),
        geographic_basis=case.geo_zip3 or "")
    db.add(row)
    db.flush()
    record_audit(db, user_id=user.id, case_id=case.id, entity="item",
                 entity_id=row.id, action="create",
                 summary=f"Added '{row.item}' from catalog")
    db.commit()
    flash(request, f"Added '{row.item}' — priced from VA at save/compute.",
          "success")
    return RedirectResponse(f"/cases/{case.id}", status_code=303)
```

Note: pricing is applied at `compute_case` time (which `case_detail` calls on
render), so the added row shows its VA price immediately on the case page.

- [ ] **Step 4: Create the catalog template**

```html
<!-- src/palcp_web/templates/catalog/list.html -->
{% extends "base.html" %}
{% block title %}Common items{% endblock %}
{% block content %}
<h1>Common LCP items — {{ case.name }}</h1>
<p class="small muted">One click adds a fully-coded line; the price is pulled from
the VA library at this case's locality ({{ case.geo_zip3 or "set a ZIP on the case" }}).</p>
<form method="get" action="/cases/{{ case.id }}/catalog" class="actions">
  <input name="q" value="{{ q }}" placeholder="search e.g. MRI, 97110, wheelchair">
  <button class="btn secondary">Search</button>
  <a class="btn secondary" href="/cases/{{ case.id }}">Back to case</a>
</form>
<table>
  <thead><tr><th>Item</th><th>Category</th><th>Code</th><th>Growth</th><th></th></tr></thead>
  <tbody>
  {% for e in entries %}
    <tr>
      <td>{{ e.label }}</td><td class="small">{{ e.category }}</td>
      <td class="small">{{ e.code }} ({{ e.code_type }})</td>
      <td class="small">{{ e.growth_key }}</td>
      <td>
        <form method="post" action="/cases/{{ case.id }}/catalog/add">
          <input type="hidden" name="key" value="{{ e.key }}">
          <button class="btn small" type="submit">Add</button>
        </form>
      </td>
    </tr>
  {% else %}
    <tr><td colspan="5" class="muted">No matches.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Register router + add a link from the case page**

In `main.py` add `catalog` to the import and the include loop. In
`cases/detail.html`, near the "Add care item" area, add:
`<a class="btn secondary" href="/cases/{{ case.id }}/catalog">+ Add from common items</a>`

- [ ] **Step 6: Run the tests**

Run: `pytest tests/test_web_va_pricing.py::test_catalog_add_creates_priced_row -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/palcp_web/routers/catalog.py src/palcp_web/templates/catalog/list.html src/palcp_web/main.py src/palcp_web/templates/cases/detail.html tests/test_web_va_pricing.py
git commit -m "feat(web): common-items catalog with one-click auto-priced add"
```

---

## Task 11: Fetch/ingest script, disclosure, gitignore, docs, end-to-end

**Files:**
- Create: `scripts/fetch_va_charges.py`
- Modify: `.gitignore`
- Modify: `src/palcp/workbook/content.py` (Data Sources disclosure)
- Modify: `README.md`, `docs/DATA_SCHEMA.md`
- Test: manual run + full suite

- [ ] **Step 1: Write the fetch/ingest script**

```python
# scripts/fetch_va_charges.py
"""Refresh the VA Reasonable Charges data the tool prices from.

Usage:
  # ingest the official outpatient/professional workbook you downloaded
  python scripts/fetch_va_charges.py --outpatient ~/Downloads/va_outpatient.xlsx \
      --version v5.26 --effective 2026-01-01 --out data/va_charges_normalized.csv

  # also cache the public inpatient + data-sources files for citations
  python scripts/fetch_va_charges.py --fetch-public --out-dir data/va_public

The normalized CSV (gitignored) is picked up automatically by the web app's
ensure_default_va_library(). Without --outpatient the app falls back to the
labeled SAMPLE seed.
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from pathlib import Path

PUBLIC_FILES = {
    "inpatient_table_a_v5-25.xlsx":
        "https://www.va.gov/COMMUNITYCARE/docs/RO/Inpatient-DataTables/v5-25-Table-A.xlsx",
    "inpatient_table_b_v5-25.xlsx":
        "https://www.va.gov/COMMUNITYCARE/docs/RO/Inpatient-DataTables/v5-25-Table-B.xlsx",
}


def _ingest_outpatient(path: str, version: str, effective: str, out: str) -> int:
    from palcp.pricing.va import load_va_outpatient
    table = load_va_outpatient(path, version=version, effective_date=effective)
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "code", "code_type", "description", "amount",
                    "percentile", "geographic_area", "effective_date", "citation_url"])
        for r in table.records:
            w.writerow([r.source, r.code, r.code_type, r.description, r.amount,
                        r.percentile if r.percentile is not None else "",
                        r.geographic_area, r.effective_date, r.citation_url])
    return len(table.records)


def _fetch_public(out_dir: str) -> None:
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    for name, url in PUBLIC_FILES.items():
        print(f"downloading {name} ...")
        urllib.request.urlretrieve(url, d / name)  # noqa: S310 (trusted gov URL)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outpatient", help="path to official VA outpatient .xlsx")
    ap.add_argument("--version", default="v5.26")
    ap.add_argument("--effective", default="2026-01-01")
    ap.add_argument("--out", default="data/va_charges_normalized.csv")
    ap.add_argument("--fetch-public", action="store_true")
    ap.add_argument("--out-dir", default="data/va_public")
    args = ap.parse_args(argv)

    if args.fetch_public:
        _fetch_public(args.out_dir)
    if args.outpatient:
        n = _ingest_outpatient(args.outpatient, args.version, args.effective, args.out)
        print(f"wrote {n} VA charge rows -> {args.out}")
    if not args.fetch_public and not args.outpatient:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Gitignore the official/normalized data**

Append to `.gitignore`:

```
# Official VA Reasonable Charges data (CPT is AMA-copyrighted; do not commit)
data/va_charges_normalized.csv
data/va_public/
*va_outpatient*.xlsx
```

- [ ] **Step 3: Disclose VA version + locality in the workbook**

In `src/palcp/workbook/content.py`, add a helper that the builder can call to append a Data Sources note. Add:

```python
def va_disclosure(version: str = "", effective_date: str = "",
                  locality: str = "") -> str:
    parts = ["VA Reasonable Charges"]
    if version:
        parts.append(version)
    if effective_date:
        parts.append(f"effective {effective_date}")
    base = " ".join(parts)
    loc = f"locality ZIP {locality}" if locality else "national base (GAAF not applied)"
    return (f"{base}; {loc}. Public U.S. Department of Veterans Affairs "
            f"outpatient/professional reasonable charges. CPT© AMA.")
```

(Wire it into the Data Sources tab where source notes are emitted; keep it
additive — the existing `content.py` source-notes list is the insertion point.)

- [ ] **Step 4: Document in README + DATA_SCHEMA**

Add a "VA Reasonable Charges (default pricing)" section to `README.md` explaining:
the app ships a labeled SAMPLE; run `scripts/fetch_va_charges.py --outpatient …`
with the official file (downloaded after accepting the CPT disclaimer) to load
real prices; the normalized CSV is gitignored; CPT is AMA-copyrighted and the
firm's CPT license governs internal use. Add the per-case ZIP3 + catalog to
`docs/DATA_SCHEMA.md`.

- [ ] **Step 5: Run the entire test suite**

Run: `pytest -q`
Expected: PASS (all engine + web tests).

- [ ] **Step 6: Manual smoke (browser)**

```bash
# restart the dev server (Task already has a venv)
pkill -f "uvicorn palcp_web" 2>/dev/null
SECRET_KEY=dev SESSION_HTTPS_ONLY=0 .venv/bin/uvicorn palcp_web.main:app --port 8000 &
```
Then verify: create a case → set ZIP 191 → open "Add from common items" → add
"MRI lumbar" → confirm it shows a VA SAMPLE price and a ✓ provenance line; type
`99214` in the add-item code box → confirm fields auto-fill. Capture a screenshot.

- [ ] **Step 7: Commit**

```bash
git add scripts/fetch_va_charges.py .gitignore src/palcp/workbook/content.py README.md docs/DATA_SCHEMA.md
git commit -m "feat: VA fetch/ingest script, workbook disclosure, docs, gitignore"
```

---

## Self-review

**Spec coverage:**
- §4.1 VA ingestion → Tasks 3, 11. §4.2 geo/ZIP3 → Tasks 4, 6, 9. §4.3 extended auto-fill → Task 2. §4.4 growth mapper → Task 1. §4.5 system default library → Tasks 6, 7. §4.6 `/lookup-code` → Tasks 8, 9. §4.7 catalog → Tasks 5, 10. §6 defensibility (no fabrication, disclosure) → Tasks 4 (unresolved), 7 (SAMPLE label), 11 (disclosure). §7 licensing → Task 11 (gitignore/docs). §8 testing → every task. §9 migration → Task 6.
- All spec sections map to at least one task. No gaps.

**Placeholder scan:** No "TBD/TODO/handle edge cases". Every code step shows real code; every test step shows real assertions.

**Type/name consistency:** `growth_key_for`/`category_hint` (Task 1) used identically in Tasks 2 & 8. `load_va_outpatient(path, *, version, effective_date, sheet)` + `SEED_PATH` (Task 3) used in Tasks 7 & 11. `ensure_default_va_library(db)` (Task 7) used in Tasks 7 & 8 startup. `_care_item(row, geo_zip3="")` signature change (Task 9) is backward-compatible (default arg) so Task 8's probe path is unaffected. OOB ids `f_unit_cost/.../f_growth_key` defined in Task 8 fragment match the ids added to the forms in Task 9.

**Note for executor:** Tasks 1–5 are pure engine work (parallelizable). Tasks 6→7→8→9→10 are web and have a dependency order (migration/models → default library → lookup → form wiring → catalog). Task 11 is last. The `_care_item` probe in Task 8 sets `geographic_basis=case.geo_zip3` explicitly, so it does not depend on Task 9's signature change.

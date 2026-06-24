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

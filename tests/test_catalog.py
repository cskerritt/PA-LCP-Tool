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

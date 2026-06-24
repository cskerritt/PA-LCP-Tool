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

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


def _is_attendant_cpt(num: int) -> bool:
    """CPT home-visit / care-in-residence range (99500-99602)."""
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

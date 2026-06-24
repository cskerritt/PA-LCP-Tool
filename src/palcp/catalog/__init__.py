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
    """Case-insensitive match on label, code, category, key, or note. Empty -> all."""
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

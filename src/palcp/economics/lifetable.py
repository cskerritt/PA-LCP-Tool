"""Optional life-expectancy lookup from a *user-supplied, published* life table.

This module deliberately ships **no** embedded mortality numbers.  Life
expectancy drives the entire valuation, so the figure must trace to a verifiable
published source the analyst can cite and defend (e.g. CDC/NCHS *United States
Life Tables*) -- or, where the injury shortens lifespan, to a qualified medical
or mortality opinion (per *Anderson-Moody* / *Gunn*).  Hard-coding numbers here
would invite a transcription error into evidence; instead we read a table the
analyst provides and preserve its source citation.

Expected CSV columns (header row, case-insensitive)::

    age, sex, ex, source, citation_url, as_of

* ``age``  -- integer age in years
* ``sex``  -- ``total`` | ``male`` | ``female`` (matched case-insensitively)
* ``ex``   -- expectation of remaining life at that age, in years
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..models import LifeExpectancy


@dataclass
class _Row:
    age: int
    sex: str
    ex: float
    source: str
    citation_url: str
    as_of: str


class LifeTable:
    """An in-memory life table loaded from CSV."""

    def __init__(self, rows: list[_Row]):
        self._rows = rows

    @classmethod
    def from_csv(cls, path: str | Path) -> "LifeTable":
        rows: list[_Row] = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            lower = {f.lower(): f for f in (reader.fieldnames or [])}
            required = {"age", "sex", "ex"}
            missing = required - set(lower)
            if missing:
                raise ValueError(
                    f"Life table {path} is missing column(s): {sorted(missing)}"
                )
            for raw in reader:
                rows.append(
                    _Row(
                        age=int(float(raw[lower["age"]])),
                        sex=str(raw[lower["sex"]]).strip().lower(),
                        ex=float(raw[lower["ex"]]),
                        source=str(raw.get(lower.get("source", ""), "") or ""),
                        citation_url=str(raw.get(lower.get("citation_url", ""), "") or ""),
                        as_of=str(raw.get(lower.get("as_of", ""), "") or ""),
                    )
                )
        if not rows:
            raise ValueError(f"Life table {path} contained no data rows.")
        return cls(rows)

    def lookup(self, age: int, sex: str = "total") -> Optional[_Row]:
        sex = (sex or "total").strip().lower()
        # Exact (age, sex) first, then fall back to the closest age for that sex.
        candidates = [r for r in self._rows if r.sex == sex]
        if not candidates:
            candidates = self._rows
        exact = [r for r in candidates if r.age == int(age)]
        if exact:
            return exact[0]
        return min(candidates, key=lambda r: abs(r.age - int(age)), default=None)

    def life_expectancy(
        self, age_at_report: float, sex: str = "total"
    ) -> LifeExpectancy:
        """Build a :class:`~palcp.models.LifeExpectancy` from the table."""
        row = self.lookup(int(round(age_at_report)), sex)
        if row is None:
            raise ValueError(
                f"No life-table row for age={age_at_report} sex={sex!r}."
            )
        return LifeExpectancy(
            age_at_report=age_at_report,
            additional_years=row.ex,
            source=row.source,
            citation_url=row.citation_url,
            as_of=row.as_of,
            note=f"Period life table, {row.sex}, age {row.age}.",
        )

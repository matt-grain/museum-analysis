"""Population SPARQL-row parsing helpers (split out from wikidata_client for size)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PopulationPoint:
    """A single (year, population) data point for a city."""

    year: int
    population: int


_OUTLIER_RATIO = 2.0


def filter_scope_outliers(year_to_pop: dict[int, int]) -> dict[int, int]:
    """Drop values >2x the series minimum.

    Wikidata P1082 can mix admin-boundary, urban-area, and metro-area scopes
    across years (e.g., Tokyo Q1490 reports ~14M admin + ~38M metro). Real
    populations don't swing 2x year-over-year, so anything that does is a
    geographic-scope mismatch. Anchoring on MIN (not median) biases toward
    the smallest scope — usually the admin-boundary figure, which is what
    we want for "city population."

    Passes the series through unchanged when <3 points or when the series
    is already internally consistent (max/min <= 2x).
    """
    if len(year_to_pop) < 3:
        return year_to_pop
    values = year_to_pop.values()
    lo, hi = min(values), max(values)
    if hi <= lo * _OUTLIER_RATIO:
        return year_to_pop
    cutoff = lo * _OUTLIER_RATIO
    return {y: p for y, p in year_to_pop.items() if p <= cutoff}


def _val(binding: dict[str, Any], key: str) -> str | None:
    entry = binding.get(key)
    return str(entry.get("value", "")) if entry is not None else None


def _extract_qid(uri: str | None) -> str | None:
    return uri.split("/")[-1] if uri else None


def parse_populations(bindings: list[dict[str, Any]]) -> dict[str, list[PopulationPoint]]:
    """Group SPARQL rows by city QID, filter scope outliers, sort by year."""
    raw: dict[str, dict[int, int]] = {}
    for row in bindings:
        city_qid = _extract_qid(_val(row, "city")) or ""
        year_str, pop_str = _val(row, "year"), _val(row, "population")
        if not year_str or not pop_str:
            continue
        yr, pop = int(year_str), int(float(pop_str))
        raw.setdefault(city_qid, {})
        # MIN on same-(city,year) dups biases toward admin-boundary over
        # metro-area when both are present in a single year.
        existing = raw[city_qid].get(yr)
        raw[city_qid][yr] = pop if existing is None else min(existing, pop)
    filtered = {qid: filter_scope_outliers(pts) for qid, pts in raw.items()}
    return {
        qid: [PopulationPoint(year=y, population=p) for y, p in sorted(pts.items())] for qid, pts in filtered.items()
    }

"""City response DTOs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PopulationPointOut(BaseModel):
    year: int
    population: int

    model_config = ConfigDict(from_attributes=True)


class CityPopulationsOut(BaseModel):
    id: int
    name: str
    wikidata_qid: str
    country: str | None
    population_history: list[PopulationPointOut]

    model_config = ConfigDict(from_attributes=True)

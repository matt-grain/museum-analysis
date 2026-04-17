"""Museum response DTOs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from museums.schemas.common import PaginationMeta


class VisitorRecordOut(BaseModel):
    year: int
    visitors: int

    model_config = ConfigDict(from_attributes=True)


class MuseumOut(BaseModel):
    id: int
    name: str
    wikipedia_title: str
    wikidata_qid: str | None
    city_name: str | None
    country: str | None
    visitor_records: list[VisitorRecordOut]

    model_config = ConfigDict(from_attributes=True)

    # Pydantic model_validator(mode="before") receives raw pre-validation input
    # (ORM instance or dict). Any is the documented type.
    @model_validator(mode="before")
    @classmethod
    def _flatten_city_name(cls, data: Any) -> Any:
        """Flatten city.name into city_name when building from ORM attributes."""
        if hasattr(data, "city"):
            city = data.city
            return {
                "id": data.id,
                "name": data.name,
                "wikipedia_title": data.wikipedia_title,
                "wikidata_qid": data.wikidata_qid,
                "city_name": city.name if city is not None else None,
                "country": data.country,
                "visitor_records": list(data.visitor_records),
            }
        return data


class PaginatedMuseumsOut(BaseModel):
    items: list[MuseumOut]
    pagination: PaginationMeta

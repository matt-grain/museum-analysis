"""Unit tests for MuseumOut schema — model_validator and city_name flattening."""

from __future__ import annotations

from unittest.mock import MagicMock

from museums.schemas.museum import MuseumOut


def _make_city_mock(city_name: str) -> MagicMock:
    """Return a mock that behaves like a City ORM object."""
    city = MagicMock()
    city.name = city_name  # set attribute directly to avoid MagicMock(name=...) pitfall
    return city


def _make_orm_museum(city_name: str | None = "Paris") -> MagicMock:
    """Build a mock ORM Museum object with the expected attribute shape."""
    mock = MagicMock()
    mock.id = 1
    mock.name = "Louvre"
    mock.wikipedia_title = "Louvre"
    mock.wikidata_qid = "Q19675"
    mock.country = "France"
    mock.visitor_records = []
    mock.city = _make_city_mock(city_name) if city_name is not None else None
    return mock


def test_museum_out_flattens_city_name_from_orm_object_with_city() -> None:
    # Arrange
    orm_museum = _make_orm_museum(city_name="Paris")

    # Act
    result = MuseumOut.model_validate(orm_museum, from_attributes=True)

    # Assert
    assert result.city_name == "Paris"
    assert result.name == "Louvre"


def test_museum_out_returns_none_city_name_when_city_is_none() -> None:
    # Arrange
    orm_museum = _make_orm_museum(city_name=None)

    # Act
    result = MuseumOut.model_validate(orm_museum, from_attributes=True)

    # Assert
    assert result.city_name is None


def test_museum_out_passes_plain_dict_through() -> None:
    # Arrange
    data: dict[str, object] = {
        "id": 1,
        "name": "Louvre",
        "wikipedia_title": "Louvre",
        "wikidata_qid": "Q19675",
        "city_name": "Paris",
        "country": "France",
        "visitor_records": [],
    }

    # Act
    result = MuseumOut.model_validate(data)

    # Assert
    assert result.id == 1
    assert result.name == "Louvre"
    assert result.city_name == "Paris"
    assert result.visitor_records == []

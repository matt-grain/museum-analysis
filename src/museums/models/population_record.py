"""PopulationRecord ORM model — per-year population datapoint for a city."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from museums.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from museums.models.city import City


class PopulationRecord(Base, TimestampMixin):
    """One row per (city, year) population datapoint from Wikidata."""

    __tablename__ = "population_records"

    __table_args__ = (
        UniqueConstraint("city_id", "year", name="uq_population_records_city_year"),
        CheckConstraint("year >= 2000 AND year <= 2100", name="ck_population_records_year_range"),
        CheckConstraint("population > 0", name="ck_population_records_population_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id", ondelete="CASCADE"), index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    population: Mapped[int] = mapped_column(BigInteger, nullable=False)

    city: Mapped[City] = relationship(back_populates="population_records")

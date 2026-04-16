"""City ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from museums.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from museums.models.museum import Museum
    from museums.models.population_record import PopulationRecord


class City(Base, TimestampMixin):
    """One row per unique city referenced by at least one museum."""

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    wikidata_qid: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(200))

    population_records: Mapped[list[PopulationRecord]] = relationship(
        back_populates="city", cascade="all, delete-orphan"
    )
    museums: Mapped[list[Museum]] = relationship(back_populates="city")

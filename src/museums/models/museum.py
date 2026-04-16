"""Museum ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from museums.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from museums.models.city import City
    from museums.models.visitor_record import VisitorRecord


class Museum(Base, TimestampMixin):
    """One row per Wikipedia-listed museum."""

    __tablename__ = "museums"

    id: Mapped[int] = mapped_column(primary_key=True)
    wikidata_qid: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    wikipedia_title: Mapped[str] = mapped_column(String(300), nullable=False)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id", ondelete="SET NULL"), index=True)
    country: Mapped[str | None] = mapped_column(String(200))

    city: Mapped[City | None] = relationship(back_populates="museums")
    visitor_records: Mapped[list[VisitorRecord]] = relationship(back_populates="museum", cascade="all, delete-orphan")

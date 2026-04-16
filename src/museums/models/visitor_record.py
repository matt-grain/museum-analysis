"""VisitorRecord ORM model — per-year visitor count for a museum."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from museums.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from museums.models.museum import Museum


class VisitorRecord(Base, TimestampMixin):
    """One row per (museum, year) visitor count from Wikidata."""

    __tablename__ = "visitor_records"

    __table_args__ = (
        UniqueConstraint("museum_id", "year", name="uq_visitor_records_museum_year"),
        CheckConstraint("year >= 2000 AND year <= 2100", name="ck_visitor_records_year_range"),
        CheckConstraint("visitors > 0", name="ck_visitor_records_visitors_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    museum_id: Mapped[int] = mapped_column(ForeignKey("museums.id", ondelete="CASCADE"), index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    visitors: Mapped[int] = mapped_column(BigInteger, nullable=False)

    museum: Mapped[Museum] = relationship(back_populates="visitor_records")

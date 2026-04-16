"""RefreshState ORM model — singleton tracking last data refresh."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from museums.models.base import Base


class RefreshState(Base):
    """Singleton row (id=1) tracking when data was last refreshed."""

    __tablename__ = "refresh_state"

    __table_args__ = (CheckConstraint("id = 1", name="ck_refresh_state_singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_museums_count: Mapped[int | None]
    last_refresh_cities_count: Mapped[int | None]

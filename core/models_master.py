"""
Masterdatabasen (F0-04, B-004): registret över bolagen och vilken databas varje bolag har.

Användarna ligger i bolagens egna databaser, som i PE Portal (B-006). Ett bolag hittas vid inloggningen via
Entra-katalogens id (`entra_tenant_id`).
"""

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db_routing import MASTER_BIND
from core.timeutil import utcnow
from extensions import db


class Tenant(db.Model):  # type: ignore[name-defined]
    """Ett bolag på plattformen, med en egen databas."""

    __tablename__ = 'tenants'
    __bind_key__ = MASTER_BIND

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    database_url: Mapped[str] = mapped_column(Text, nullable=False)
    entra_tenant_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    def __repr__(self) -> str:
        return f'<Tenant {self.slug}>'

"""Tid: UTC i databasen (timestamptz), lokal tid i gränssnittet (backend-grund 12)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)

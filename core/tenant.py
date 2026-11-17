"""
Bolagsval och schemahjälp (F0-04). Förlaga: pe-portal/core/tenant.py.

Uppslaget av bolag vid inloggning (via Entra-katalogens id) kommer i F0-13. Här finns det som behövs för att köra kod
mot ett visst bolags databas.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flask import g

from core.db_routing import MASTER_BIND, get_engine
from extensions import db


@contextmanager
def tenant_context(tenant: Any) -> Iterator[None]:
    """Kör kod mot ett bolags databas. Tar ett Tenant-objekt eller en databas-URL."""
    database_url = getattr(tenant, 'database_url', tenant)
    previous_url = g.get('tenant_database_url')
    previous_tenant = g.get('tenant')
    db.session.remove()
    g.tenant_database_url = database_url
    g.tenant = tenant if hasattr(tenant, 'slug') else None
    try:
        yield
    finally:
        db.session.remove()
        g.tenant_database_url = previous_url
        g.tenant = previous_tenant


def create_master_schema() -> None:
    """Masterdatabasens tabeller direkt från modellerna — ENDAST för prov mot SQLite. Riktiga databaser byggs med
    migrationerna (core/migrations.py)."""
    db.metadatas[MASTER_BIND].create_all(bind=db.engines[MASTER_BIND])


def create_tenant_schema(database_url: str) -> None:
    """Bolagsdatabasens tabeller direkt från modellerna — ENDAST för prov mot SQLite."""
    db.metadata.create_all(bind=get_engine(database_url))

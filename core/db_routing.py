"""
Dirigerar varje databasfråga till rätt bolagsdatabas (F0-04, B-004). Förlaga: pe-portal/core/db_routing.py.

Mastermodellerna är märkta med `__bind_key__ = 'master'` och går alltid till masterdatabasen. Alla andra modeller
dirigeras till den bolagsdatabas som är vald för anropet (`core.tenant.tenant_context`). Finns ingen vald, kastas ett
fel i stället för att frågan går till fel bolag.

Modulen importerar varken `extensions` eller några modeller, så att `extensions.py` kan använda den.
"""

import os
import sqlite3
import threading
from typing import Any

from flask import g, has_app_context
from flask_sqlalchemy.session import Session as FlaskSQLAlchemySession
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

MASTER_BIND = 'master'

TENANT_POOL_SIZE = int(os.environ.get('TENANT_POOL_SIZE', '4'))
MASTER_POOL_SIZE = int(os.environ.get('MASTER_POOL_SIZE', '2'))

_engines: dict[str, Engine] = {}
_engine_lock = threading.Lock()


@event.listens_for(Engine, 'connect')
def _sqlite_foreign_keys(dbapi_connection: Any, connection_record: Any) -> None:
    """SQLite upprätthåller inte främmande nycklar om man inte ber om det. Utan detta går en radering igenom i proven
    som PostgreSQL stoppar (backend-grund 9)."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.execute('PRAGMA foreign_keys=ON')


def _engine_options(database_url: str) -> dict[str, Any]:
    if database_url.startswith('sqlite'):
        return {'pool_pre_ping': True}
    return {'pool_size': TENANT_POOL_SIZE, 'max_overflow': 0, 'pool_pre_ping': True, 'pool_recycle': 280}


def master_engine_options(database_url: str) -> dict[str, Any]:
    if database_url.startswith('sqlite'):
        return {}
    return {'pool_size': MASTER_POOL_SIZE, 'max_overflow': 2, 'pool_pre_ping': True, 'pool_recycle': 280}


def get_engine(database_url: str) -> Engine:
    """Returnera (och cacha) en engine för en bolagsdatabas."""
    engine = _engines.get(database_url)
    if engine is not None:
        return engine
    with _engine_lock:
        engine = _engines.get(database_url)
        if engine is None:
            engine = create_engine(database_url, **_engine_options(database_url))
            _engines[database_url] = engine
    return engine


def dispose_engines() -> None:
    """Stäng alla bolagsanslutningar. Används av proven och administrativa kommandon."""
    with _engine_lock:
        for engine in _engines.values():
            engine.dispose()
        _engines.clear()


def current_tenant_engine() -> Engine | None:
    if not has_app_context():
        return None
    database_url = g.get('tenant_database_url')
    return get_engine(database_url) if database_url else None


def _is_master_mapper(mapper: Any) -> bool:
    """Flask-SQLAlchemy lagrar __bind_key__ på tabellens metadata, inte på tabellen."""
    table = getattr(mapper, 'local_table', None) if mapper is not None else None
    return table is not None and table.metadata.info.get('bind_key') == MASTER_BIND


class TenantSession(FlaskSQLAlchemySession):
    """Session som väljer databas utifrån vilket bolag anropet gäller."""

    def get_bind(self, mapper=None, clause=None, **kwargs):  # type: ignore[no-untyped-def]
        if _is_master_mapper(mapper):
            return super().get_bind(mapper=mapper, clause=clause, **kwargs)
        engine = current_tenant_engine()
        if engine is None:
            raise RuntimeError('Inget bolag är valt för anropet — kan inte avgöra vilken databas frågan gäller. '
                               'Använd core.tenant.tenant_context().')
        return engine

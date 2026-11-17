"""
Migrationerna mot riktig PostgreSQL (F0-04, F0-08). Körs alltid i CI (REQUIRE_PG=1).
"""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import create_engine, inspect

from core import migrations
from extensions import db


@pytest.mark.parametrize('kind', ['master', 'tenant'])
def test_migrationerna_ger_exakt_modellernas_schema(app: Flask, pg_database: Callable[[], str], kind: str) -> None:
    engine = create_engine(pg_database())
    ran = migrations.migrate(engine, kind)
    assert ran == [m.label for m in migrations.discover(kind)]
    with app.app_context():
        metadata = db.metadatas['master'] if kind == 'master' else db.metadata
    assert migrations.schema_diff(engine, metadata) == {
        'missing_tables': [], 'extra_tables': [], 'missing_columns': [], 'extra_columns': []}
    engine.dispose()


@pytest.mark.parametrize('kind', ['master', 'tenant'])
def test_aterstallningen_tar_bort_allt_och_migrationen_gar_att_kora_igen(
        pg_database: Callable[[], str], kind: str) -> None:
    engine = create_engine(pg_database())
    migrations.migrate(engine, kind)
    latest = migrations.discover(kind)[-1]
    assert migrations.rollback(engine, kind, latest.version) == latest.label
    assert set(inspect(engine).get_table_names()) == {migrations.TABLE}
    assert migrations.migrate(engine, kind) == [latest.label]
    engine.dispose()


def test_en_andrad_migration_stoppar_allt(pg_database: Callable[[], str], tmp_path: Path) -> None:
    source = Path(migrations.MIGRATIONS_DIR) / 'tenant'
    copy = tmp_path / 'tenant'
    shutil.copytree(source, copy)
    engine = create_engine(pg_database())
    migrations.migrate(engine, 'tenant', copy)
    first = sorted(copy.glob('*_baslinje.sql'))[0]
    first.write_text(first.read_text(encoding='utf-8') + '\n-- ändrad i efterhand\n', encoding='utf-8')
    with pytest.raises(migrations.MigrationError, match='ÄNDRAD'):
        migrations.migrate(engine, 'tenant', copy)
    engine.dispose()


def test_radlaset_laser_om_det_sessionen_redan_last(pg_database: Callable[[], str]) -> None:
    """Två samtidiga sessioner: den andra ska se vad den första just skrev, inte det den läste innan (F0-17)."""
    from sqlalchemy.orm import Session

    from core.locking import lock
    from models import Job
    engine = create_engine(pg_database())
    migrations.migrate(engine, 'tenant')
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO users (id, username, display_name, is_admin, active, failed_logins, "
                             "created_at) VALUES (1, 'anna', 'Anna', false, true, 0, now())")
        conn.exec_driver_sql("INSERT INTO documents (id, title, owner_id, created_at) VALUES (1, 'Offert', 1, now())")
        conn.exec_driver_sql("INSERT INTO document_versions (id, document_id, version_no, storage_key, sha256, "
                             "page_count, size_bytes, source, created_by, created_at) VALUES "
                             "(1, 1, 1, 'p/documents/1.pdf', repeat('0', 64), 1, 10, 'upload', 1, now())")
        conn.exec_driver_sql("INSERT INTO jobs (id, kind, status, version_id, requested_by, cost_sek, created_at) "
                             "VALUES (1, 'ocr', 'queued', 1, 1, 0, now())")
    with Session(engine) as first, Session(engine) as second:
        stale = first.get(Job, 1)
        assert stale is not None and stale.status == 'queued'
        job = second.get(Job, 1)
        assert job is not None
        job.status = 'running'
        second.commit()
        locked = lock(first, Job, 1)
        assert locked is stale
        assert locked.status == 'running'
        first.rollback()
    engine.dispose()


def test_frammande_nycklar_stoppar_radering_i_postgresql(pg_database: Callable[[], str]) -> None:
    engine = create_engine(pg_database())
    migrations.migrate(engine, 'tenant')
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO users (id, username, display_name, is_admin, active, failed_logins, "
                             "created_at) VALUES (1, 'anna', 'Anna', false, true, 0, now())")
        conn.exec_driver_sql("INSERT INTO documents (title, owner_id, created_at) VALUES ('Offert', 1, now())")
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.exec_driver_sql('DELETE FROM users WHERE id = 1')
    engine.dispose()

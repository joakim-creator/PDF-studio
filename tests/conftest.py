"""
Gemensam uppsättning för proven (F0-08). Förlaga: pe-portal/tests/conftest.py.

Två sorters databas:
- **SQLite** (alltid): appens beteende — åtkomst, isolering mellan bolag, villkor. Schemat och seeden byggs en gång
  per körning till en mallfil, och varje provbolag får en kopia (backend-grund 13). Främmande nycklar är påslagna.
- **PostgreSQL** (när PG_TEST_URL finns): migrationerna och schemavakten. Varje prov får en egen, nyskapad databas
  som tas bort efteråt. I CI är PostgreSQL obligatoriskt (REQUIRE_PG=1) — ett schemaprov som tyst hoppas över
  bevisar ingenting.
"""

import os
import shutil
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix='pdfstudio-prov-'))
os.environ['SECRET_KEY'] = 'prov-hemlighet'
os.environ['MASTER_DATABASE_URL'] = f'sqlite:///{(_TMP / "master.db").as_posix()}'
os.environ['PDF_LOG_REQUESTS'] = '0'

from flask import Flask  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import create_app  # noqa: E402
from core.db_routing import dispose_engines  # noqa: E402
from core.models_master import Tenant  # noqa: E402
from core.tenant import create_master_schema, create_tenant_schema, tenant_context  # noqa: E402
from extensions import db  # noqa: E402

TEMPLATE_SLUG = 'mall'
_flask_app = create_app({'TESTING': True})
_templates: dict[bool, Path] = {}


@pytest.fixture
def app() -> Iterator[Flask]:
    with _flask_app.app_context():
        create_master_schema()
    yield _flask_app


def _template(seed: bool) -> Path:
    """Mallfilen byggs färsk en gång per körning från modellerna och seeden; inget sparas i projektet."""
    if seed not in _templates:
        path = _TMP / ('mall-seed.db' if seed else 'mall-tom.db')
        url = f'sqlite:///{path.as_posix()}'
        with _flask_app.app_context():
            create_tenant_schema(url)
            if seed:
                from tests.seed import seed_all
                with tenant_context(url):
                    seed_all(TEMPLATE_SLUG)
        dispose_engines()  # filen ska vara färdigskriven och stängd innan den kopieras
        _templates[seed] = path
    return _templates[seed]


@dataclass
class TestTenant:
    __test__ = False
    slug: str
    database_url: str
    tenant_id: int

    def context(self) -> AbstractContextManager[None]:
        return tenant_context(self.database_url)


@pytest.fixture
def make_tenant(app: Flask) -> Callable[..., TestTenant]:
    """Ett provbolag med egen SQLite-databas: en kopia av mallen, med bolagets slug i lagringsnycklarna."""

    def _make(seed: bool = True) -> TestTenant:
        slug = f'prov{uuid.uuid4().hex[:8]}'
        path = _TMP / f'{slug}.db'
        url = f'sqlite:///{path.as_posix()}'
        shutil.copyfile(_template(seed), path)
        with app.app_context():
            tenant = Tenant(slug=slug, name=f'Provbolag {slug}', database_url=url)
            db.session.add(tenant)
            db.session.commit()
            t = TestTenant(slug, url, tenant.id)
            if seed:
                with t.context():
                    db.session.execute(
                        text('UPDATE document_versions SET storage_key = :slug || SUBSTR(storage_key, :cut) '
                             'WHERE storage_key LIKE :prefix'),
                        {'slug': slug, 'cut': len(TEMPLATE_SLUG) + 1, 'prefix': TEMPLATE_SLUG + '/%'})
                    db.session.commit()
        return t

    return _make


@pytest.fixture
def tenant(make_tenant: Callable[..., TestTenant]) -> TestTenant:
    return make_tenant()


@pytest.fixture
def pg_database() -> Iterator[Callable[[], str]]:
    """Fabrik för nya, tomma PostgreSQL-databaser. Tas bort efter provet."""
    admin_url = os.environ.get('PG_TEST_URL')
    if not admin_url:
        if os.environ.get('REQUIRE_PG') == '1':
            pytest.fail('PG_TEST_URL saknas men REQUIRE_PG=1 — schemaproven får inte hoppas över')
        pytest.skip('PG_TEST_URL saknas — schema- och migrationsprov körs inte (se scripts/verify.py)')

    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT')
    names: list[str] = []

    def _create() -> str:
        name = f'prov_{uuid.uuid4().hex[:12]}'
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE {name}'))
        names.append(name)
        return admin_url.rsplit('/', 1)[0] + '/' + name

    yield _create

    dispose_engines()
    with admin.connect() as conn:
        for name in names:
            conn.execute(text(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)'))
    admin.dispose()

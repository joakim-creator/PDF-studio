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
os.environ['ENTRA_CLIENT_ID'] = 'prov-klient'          # Microsoft-inloggningen prövas alltid mot låtsasklienten
os.environ['ENTRA_CLIENT_SECRET'] = 'prov-hemlighet'
os.environ.pop('GLITCHTIP_DSN', None)
os.environ['STORAGE_MODE'] = 'local'                    # proven sparar alltid lokalt, i en tillfällig mapp
os.environ['STORAGE_FOLDER'] = str(_TMP / 'filer')
os.environ.pop('TOTP_KEY', None)

from typing import Any  # noqa: E402

from flask import Flask  # noqa: E402
from flask.testing import FlaskClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from werkzeug.test import TestResponse  # noqa: E402

from app import create_app  # noqa: E402
from core.db_routing import dispose_engines  # noqa: E402
from core.models_master import Tenant  # noqa: E402
from core.tenant import create_master_schema, create_tenant_schema, tenant_context  # noqa: E402
from extensions import db  # noqa: E402

TEMPLATE_SLUG = 'mall'
_flask_app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
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
    entra_tenant_id: str

    def context(self) -> AbstractContextManager[None]:
        return tenant_context(self)   # bär både databasen och slug (lagringsnycklarna)


@pytest.fixture
def make_tenant(app: Flask) -> Callable[..., TestTenant]:
    """Ett provbolag med egen SQLite-databas: en kopia av mallen, med bolagets slug i lagringsnycklarna."""

    def _make(seed: bool = True) -> TestTenant:
        slug = f'prov{uuid.uuid4().hex[:8]}'
        path = _TMP / f'{slug}.db'
        url = f'sqlite:///{path.as_posix()}'
        shutil.copyfile(_template(seed), path)
        with app.app_context():
            tenant = Tenant(slug=slug, name=f'Provbolag {slug}', database_url=url, entra_tenant_id=str(uuid.uuid4()))
            db.session.add(tenant)
            db.session.commit()
            t = TestTenant(slug, url, tenant.id, str(tenant.entra_tenant_id))
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


def local_login(client: FlaskClient, tenant: TestTenant, username: str, password: str) -> TestResponse:
    """Lokal inloggning som i drift: lösenordet och sedan engångskoden. Nyckeln läses ur bolagets databas, som
    användaren läser den på skärmen vid registreringen. Ingen bakdörr: samma två steg."""
    response = client.post('/login', data={'tenant': tenant.slug, 'username': username, 'password': password})
    if response.status_code != 302 or not response.headers['Location'].endswith('/login/kod'):
        return response
    from sqlalchemy import select

    from core import totp
    from models import User
    with _flask_app.app_context(), tenant.context():
        stored = db.session.scalars(select(User.totp_secret).where(User.username == username)).one()
        secret = totp.decrypt(stored)
    assert secret is not None
    return client.post('/login/kod', data={'code': totp.code(secret)})


class FakeMsal:
    """Låtsas-Microsoft: ger de påståenden (claims) provet bestämt. Anropar aldrig nätet."""

    def __init__(self, claims: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.claims, self.error = claims or {}, error

    def initiate_auth_code_flow(self, scopes: list[str], redirect_uri: str, prompt: str | None = None) -> dict[str, Any]:
        return {'auth_uri': 'https://login.prov.invalid/authorize', 'state': 'prov-state'}

    def acquire_token_by_auth_code_flow(self, flow: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        if self.error:
            return {'error': self.error}
        return {'id_token_claims': self.claims}


@pytest.fixture
def microsoft(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeMsal]:
    """Ställ in vad Microsoft svarar och gå igenom flödet: microsoft(claims) och sedan /auth/microsoft."""
    from core import auth

    def _set(claims: dict[str, Any] | None = None, error: str | None = None) -> FakeMsal:
        fake = FakeMsal(claims, error)
        monkeypatch.setattr(auth, 'entra_app', lambda: fake)
        return fake

    return _set


@pytest.fixture(autouse=True)
def no_real_microsoft(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inget prov når Microsoft. Ett prov som behöver inloggningen ställer in svaret med fixturen `microsoft`."""
    from core import auth

    def refuse() -> None:
        raise AssertionError('provet försökte anropa Microsoft på riktigt')
    monkeypatch.setattr(auth, 'entra_app', refuse)


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

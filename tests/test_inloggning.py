"""Inloggning lokalt och via Microsoft, spärrar, loggen och sessionen (F0-13, F0-14). Seeden: tests/seed.py."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from flask import Flask
from sqlalchemy import select

from app import create_app
from core import accounts, totp
from core.timeutil import utcnow
from extensions import db
from models import LoginEvent, User
from tests.conftest import TestTenant, local_login
from tests.seed import BERTIL_OID, PASSWORDS, SEED_IP


def _user(name: str) -> User:
    return db.session.scalars(select(User).where(User.username == name)).one()


def _log(app: Flask, tenant: TestTenant) -> list[tuple[str, str, str]]:
    with app.app_context(), tenant.context():
        return [(e.username, e.method, e.outcome) for e in
                db.session.scalars(select(LoginEvent).where(LoginEvent.ip != SEED_IP).order_by(LoginEvent.id))]


def _password(client: Any, tenant: TestTenant, username: str, password: str) -> Any:
    return client.post('/login', data={'tenant': tenant.slug, 'username': username, 'password': password})


# ── Lokala konton ────────────────────────────────────────────────────────────

def test_utan_inloggning_hamnar_man_pa_inloggningen(app: Flask) -> None:
    res = app.test_client().get('/')
    assert res.status_code == 302
    assert res.headers['Location'].startswith('/login')


def test_losenord_och_engangskod_loggar_in(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    first = _password(client, tenant, 'anna', PASSWORDS['anna'])
    assert first.headers['Location'].endswith('/login/kod')
    enrol = client.get('/login/kod').get_data(as_text=True)
    assert 'Nyckeln visas bara nu' in enrol
    assert client.get('/').status_code == 302          # inte inloggad efter bara lösenordet
    res = local_login(client, tenant, 'anna', PASSWORDS['anna'])
    assert res.status_code == 302 and res.headers['Location'] == '/'
    assert '<span class="muted">Anna Andersson</span>' in client.get('/').get_data(as_text=True)
    with app.app_context(), tenant.context():
        anna = _user('anna')
        assert anna.totp_enabled_at is not None and anna.last_login_at is not None
    assert _log(app, tenant) == [('anna', 'password', 'ok'), ('anna', 'password', 'ok'), ('anna', 'totp', 'ok')]


def test_nyckeln_sparas_krypterad(app: Flask, tenant: TestTenant) -> None:
    local_login(app.test_client(), tenant, 'anna', PASSWORDS['anna'])
    with app.app_context(), tenant.context():
        stored = _user('anna').totp_secret
        secret = totp.decrypt(stored)
    assert secret is not None and len(secret) == 32
    assert secret not in (stored or '')


def test_andra_gangen_visas_ingen_nyckel(app: Flask, tenant: TestTenant) -> None:
    local_login(app.test_client(), tenant, 'anna', PASSWORDS['anna'])
    client = app.test_client()
    _password(client, tenant, 'anna', PASSWORDS['anna'])
    page = client.get('/login/kod').get_data(as_text=True)
    assert 'Nyckeln visas bara nu' not in page
    assert 'Skriv koden från autentiseringsappen' in page


@pytest.mark.parametrize('slug_ok, username, password, outcome', [
    (True, 'anna', 'fel-losenord-1234', 'fel_losenord'),
    (True, 'okand', 'vad-som-helst-1234', 'okand'),
    (True, 'bertil', 'vad-som-helst-1234', 'inget_losenord'),   # bara Microsoft
    (False, 'anna', PASSWORDS['anna'], None),                    # fel bolag ger inget i loggen
])
def test_fel_ger_samma_meddelande(app: Flask, tenant: TestTenant, slug_ok: bool, username: str, password: str,
                                  outcome: str | None) -> None:
    client = app.test_client()
    data = {'tenant': tenant.slug if slug_ok else 'finnsinte', 'username': username, 'password': password}
    page = client.post('/login', data=data, follow_redirects=True).get_data(as_text=True)
    assert 'Fel bolag, användarnamn eller lösenord.' in page
    assert client.get('/').status_code == 302
    assert [o for _, _, o in _log(app, tenant)] == ([outcome] if outcome else [])


def test_inaktiverat_konto_nekas(app: Flask, tenant: TestTenant) -> None:
    page = _password(app.test_client(), tenant, 'david', PASSWORDS['david']).get_data(as_text=True)
    assert 'Kontot är inaktiverat' in page
    assert _log(app, tenant) == [('david', 'password', 'inaktiverad')]


def test_fem_fel_laser_kontot_aven_for_ratt_losenord(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    for _ in range(5):
        _password(client, tenant, 'anna', 'fel-losenord-1234')
    with app.app_context(), tenant.context():
        anna = _user('anna')
        assert anna.failed_logins == 5 and anna.locked_until is not None
    page = _password(client, tenant, 'anna', PASSWORDS['anna']).get_data(as_text=True)
    assert 'tillfälligt låst' in page
    assert client.get('/').status_code == 302
    assert _log(app, tenant)[-1] == ('anna', 'password', 'last')


def test_las_upphor_efter_femton_minuter(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        anna = _user('anna')
        anna.failed_logins, anna.locked_until = 5, utcnow() - timedelta(seconds=1)
        db.session.commit()
    res = local_login(app.test_client(), tenant, 'anna', PASSWORDS['anna'])
    assert res.headers['Location'] == '/'
    with app.app_context(), tenant.context():
        assert _user('anna').failed_logins == 0


def test_fel_engangskod_raknas_mot_spärren(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    _password(client, tenant, 'erik', PASSWORDS['erik'])
    for _ in range(5):
        client.post('/login/kod', data={'code': '000000'})
    with app.app_context(), tenant.context():
        assert _user('erik').locked_until is not None
    assert [o for _, m, o in _log(app, tenant) if m == 'totp'] == ['fel_kod'] * 5


def test_tio_misslyckade_forsok_fran_samma_adress_ger_429(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    for n in range(10):
        _password(client, tenant, f'okand{n}', 'vad-som-helst-1234')
    assert _password(client, tenant, 'anna', PASSWORDS['anna']).status_code == 429


def test_next_till_en_annan_webbplats_ignoreras(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    client.post('/login?next=//ond.example/stjal', data={'tenant': tenant.slug, 'username': 'anna',
                                                         'password': PASSWORDS['anna']})
    with app.app_context(), tenant.context():
        secret = totp.decrypt(_user('anna').totp_secret)
    assert secret is not None
    res = client.post('/login/kod', data={'code': totp.code(secret)})
    assert res.headers['Location'] == '/'


def test_rfc6238_testvektorer() -> None:
    secret = totp.base32_secret(b'12345678901234567890')
    assert [totp.code(secret, at=t) for t in (59, 1111111109, 1234567890, 2000000000)] == [
        '287082', '081804', '005924', '279037']
    assert totp.verify(secret, '287082', at=59 + 30)          # ett steg bakåt godtas
    assert not totp.verify(secret, '287082', at=59 + 90)      # tre steg bakåt gör det inte


def test_utloggning_avslutar_sessionen(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    local_login(client, tenant, 'anna', PASSWORDS['anna'])
    assert client.post('/logout').headers['Location'] == '/login'
    assert client.get('/').status_code == 302


# ── Sessionen (F0-14) ────────────────────────────────────────────────────────

def test_inaktivering_avslutar_en_pagaende_session(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    local_login(client, tenant, 'anna', PASSWORDS['anna'])
    assert client.get('/').status_code == 200
    with app.app_context(), tenant.context():
        accounts.deactivate(_user('erik'), _user('anna'))
        db.session.commit()
    assert client.get('/').status_code == 302


def test_sessionen_galler_bara_i_sitt_bolag(app: Flask, make_tenant: Callable[..., TestTenant]) -> None:
    first, second = make_tenant(), make_tenant()
    with app.app_context(), second.context():
        _user('anna').username = 'anna.annan'   # samma användar-id, en annan person
        db.session.commit()
    client = app.test_client()
    local_login(client, first, 'anna', PASSWORDS['anna'])
    assert client.get('/').status_code == 200
    with client.session_transaction() as sess:
        sess['tenant_id'] = second.tenant_id
    assert client.get('/').status_code == 302


def test_en_forfalskad_kaka_godtas_inte(app: Flask, tenant: TestTenant) -> None:
    client = app.test_client()
    local_login(client, tenant, 'anna', PASSWORDS['anna'])
    cookie = client.get_cookie('session')
    assert cookie is not None
    head, _, signature = cookie.value.rpartition('.')
    client.set_cookie('session', f'{head}.{"A" * len(signature)}')
    assert client.get('/').status_code == 302


def test_kakan_ar_skyddad() -> None:
    prod = create_app({'TESTING': False, 'SECRET_KEY': 'x'})
    assert prod.config['SESSION_COOKIE_SECURE'] is True
    assert prod.config['SESSION_COOKIE_HTTPONLY'] is True
    assert prod.config['SESSION_COOKIE_SAMESITE'] == 'Lax'


def test_formularen_kraver_csrf(tenant: TestTenant) -> None:
    protected = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': True})
    res = protected.test_client().post('/login', data={'tenant': tenant.slug, 'username': 'anna',
                                                       'password': PASSWORDS['anna']})
    assert res.status_code == 400


# ── Microsoft ────────────────────────────────────────────────────────────────

def _microsoft(client: Any) -> Any:
    assert client.get('/auth/microsoft').headers['Location'] == 'https://login.prov.invalid/authorize'
    return client.get('/auth/microsoft/callback?code=x&state=prov-state')


def test_microsoft_loggar_in_via_katalog_och_objekt_id(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    microsoft({'tid': tenant.entra_tenant_id, 'oid': BERTIL_OID, 'preferred_username': 'bertil@prov.invalid'})
    client = app.test_client()
    assert _microsoft(client).headers['Location'] == '/'
    assert '<span class="muted">Bertil Berg</span>' in client.get('/').get_data(as_text=True)
    assert _log(app, tenant) == [('bertil', 'microsoft', 'ok')]


def test_microsoft_binder_kontot_forsta_gangen_via_e_post(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    microsoft({'tid': tenant.entra_tenant_id, 'oid': 'ny-oid-anna', 'preferred_username': 'Anna@Prov.Invalid'})
    client = app.test_client()
    assert _microsoft(client).headers['Location'] == '/'
    with app.app_context(), tenant.context():
        assert _user('anna').entra_oid == 'ny-oid-anna'


def test_microsoft_fran_en_okand_organisation_nekas(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    microsoft({'tid': 'en-annan-katalog', 'oid': BERTIL_OID})
    client = app.test_client()
    page = client.get(_microsoft(client).headers['Location']).get_data(as_text=True)
    assert 'Organisationen är inte ansluten' in page
    assert client.get('/').status_code == 302


def test_microsoft_okant_konto_skapas_inte(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    microsoft({'tid': tenant.entra_tenant_id, 'oid': 'okand-oid', 'preferred_username': 'ny@prov.invalid'})
    client = app.test_client()
    _microsoft(client)
    assert client.get('/').status_code == 302
    with app.app_context(), tenant.context():
        assert db.session.scalars(select(User).where(User.username == 'ny@prov.invalid')).one_or_none() is None
    assert _log(app, tenant) == [('ny@prov.invalid', 'microsoft', 'nekad')]


def test_microsoft_inaktiverat_konto_nekas(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    with app.app_context(), tenant.context():
        accounts.deactivate(_user('erik'), _user('bertil'))
        db.session.commit()
    microsoft({'tid': tenant.entra_tenant_id, 'oid': BERTIL_OID})
    client = app.test_client()
    _microsoft(client)
    assert client.get('/').status_code == 302
    assert _log(app, tenant) == [('(microsoft)', 'microsoft', 'inaktiverad')]


def test_en_organisation_godtar_sin_egen_katalog(app: Flask, tenant: TestTenant, microsoft: Any,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """B-011: med ENTRA_TENANT_ID loggar appen in mot den katalogen och släpper in den (oavsett versaler)."""
    from core import auth
    monkeypatch.setenv('ENTRA_TENANT_ID', tenant.entra_tenant_id.upper())
    assert auth.entra_authority() == f'https://login.microsoftonline.com/{tenant.entra_tenant_id}'
    microsoft({'tid': tenant.entra_tenant_id, 'oid': BERTIL_OID})
    client = app.test_client()
    assert _microsoft(client).headers['Location'] == '/'


def test_en_organisation_nekar_ett_annat_anslutet_bolag(app: Flask, make_tenant: Callable[..., TestTenant],
                                                       microsoft: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """B-011: även ett bolag som finns i registret nekas om dess katalog inte är appens. Utan spärren loggar Bertil
    in i det andra bolaget — seeden har honom i båda."""
    from core import auth
    own, other = make_tenant(), make_tenant()
    monkeypatch.setenv('ENTRA_TENANT_ID', own.entra_tenant_id)
    microsoft({'tid': other.entra_tenant_id, 'oid': BERTIL_OID})
    client = app.test_client()
    page = client.get(_microsoft(client).headers['Location']).get_data(as_text=True)
    assert 'Organisationen är inte ansluten' in page
    assert client.get('/').status_code == 302
    assert _log(app, other) == []
    monkeypatch.delenv('ENTRA_TENANT_ID')
    assert auth.entra_authority() == 'https://login.microsoftonline.com/organizations'


def test_microsoft_fel_fran_microsoft_nekas(app: Flask, tenant: TestTenant, microsoft: Any) -> None:
    microsoft(error='access_denied')
    client = app.test_client()
    _microsoft(client)
    assert client.get('/').status_code == 302


# ── Kommandon ────────────────────────────────────────────────────────────────

def test_konto_skapa_kraver_tolv_tecken(app: Flask, tenant: TestTenant) -> None:
    runner = app.test_cli_runner()
    short = runner.invoke(args=['konto-skapa', 'fredrik', '--tenant', tenant.slug, '--namn', 'Fredrik',
                                '--losenord', 'kort-11-tkn'])
    assert short.exit_code != 0 and 'minst 12 tecken' in short.output
    ok = runner.invoke(args=['konto-skapa', 'fredrik', '--tenant', tenant.slug, '--namn', 'Fredrik',
                             '--losenord', 'tolv-tecken!'])
    assert ok.exit_code == 0, ok.output
    assert local_login(app.test_client(), tenant, 'fredrik', 'tolv-tecken!').headers['Location'] == '/'

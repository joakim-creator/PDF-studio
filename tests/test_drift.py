"""Proxy, säkerhetshuvuden, felsida, hälsosida och felrapportering (F0-10, F0-11, F0-17)."""

from collections.abc import Iterator
from typing import Any

import pytest
from flask import Flask, request
from sentry_sdk.transport import Transport

from app import create_app
from core import observability
from core.models_master import Tenant
from extensions import db


@pytest.fixture
def prov_app() -> Flask:
    """En egen app med provsidor. Fel ska ge felsidan, inte kastas vidare till provet."""
    app = create_app({'TESTING': True, 'PROPAGATE_EXCEPTIONS': False})

    @app.get('/prov/adress')
    def adress() -> dict[str, str]:
        return {'adress': request.remote_addr or '', 'schema': request.scheme}

    @app.get('/prov/krasch')
    def krasch() -> str:
        raise RuntimeError('hemlig detalj ur databasen')

    @app.get('/api/prov/krasch')
    def api_krasch() -> str:
        raise RuntimeError('hemlig detalj ur databasen')

    return app


@pytest.fixture(autouse=True)
def _fresh_cap(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    observability.reset_report_cap()
    yield
    observability.reset_report_cap()


# ── Proxy (F0-10) ────────────────────────────────────────────────────────────

def test_klientens_adress_kommer_fran_proxyn(prov_app: Flask) -> None:
    client = prov_app.test_client()
    seen = {client.get('/prov/adress', headers={'X-Forwarded-For': f'203.0.113.{n}'},
                       environ_base={'REMOTE_ADDR': '127.0.0.1'}).get_json()['adress'] for n in range(12)}
    assert seen == {f'203.0.113.{n}' for n in range(12)}


def test_bara_en_proxy_ar_betrodd(prov_app: Flask) -> None:
    res = prov_app.test_client().get('/prov/adress', headers={'X-Forwarded-For': '198.51.100.1, 203.0.113.5'},
                                     environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert res.get_json()['adress'] == '203.0.113.5'   # den förfalskade första adressen räknas inte


def test_https_fran_proxyn_ger_hsts(prov_app: Flask) -> None:
    client = prov_app.test_client()
    secure = client.get('/prov/adress', headers={'X-Forwarded-Proto': 'https'})
    assert secure.get_json()['schema'] == 'https'
    assert secure.headers['Strict-Transport-Security'] == 'max-age=31536000'
    assert 'Strict-Transport-Security' not in client.get('/prov/adress').headers


def test_sakerhetshuvuden_pa_varje_svar(app: Flask) -> None:
    headers = app.test_client().get('/health').headers
    assert headers['X-Frame-Options'] == 'DENY'
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert "frame-ancestors 'none'" in headers['Content-Security-Policy-Report-Only']


# ── Felsidan (F0-11) ─────────────────────────────────────────────────────────

def test_felsidan_visar_arendenumret_men_inga_detaljer(prov_app: Flask) -> None:
    res = prov_app.test_client().get('/prov/krasch', headers={'X-Request-ID': 'arende-123'})
    page = res.get_data(as_text=True)
    assert res.status_code == 500
    assert 'arende-123' in page
    assert 'hemlig detalj' not in page
    assert 'RuntimeError' not in page


def test_api_fel_svarar_med_json(prov_app: Flask) -> None:
    res = prov_app.test_client().get('/api/prov/krasch', headers={'X-Request-ID': 'arende-456'})
    assert res.status_code == 500
    assert res.get_json() == {'error': 'internt fel', 'arende': 'arende-456'}


def test_felet_loggas_med_stack_och_arendenummer(prov_app: Flask, caplog: pytest.LogCaptureFixture) -> None:
    prov_app.test_client().get('/prov/krasch', headers={'X-Request-ID': 'arende-789'})
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert len(errors) == 1
    assert errors[0].exc_info is not None
    assert errors[0].request_id == 'arende-789'  # type: ignore[attr-defined]


# ── Hälsosidan (F0-11) ───────────────────────────────────────────────────────

def test_halsosidan_svarar_503_nar_ett_bolag_inte_nas(app: Flask, tenant: Any, tmp_path: Any) -> None:
    broken_url = f'sqlite:///{(tmp_path / "finns-inte" / "bolag.db").as_posix()}'
    with app.app_context():
        broken = Tenant(slug=f'trasig{tmp_path.name[-6:]}', name='Trasigt bolag', database_url=broken_url)
        db.session.add(broken)
        db.session.commit()
        broken_id = broken.id
    try:
        res = app.test_client().get('/health')
        healthy, total = (int(n) for n in res.get_json()['bolag'].split('/'))
        assert res.status_code == 503
        assert res.get_json()['status'] == 'fel'
        assert total - healthy == 1
        assert 'finns-inte' not in res.get_data(as_text=True)   # inga detaljer på den publika sidan
    finally:
        with app.app_context():
            db.session.get(Tenant, broken_id).active = False  # type: ignore[union-attr]
            db.session.commit()
    assert app.test_client().get('/health').status_code == 200


# ── Felrapporteringen (F0-11) ────────────────────────────────────────────────

def _event() -> dict[str, Any]:
    return {
        'request': {'url': 'https://pdf.example/api/dok?personnummer=19800101-1234', 'method': 'POST',
                    'cookies': {'session': 'hemlig'}, 'headers': {'Authorization': 'Bearer x'},
                    'data': {'losenord': 'hemligt'}, 'query_string': 'personnummer=19800101-1234'},
        'breadcrumbs': [{'message': 'SELECT * FROM users'}],
        'extra': {'sys.argv': ['gunicorn']},
        'exception': {'values': [{'type': 'RuntimeError'}]},
    }


def test_rapporten_tvattas_innan_den_lamnar_servern(prov_app: Flask) -> None:
    with prov_app.test_request_context('/', headers={'X-Request-ID': 'arende-1'}):
        event = observability.scrub(_event())
    assert event is not None
    assert event['request'] == {'url': 'https://pdf.example/api/dok', 'method': 'POST'}
    assert 'breadcrumbs' not in event
    assert 'extra' not in event
    assert event['tags'] == {'arende': 'arende-1'}
    assert '19800101' not in str(event)
    assert 'hemlig' not in str(event)


def test_taket_per_timme_haller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('ERROR_REPORT_HOURLY_MAX', '2')
    results = [observability.scrub(_event()) for _ in range(3)]
    assert [r is not None for r in results] == [True, True, False]


class _Capture(Transport):
    """Samlar rapporterna i minnet. Ärver Transport, annars går anropet ut på nätet (backend-grund 3)."""

    def __init__(self, options: Any = None) -> None:
        super().__init__(options)
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


def test_ett_fel_rapporteras_tvattat_och_med_arendenummer(prov_app: Flask) -> None:
    transport = _Capture()
    observability.init_error_reporting('https://nyckel@glitchtip.prov.invalid/1', transport=transport)
    try:
        prov_app.test_client().get('/prov/krasch?personnummer=19800101-1234', headers={'X-Request-ID': 'arende-9'},
                                   environ_base={'HTTP_COOKIE': 'session=kakvarde-xyz'})
    finally:
        observability.disable_error_reporting()
    assert len(transport.events) == 1
    event = transport.events[0]
    assert event['tags']['arende'] == 'arende-9'
    assert event['request'] == {'url': 'http://localhost/prov/krasch', 'method': 'GET'}
    assert 'kakvarde-xyz' not in str(event)
    assert '19800101' not in str(event)
    assert 'vars' not in str(event['exception'])   # inga lokala variabler i stacken

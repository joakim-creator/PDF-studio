"""Hälsosidan och ärendenumret (F0-03)."""

import pytest
from flask import Flask

from app import create_app


def test_health_svarar_ok(app: Flask) -> None:
    res = app.test_client().get('/health')
    assert res.status_code == 200
    assert res.get_json() == {'app': 'ok'}


def test_varje_svar_bar_ett_arendenummer(app: Flask) -> None:
    res = app.test_client().get('/health')
    rid = res.headers['X-Request-ID']
    assert len(rid) == 16
    assert all(c in '0123456789abcdef' for c in rid)


def test_ett_giltigt_arendenummer_fran_proxyn_foljer_med(app: Flask) -> None:
    res = app.test_client().get('/health', headers={'X-Request-ID': 'nginx-abc123'})
    assert res.headers['X-Request-ID'] == 'nginx-abc123'


def test_ett_ogiltigt_arendenummer_ersatts(app: Flask) -> None:
    res = app.test_client().get('/health', headers={'X-Request-ID': 'x' * 65})
    assert res.headers['X-Request-ID'] != 'x' * 65
    assert len(res.headers['X-Request-ID']) == 16


def test_appen_startar_inte_utan_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        create_app()


def test_appen_startar_inte_utan_masterdatabas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('MASTER_DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='MASTER_DATABASE_URL'):
        create_app({'TESTING': True})

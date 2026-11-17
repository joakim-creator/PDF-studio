"""Konton inaktiveras, tillägg delas ut uttryckligen, allt loggas (F0-14, F0-15). Seeden: tests/seed.py."""

import pytest
from flask import Flask
from sqlalchemy import select

from core import accounts
from core.access import DELETE_DOCUMENT, AccessDenied, has_permission, visible_documents
from extensions import db
from models import AuditEvent, User
from tests.conftest import TestTenant


def _user(name: str) -> User:
    return db.session.scalars(select(User).where(User.username == name)).one()


def _events(action: str) -> list[str]:
    return list(db.session.scalars(select(AuditEvent.description).where(AuditEvent.action == action)))


def test_inaktivering_kraver_tillagget_och_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        accounts.deactivate(_user('erik'), _user('bertil'))
        db.session.commit()
        bertil = _user('bertil')
        assert bertil.active is False
        assert list(db.session.scalars(visible_documents(bertil))) == []
        assert _events('inaktivera') == ['bertil inaktiverades']


def test_administrator_kan_inte_inaktivera_utan_tillagg(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        with pytest.raises(AccessDenied) as denied:
            accounts.deactivate(_user('cecilia'), _user('bertil'))
        assert denied.value.permission == accounts.MANAGE_ACCOUNTS
        db.session.rollback()
        assert _user('bertil').active is True
        assert _events('inaktivera') == []


def test_ingen_kan_inaktivera_sig_sjalv(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(AccessDenied, match='eget konto'):
        accounts.deactivate(_user('erik'), _user('erik'))


def test_ett_inaktiverat_konto_kan_ateraktiveras(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        accounts.reactivate(_user('erik'), _user('david'))
        db.session.commit()
        assert _user('david').active is True
        assert _events('ateraktivera') == ['david återaktiverades']


def test_tillagg_delas_ut_uttryckligen_och_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        assert has_permission(_user('anna'), DELETE_DOCUMENT) is False
        accounts.grant(_user('erik'), _user('anna'), DELETE_DOCUMENT)
        db.session.commit()
        assert has_permission(_user('anna'), DELETE_DOCUMENT) is True
        assert _events('tillagg') == ['erik fick dokument.radera', 'anna fick dokument.radera']


def test_ingen_kan_ge_sig_sjalv_ett_tillagg(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(AccessDenied, match='dig själv'):
        accounts.grant(_user('erik'), _user('erik'), DELETE_DOCUMENT)


def test_administrator_kan_inte_dela_ut_tillagg_utan_tillagget(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(AccessDenied) as denied:
        accounts.grant(_user('cecilia'), _user('anna'), DELETE_DOCUMENT)
    assert denied.value.permission == accounts.MANAGE_ACCOUNTS


def test_okant_tillagg_godtas_inte(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(ValueError, match='okänt tillägg'):
        accounts.grant(_user('erik'), _user('anna'), 'allt.och.lite.till')


def test_tillagg_kan_tas_bort_och_det_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        cecilia = _user('cecilia')
        accounts.grant(_user('erik'), cecilia, accounts.MANAGE_ACCOUNTS)
        db.session.commit()
        accounts.revoke(cecilia, _user('erik'), DELETE_DOCUMENT)
        db.session.commit()
        assert has_permission(_user('erik'), DELETE_DOCUMENT) is False
        assert _events('tillagg_bort') == ['erik förlorade dokument.radera']

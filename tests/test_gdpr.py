"""Gallringsregeln, besluten och registerutdraget (F0-16). Seeden: tests/seed.py."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import func, select, update

from core import retention
from core.access import AccessDenied
from extensions import db
from models import Annotation, AuditEvent, Document, DocumentVersion, User
from tests.conftest import TestTenant

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def _user(name: str) -> User:
    return db.session.scalars(select(User).where(User.username == name)).one()


def _doc_id(title: str) -> int:
    return db.session.scalars(select(Document.id).where(Document.title == title)).one()


def _age(title: str, when: datetime) -> None:
    """Sätter all aktivitet på dokumentet (dokumentet, versionerna, kommentarerna) till `when`."""
    doc_id = _doc_id(title)
    versions = select(DocumentVersion.id).where(DocumentVersion.document_id == doc_id)
    db.session.execute(update(Document).where(Document.id == doc_id).values(created_at=when))
    db.session.execute(update(DocumentVersion).where(DocumentVersion.document_id == doc_id).values(created_at=when))
    db.session.execute(update(Annotation).where(Annotation.version_id.in_(versions)).values(created_at=when))
    db.session.commit()


def _titles(now: datetime = NOW) -> list[tuple[str, str]]:
    return [(c.title, c.reason) for c in retention.candidates(now)]


def test_nya_dokument_star_inte_pa_tur(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        assert db.session.scalar(select(func.count()).select_from(Document)) == 5
        assert _titles(datetime.now(UTC)) == []


def test_tjugofyra_manader_utan_aktivitet_star_pa_tur(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        _age('Faktura oktober', datetime(2024, 11, 17, 11, 0, tzinfo=UTC))     # 24 månader och en timme
        _age('Hyresavtal L25', datetime(2024, 11, 18, 12, 0, tzinfo=UTC))      # en dag kvar
        for title in ('Offert Kund AB', 'Anteckningar', 'Gammal rapport'):
            _age(title, NOW)
        assert _titles() == [('Faktura oktober', retention.REASON_INACTIVE)]


def test_en_ny_kommentar_raknas_som_aktivitet(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        old = datetime(2023, 1, 1, tzinfo=UTC)
        for title in ('Offert Kund AB', 'Anteckningar', 'Faktura oktober', 'Gammal rapport', 'Hyresavtal L25'):
            _age(title, old)
        offert_v2 = db.session.scalars(select(DocumentVersion.id).where(
            DocumentVersion.document_id == _doc_id('Offert Kund AB'), DocumentVersion.version_no == 2)).one()
        db.session.execute(update(Annotation).where(Annotation.version_id == offert_v2).values(created_at=NOW))
        db.session.commit()
        assert 'Offert Kund AB' not in [t for t, _ in _titles()]
        assert len(_titles()) == 4


def test_papperskorgen_toms_efter_sju_dagar(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        for title in ('Offert Kund AB', 'Anteckningar', 'Faktura oktober', 'Gammal rapport', 'Hyresavtal L25'):
            _age(title, NOW)
        db.session.execute(update(Document).where(Document.id == _doc_id('Anteckningar'))
                           .values(deleted_at=NOW - timedelta(days=7, minutes=1)))
        db.session.execute(update(Document).where(Document.id == _doc_id('Faktura oktober'))
                           .values(deleted_at=NOW - timedelta(days=6)))
        db.session.commit()
        assert _titles() == [('Anteckningar', retention.REASON_TRASH)]


def test_besluta_kraver_tillagget(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(AccessDenied) as denied:
        retention.decide(_user('erik'), _doc_id('Anteckningar'), keep=False)
    assert denied.value.permission == retention.DECIDE


def test_behalla_kraver_en_anledning(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(ValueError, match='anledning'):
        retention.decide(_user('cecilia'), _doc_id('Anteckningar'), keep=True, reason='  ')


def test_behall_ger_ny_provning_om_tjugofyra_manader_och_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        _age('Faktura oktober', datetime(2023, 1, 1, tzinfo=UTC))
        retention.decide(_user('cecilia'), _doc_id('Faktura oktober'), keep=True, reason='Tvist med kund pågår')
        db.session.commit()
        doc = db.session.get(Document, _doc_id('Faktura oktober'))
        assert doc is not None and doc.purge_after is not None
        due = retention._aware(doc.purge_after)
        assert 729 <= (due - datetime.now(UTC)).days <= 731
        assert 'Faktura oktober' not in [t for t, _ in _titles(datetime.now(UTC))]
        assert ('Faktura oktober', retention.REASON_EXPIRED) in _titles(due + timedelta(minutes=1))
        event = db.session.scalars(select(AuditEvent).where(AuditEvent.action == 'behall')).one()
        assert event.user_id == _user('cecilia').id
        assert event.description.startswith(f'Dokument {doc.id} ”Faktura oktober” behålls: Tvist med kund pågår.')


def test_gallra_flyttar_till_papperskorgen_och_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        doc_id = _doc_id('Gammal rapport')
        retention.decide(_user('cecilia'), doc_id, keep=False)
        db.session.commit()
        doc = db.session.get(Document, doc_id)
        assert doc is not None and doc.deleted_at is not None
        later = retention._aware(doc.deleted_at) + timedelta(days=8)
        assert ('Gammal rapport', retention.REASON_TRASH) in _titles(later)
        assert db.session.scalars(select(AuditEvent.description).where(AuditEvent.action == 'gallra')).all() == [
            f'Dokument {doc_id} ”Gammal rapport” gallras (papperskorgen, töms efter 7 dagar)']


def test_registerutdraget_tar_med_allt_om_personen_men_inga_hemligheter(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        anna = _user('anna')
        anna.password_hash = 'scrypt$hemlig-hash'
        anna.totp_secret = 'krypterad-nyckel'
        db.session.commit()
        data = retention.extract(_user('anna'))
        text = json.dumps(data, ensure_ascii=False)
    assert data['konto']['username'] == 'anna'
    assert data['konto']['email'] == 'anna@prov.invalid'
    assert data['konto']['lösenord'] is True and data['konto']['engångskod'] is True
    assert {d['title'] for d in data['egna_dokument']} == {'Offert Kund AB', 'Anteckningar'}
    assert data['delade_dokument'] == []
    assert [k['body'] for k in data['kommentarer']] == ['Stämmer totalen?']
    assert 'hemlig-hash' not in text and 'krypterad-nyckel' not in text


def test_registerutdraget_for_den_som_fatt_ett_dokument_delat(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        data = retention.extract(_user('bertil'))
    assert [d['title'] for d in data['delade_dokument']] == ['Offert Kund AB']
    assert [(j['kind'], j['cost_sek']) for j in data['jobb']] == [('ocr', '0.4200')]
    assert [u['model'] for u in data['ai_kostnader']] == ['claude-opus-5-5']


def test_kommandona_torrkor_och_lamnar_utdrag(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        _age('Faktura oktober', datetime(2023, 1, 1, tzinfo=UTC))
    runner = app.test_cli_runner()
    result = runner.invoke(args=['gdpr-kandidater', '--tenant', tenant.slug])
    assert result.exit_code == 0, result.output
    assert f'{tenant.slug}: 1 dokument på tur (torrkörning — inget ändrat)' in result.output
    assert 'Faktura oktober' in result.output
    with app.app_context(), tenant.context():
        assert db.session.scalar(select(func.count()).select_from(Document).where(Document.deleted_at.isnot(None))) == 0
    extract = runner.invoke(args=['gdpr-utdrag', 'bertil', '--tenant', tenant.slug])
    assert extract.exit_code == 0, extract.output
    assert json.loads(extract.output)['konto']['display_name'] == 'Bertil Berg'
    missing = runner.invoke(args=['gdpr-utdrag', 'okand', '--tenant', tenant.slug])
    assert missing.exit_code != 0
    assert 'ingen användare okand' in missing.output

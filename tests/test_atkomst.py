"""Åtkomst inom och mellan bolag, och villkoren i schemat (F0-05, F0-06). Seeden: tests/seed.py."""

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.access import DELETE_DOCUMENT, AccessDenied, delete_document, get_document, has_permission, \
    visible_documents
from extensions import db
from models import AuditEvent, Document, DocumentVersion, User
from tests.conftest import TestTenant


def _user(name: str) -> User:
    return db.session.scalars(select(User).where(User.username == name)).one()


def _titles(name: str) -> set[str]:
    return {d.title for d in db.session.scalars(visible_documents(_user(name)))}


def _doc(title: str) -> Document:
    return db.session.scalars(select(Document).where(Document.title == title)).one()


def _doc_id(title: str) -> int:
    return db.session.scalars(select(Document.id).where(Document.title == title)).one()


def test_var_och_en_ser_sitt_eget_och_det_som_delats(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        assert _titles('anna') == {'Offert Kund AB', 'Anteckningar'}
        assert _titles('bertil') == {'Faktura oktober', 'Offert Kund AB'}
        assert _titles('erik') == {'Hyresavtal L25'}
        assert _titles('cecilia') == set()   # administratör ser inte andras dokument


def test_ett_inaktiverat_konto_ser_ingenting(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        assert _doc('Gammal rapport').owner_id == _user('david').id   # dokumentet finns och är hans
        assert _titles('david') == set()


def test_ett_otillatet_dokument_ger_samma_fel_som_ett_som_inte_finns(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        anna = _user('anna')
        with pytest.raises(AccessDenied) as forbidden:
            get_document(anna, _doc_id('Faktura oktober'))
        with pytest.raises(AccessDenied) as missing:
            get_document(anna, 999_999)
        assert str(forbidden.value) == str(missing.value) == 'Dokumentet finns inte.'
        assert get_document(anna, _doc_id('Offert Kund AB')).title == 'Offert Kund AB'


def test_radering_kraver_tillagget_aven_for_agaren(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        anna = _user('anna')
        with pytest.raises(AccessDenied) as denied:
            delete_document(anna, _doc_id('Anteckningar'))
        assert denied.value.permission == DELETE_DOCUMENT
        db.session.rollback()
        assert _doc('Anteckningar').deleted_at is None
        assert db.session.scalar(select(func.count()).select_from(AuditEvent)
                                 .where(AuditEvent.action == 'radera')) == 0


def test_administrator_far_inga_tillagg_automatiskt(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        assert _user('cecilia').is_admin is True
        assert has_permission(_user('cecilia'), DELETE_DOCUMENT) is False
        assert has_permission(_user('erik'), DELETE_DOCUMENT) is True


def test_radering_med_tillagget_flyttar_till_papperskorgen_och_loggas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        erik = _user('erik')
        doc_id = _doc_id('Hyresavtal L25')
        delete_document(erik, doc_id)
        db.session.commit()
        assert _doc('Hyresavtal L25').deleted_at is not None
        assert _titles('erik') == set()
        event = db.session.scalars(select(AuditEvent).where(AuditEvent.action == 'radera')).one()
        assert event.user_id == erik.id
        assert event.description == f'Dokument {doc_id} ”Hyresavtal L25” flyttat till papperskorgen'


def test_tillagget_ger_inte_atkomst_till_andras_dokument(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context(), pytest.raises(AccessDenied, match='finns inte'):
        delete_document(_user('erik'), _doc_id('Anteckningar'))


def test_ett_bolag_ser_inte_ett_annat_bolags_dokument(app: Flask, make_tenant) -> None:  # type: ignore[no-untyped-def]
    first, second = make_tenant(), make_tenant()
    with app.app_context():
        with first.context():
            db.session.add(Document(title='Bara i första bolaget', owner_id=_user('anna').id))
            db.session.commit()
            assert _titles('anna') == {'Offert Kund AB', 'Anteckningar', 'Bara i första bolaget'}
        with second.context():
            assert db.session.scalar(select(func.count()).select_from(Document)
                                     .where(Document.title == 'Bara i första bolaget')) == 0
            assert _titles('anna') == {'Offert Kund AB', 'Anteckningar'}


def test_lagringsnycklarna_bar_bolagets_namn(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        keys = db.session.scalars(select(DocumentVersion.storage_key)).all()
        assert len(keys) == 6
        assert all(k.startswith(f'{tenant.slug}/documents/') for k in keys)


def test_ingen_fraga_utan_valt_bolag(app: Flask) -> None:
    with app.app_context(), pytest.raises(RuntimeError, match='Inget bolag är valt'):
        db.session.scalars(select(Document)).all()


def test_ett_konto_som_skapat_nagot_kan_inte_raderas(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        db.session.delete(_user('anna'))
        with pytest.raises(IntegrityError):
            db.session.commit()


@pytest.mark.parametrize('changes', [
    {'version_no': 1, 'parent': True},      # version 1 kan inte ha en förälder
    {'version_no': 3, 'parent': False},     # en senare version måste ha en
    {'source': 'okand'},
    {'page_count': 0},
])
def test_versionsreglerna_upprathalls_av_databasen(app: Flask, tenant: TestTenant, changes: dict) -> None:
    with app.app_context(), tenant.context():
        offert = _doc('Offert Kund AB')
        first = db.session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == offert.id,
                                                                 DocumentVersion.version_no == 1)).one()
        version = DocumentVersion(
            document_id=offert.id, version_no=changes.get('version_no', 3),
            parent_version_id=first.id if changes.get('parent', True) else None,
            storage_key=f'{tenant.slug}/documents/ny.pdf', sha256='0' * 64,
            page_count=changes.get('page_count', 1), size_bytes=10, source=changes.get('source', 'merge'),
            created_by=_user('anna').id)
        db.session.add(version)
        with pytest.raises(IntegrityError):
            db.session.commit()


def test_versionsnumret_ar_unikt_per_dokument(app: Flask, tenant: TestTenant) -> None:
    with app.app_context(), tenant.context():
        offert = _doc('Offert Kund AB')
        first = db.session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == offert.id,
                                                                 DocumentVersion.version_no == 1)).one()
        db.session.add(DocumentVersion(document_id=offert.id, version_no=2, parent_version_id=first.id,
                                       storage_key=f'{tenant.slug}/documents/dubblett.pdf', sha256='0' * 64,
                                       page_count=1, size_bytes=10, source='merge', created_by=_user('anna').id))
        with pytest.raises(IntegrityError):
            db.session.commit()

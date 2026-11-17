"""Uppladdning, versioner, slå ihop, dela, sidor och återställning (F1-01, F1-02, F1-05–F1-08)."""

import hashlib
import os
import re
from collections.abc import Iterator

import pytest
from flask import Flask
from sqlalchemy import select

from core import documents, pdfops, storage
from core.access import AccessDenied
from extensions import db
from models import Document, User
from tests import pdfs
from tests.conftest import TestTenant


def _user(name: str) -> User:
    return db.session.scalars(select(User).where(User.username == name)).one()


@pytest.fixture
def ctx(app: Flask, tenant: TestTenant) -> Iterator[TestTenant]:
    with app.app_context(), tenant.context():
        yield tenant


def _upload(name: str, data: bytes, user: str = 'anna') -> int:
    doc = documents.upload(_user(user), name, data)
    db.session.commit()
    return doc.id


# ── Uppladdning ──────────────────────────────────────────────────────────────

def test_uppladdning_sparar_filen_och_version_ett(ctx: TestTenant) -> None:
    data = pdfs.make('A', 3)
    doc_id = _upload('C:\\Users\\anna\\Offert mars.pdf', data)
    version, stored = documents.read(_user('anna'), doc_id)
    assert db.session.get(Document, doc_id).title == 'Offert mars.pdf'  # type: ignore[union-attr]
    assert (version.version_no, version.source, version.page_count, version.size_bytes) == (1, 'upload', 3, len(data))
    assert version.parent_version_id is None
    assert version.sha256 == hashlib.sha256(data).hexdigest()
    assert re.fullmatch(rf'{ctx.slug}/documents/[0-9a-f]{{32}}\.pdf', version.storage_key)
    assert stored == data


@pytest.mark.parametrize('data, message', [
    (b'\x89PNG\r\n\x1a\nbild', 'inte en PDF'),
    (b'', 'tom'),
    (b'%PDF-1.7\n' + b'0' * (32 * 1024 * 1024), 'större än 32 MB'),
    (b'%PDF-1.7\ntrasig', 'skadad'),
    (pdfs.make('L', 1, password='hemligt'), 'lösenordsskyddad'),
], ids=['bild', 'tom', 'for-stor', 'trasig', 'losenord'])
def test_uppladdning_kontrollerar_innehallet_inte_andelsen(ctx: TestTenant, data: bytes, message: str) -> None:
    with pytest.raises(documents.DocumentError, match=message):
        documents.upload(_user('anna'), 'ser-ut-som.pdf', data)
    db.session.rollback()
    assert db.session.scalars(select(Document).where(Document.title == 'ser-ut-som.pdf')).all() == []


def test_andras_dokument_gar_inte_att_lasa(ctx: TestTenant) -> None:
    doc_id = _upload('Privat.pdf', pdfs.make('P', 1))
    with pytest.raises(AccessDenied):
        documents.read(_user('bertil'), doc_id)


# ── Slå ihop och dela ────────────────────────────────────────────────────────

def test_sla_ihop_i_vald_ordning_och_kallorna_ar_orord(ctx: TestTenant) -> None:
    a, b = pdfs.make('A', 2), pdfs.make('B', 3, size=pdfs.LETTER)
    a_id, b_id = _upload('A.pdf', a), _upload('B.pdf', b)
    merged = documents.merge(_user('anna'), [b_id, a_id], 'B och A.pdf')
    db.session.commit()
    version, data = documents.read(_user('anna'), merged.id)
    assert (merged.title, version.source, version.page_count) == ('B och A.pdf', 'merge', 5)
    assert pdfs.texts(data) == ['B1', 'B2', 'B3', 'A1', 'A2']
    assert pdfs.sizes(data) == [pdfs.LETTER] * 3 + [pdfs.A4] * 2
    assert documents.read(_user('anna'), a_id)[1] == a
    assert documents.count_versions(a_id) == 1


def test_sla_ihop_kraver_tva_filer_och_atkomst_till_alla(ctx: TestTenant) -> None:
    a_id = _upload('A.pdf', pdfs.make('A', 1))
    other = _upload('Bertils.pdf', pdfs.make('X', 1), user='bertil')
    with pytest.raises(documents.DocumentError, match='minst två'):
        documents.merge(_user('anna'), [a_id], 'Ensam.pdf')
    with pytest.raises(AccessDenied):
        documents.merge(_user('anna'), [a_id, other], 'Stulen.pdf')


def test_dela_markerade_sidor_intervall_och_en_per_sida(ctx: TestTenant) -> None:
    doc_id = _upload('Avtal.pdf', pdfs.make('S', 6))
    anna = _user('anna')
    [selected] = documents.split(anna, doc_id, 'selected', pages=[2, 3])
    [ranged] = documents.split(anna, doc_id, 'range', ranges='5-6, 1')
    each = documents.split(anna, doc_id, 'each')
    db.session.commit()
    assert pdfs.texts(documents.read(anna, selected.id)[1]) == ['S2', 'S3']
    assert pdfs.texts(documents.read(anna, ranged.id)[1]) == ['S5', 'S6', 'S1']
    assert [pdfs.texts(documents.read(anna, d.id)[1]) for d in each] == [[f'S{n}'] for n in range(1, 7)]
    assert selected.title == 'Avtal – sidor 2, 3.pdf'
    assert each[0].title == 'Avtal – sida 1.pdf'
    assert documents.count_versions(doc_id) == 1


@pytest.mark.parametrize('ranges, message', [
    ('3-1', 'baklänges'), ('x', 'inte ett sidnummer'), ('9', 'Sidan 9 finns inte'), ('', 'minst en sida'),
])
def test_felaktiga_intervall_forklaras(ctx: TestTenant, ranges: str, message: str) -> None:
    doc_id = _upload('Avtal.pdf', pdfs.make('S', 6))
    with pytest.raises(documents.DocumentError, match=message):
        documents.split(_user('anna'), doc_id, 'range', ranges=ranges)


# ── Sidor och versioner ──────────────────────────────────────────────────────

def test_rotera_ger_ny_version_och_originalet_ar_kvar(ctx: TestTenant) -> None:
    original = pdfs.make('R', 3)
    doc_id = _upload('Rotera.pdf', original)
    v2 = documents.change(_user('anna'), doc_id, lambda d: pdfops.rotate(d, [2], 90))
    db.session.commit()
    assert (v2.version_no, v2.source) == (2, 'pages')
    assert v2.parent_version_id == documents.read(_user('anna'), doc_id, 1)[0].id
    assert pdfs.rotations(documents.read(_user('anna'), doc_id)[1]) == [0, 90, 0]
    assert documents.read(_user('anna'), doc_id, 1)[1] == original


def test_ta_bort_och_infoga_sidor(ctx: TestTenant) -> None:
    doc_id = _upload('Sidor.pdf', pdfs.make('T', 3, size=pdfs.LETTER))
    other = _upload('Bilaga.pdf', pdfs.make('B', 2))
    anna = _user('anna')
    bilaga = documents.read(anna, other)[1]
    documents.change(anna, doc_id, lambda d: pdfops.delete_pages(d, [2]))
    documents.change(anna, doc_id, lambda d: pdfops.insert_blank(d, 1))
    documents.change(anna, doc_id, lambda d: pdfops.insert_from(d, bilaga, 3, [2]))
    db.session.commit()
    final = documents.read(anna, doc_id)[1]
    assert pdfs.texts(final) == ['T1', '', 'T3', 'B2']
    assert pdfs.sizes(final)[1] == pdfs.LETTER            # den tomma sidan har grannens storlek
    assert [v.version_no for v in documents.versions(anna, doc_id)] == [1, 2, 3, 4]


def test_alla_sidor_kan_inte_tas_bort(ctx: TestTenant) -> None:
    doc_id = _upload('Sidor.pdf', pdfs.make('T', 2))
    with pytest.raises(documents.DocumentError, match='alla sidor'):
        documents.change(_user('anna'), doc_id, lambda d: pdfops.delete_pages(d, [1, 2]))


def test_aterstall_en_aldre_version_som_en_ny(ctx: TestTenant) -> None:
    original = pdfs.make('V', 2)
    doc_id = _upload('Versioner.pdf', original)
    anna = _user('anna')
    documents.change(anna, doc_id, lambda d: pdfops.delete_pages(d, [1]))
    restored = documents.restore(anna, doc_id, 1)
    db.session.commit()
    assert (restored.version_no, restored.source) == (3, 'restore')
    assert documents.read(anna, doc_id)[1] == original
    with pytest.raises(documents.DocumentError, match='redan den senaste'):
        documents.restore(anna, doc_id, 3)


def test_den_som_inte_ser_dokumentet_kan_inte_andra_det(ctx: TestTenant) -> None:
    offert = db.session.scalars(select(Document.id).where(Document.title == 'Offert Kund AB')).one()
    with pytest.raises(AccessDenied):   # seedens versioner saknar filer, men åtkomsten prövas först
        documents.change(_user('erik'), offert, lambda d: d)


def test_sidor_som_bild(ctx: TestTenant) -> None:
    data = pdfs.make('P', 2)
    small, large = pdfops.render_png(data, 1, 72), pdfops.render_png(data, 2, 150)
    assert small.startswith(b'\x89PNG') and large.startswith(b'\x89PNG')
    assert len(large) > len(small)
    with pytest.raises(pdfops.PdfError, match='Sidan 3 finns inte'):
        pdfops.render_png(data, 3)


# ── Lagringen ────────────────────────────────────────────────────────────────

def test_lagringen_skriver_aldrig_over_och_godtar_bara_riktiga_nycklar(tmp_path: object) -> None:
    store = storage.LocalStorage(str(tmp_path))
    key = 'bolag/documents/' + 'a' * 32 + '.pdf'
    store.put(key, b'%PDF-1')
    with pytest.raises(storage.StorageError, match='finns redan'):
        store.put(key, b'%PDF-2')
    assert store.get(key) == b'%PDF-1'
    for bad in ('../../etc/passwd', 'bolag/documents/x.pdf', 'Bolag/documents/' + 'a' * 32 + '.pdf'):
        with pytest.raises(storage.StorageError, match='ogiltig'):
            store.put(bad, b'x')


AZURITE = os.environ.get('AZURITE_CONNECTION_STRING')


def test_azure_blob_mot_azurite() -> None:
    if not AZURITE:
        if os.environ.get('REQUIRE_AZURITE') == '1':
            pytest.fail('AZURITE_CONNECTION_STRING saknas men REQUIRE_AZURITE=1')
        pytest.skip('Azurite körs inte (se scripts/verify.py)')
    from azure.storage.blob import BlobServiceClient
    container = f'prov{os.getpid()}'
    service = BlobServiceClient.from_connection_string(AZURITE)
    service.create_container(container)
    try:
        store = storage.AzureBlobStorage(AZURITE, container)
        key = 'bolag/documents/' + 'b' * 32 + '.pdf'
        assert store.exists(key) is False
        store.put(key, b'%PDF-azure')
        assert store.exists(key) is True and store.get(key) == b'%PDF-azure'
        with pytest.raises(storage.StorageError, match='finns redan'):
            store.put(key, b'%PDF-ny')
        store.delete(key)
        with pytest.raises(storage.StorageError, match='finns inte'):
            store.get(key)
    finally:
        service.delete_container(container)

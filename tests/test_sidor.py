"""Sidorna: startsidan, uppladdning, dokumentvyn, slå ihop, dela och versioner (F1-03–F1-08)."""

import io
import re
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select

from app import create_app
from core import documents
from extensions import db
from models import Document, User
from tests import pdfs
from tests.conftest import TestTenant, local_login
from tests.seed import PASSWORDS


@pytest.fixture
def anna(app: Flask, tenant: TestTenant) -> FlaskClient:
    client = app.test_client()
    assert local_login(client, tenant, 'anna', PASSWORDS['anna']).headers['Location'] == '/'
    return client


def _upload(client: FlaskClient, *files: tuple[str, bytes]) -> Any:
    return client.post('/ladda-upp', data={'files': [(io.BytesIO(data), name) for name, data in files]},
                       content_type='multipart/form-data')


def _doc_id(app: Flask, tenant: TestTenant, title: str) -> int:
    with app.app_context(), tenant.context():
        return db.session.scalars(select(Document.id).where(Document.title == title)).one()


def _latest(app: Flask, tenant: TestTenant, doc_id: int) -> tuple[int, bytes]:
    with app.app_context(), tenant.context():
        user = db.session.scalars(select(User).where(User.username == 'anna')).one()
        version, data = documents.read(user, doc_id)
        return version.version_no, data


def test_startsidan_visar_uppgifterna_och_bara_egna_dokument(anna: FlaskClient) -> None:
    page = anna.get('/').get_data(as_text=True)
    for task in ('Slå ihop', 'Dela', 'Kommentera', 'Exportera', 'Fråga AI'):
        assert f'<span class="tile-title">{task}</span>' in page
    assert 'Offert Kund AB' in page and 'Anteckningar' in page
    assert 'Faktura oktober' not in page    # bertils
    assert 'name="csrf_token"' in page


def test_sok_bland_dokumenten(anna: FlaskClient) -> None:
    page = anna.get('/?q=offert').get_data(as_text=True)
    assert 'Offert Kund AB' in page and 'Anteckningar' not in page


def test_uppladdning_via_formularet(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    res = _upload(anna, ('Avtal.pdf', pdfs.make('A', 3)))
    doc_id = _doc_id(app, tenant, 'Avtal.pdf')
    assert res.headers['Location'] == f'/dokument/{doc_id}'
    page = anna.get(f'/dokument/{doc_id}').get_data(as_text=True)
    assert '3 sidor' in page and page.count('alt="Sida ') == 3


def test_flera_filer_pa_en_gang(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    res = _upload(anna, ('A.pdf', pdfs.make('A', 1)), ('B.pdf', pdfs.make('B', 2)))
    assert res.headers['Location'] == '/'
    assert '2 filer uppladdade' in anna.get('/').get_data(as_text=True)


def test_fel_filtyp_ger_meddelande_och_inget_dokument(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    res = _upload(anna, ('bild.pdf', b'\x89PNG\r\n\x1a\nbild'))
    assert res.status_code == 302
    assert 'Filen är inte en PDF.' in anna.get('/').get_data(as_text=True)
    with app.app_context(), tenant.context():
        assert db.session.scalars(select(Document).where(Document.title == 'bild.pdf')).all() == []


def test_sidbild_och_nedladdning(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Offert; mars & X.pdf', pdfs.make('O', 2)))
    doc_id = _doc_id(app, tenant, 'Offert; mars & X.pdf')
    image = anna.get(f'/dokument/{doc_id}/v1/sida-2.png?dpi=40')
    assert image.mimetype == 'image/png' and image.data.startswith(b'\x89PNG')
    assert anna.get(f'/dokument/{doc_id}/v1/sida-3.png?dpi=40').status_code == 404
    assert anna.get(f'/dokument/{doc_id}/v1/sida-1.png?dpi=999').status_code == 400
    download = anna.get(f'/dokument/{doc_id}/ladda-ner')
    assert download.mimetype == 'application/pdf'
    disposition = download.headers['Content-Disposition']
    assert disposition == 'attachment; filename="Offert_ mars _ X.pdf"'
    assert pdfs.texts(download.data) == ['O1', 'O2']


def test_andras_dokument_ger_404(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    bertil_doc = _doc_id(app, tenant, 'Faktura oktober')
    for path in (f'/dokument/{bertil_doc}', f'/dokument/{bertil_doc}/v1/sida-1.png', f'/dokument/{bertil_doc}/ladda-ner',
                 f'/dela/{bertil_doc}'):
        assert anna.get(path).status_code == 404, path
    assert anna.post(f'/dokument/{bertil_doc}/sidor', data={'action': 'ta-bort', 'pages': ['1']}).status_code == 404


def test_rotera_ta_bort_infoga_och_aterstall(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Sidor.pdf', pdfs.make('S', 3)), ('Bilaga.pdf', pdfs.make('B', 2)))
    doc_id, bilaga = _doc_id(app, tenant, 'Sidor.pdf'), _doc_id(app, tenant, 'Bilaga.pdf')
    anna.post(f'/dokument/{doc_id}/sidor', data={'action': 'rotera-hoger', 'pages': ['1']})
    anna.post(f'/dokument/{doc_id}/sidor', data={'action': 'ta-bort', 'pages': ['2']})
    anna.post(f'/dokument/{doc_id}/sidor', data={'action': 'tom-sida', 'after': '0'})
    res = anna.post(f'/dokument/{doc_id}/sidor', data={'action': 'infoga', 'source': str(bilaga),
                                                       'source_pages': '2', 'after': '3'})
    assert 'Sparat som version 5' in anna.get(res.headers['Location']).get_data(as_text=True)
    version_no, data = _latest(app, tenant, doc_id)
    assert version_no == 5
    assert pdfs.texts(data) == ['', 'S1', 'S3', 'B2']
    assert pdfs.rotations(data) == [0, 90, 0, 0]
    anna.post(f'/dokument/{doc_id}/aterstall/1')
    version_no, data = _latest(app, tenant, doc_id)
    assert version_no == 6 and pdfs.texts(data) == ['S1', 'S2', 'S3']
    history = anna.get(f'/dokument/{doc_id}').get_data(as_text=True)
    assert 'Återställd' in history and 'Sidor ändrade' in history


def test_ta_bort_alla_sidor_ger_meddelande(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Två.pdf', pdfs.make('T', 2)))
    doc_id = _doc_id(app, tenant, 'Två.pdf')
    res = anna.post(f'/dokument/{doc_id}/sidor', data={'action': 'ta-bort', 'pages': ['1', '2']},
                    headers={'Referer': f'http://localhost/dokument/{doc_id}'})
    assert 'Det går inte att ta bort alla sidor.' in anna.get(res.headers['Location']).get_data(as_text=True)
    assert _latest(app, tenant, doc_id)[0] == 1


def test_sla_ihop_i_angiven_ordning(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('A.pdf', pdfs.make('A', 1)), ('B.pdf', pdfs.make('B', 2)))
    a, b = _doc_id(app, tenant, 'A.pdf'), _doc_id(app, tenant, 'B.pdf')
    res = anna.post('/sla-ihop', data={'docs': [str(a), str(b)], f'pos-{a}': '2', f'pos-{b}': '1',
                                       'title': 'B och A.pdf'})
    merged = _doc_id(app, tenant, 'B och A.pdf')
    assert res.headers['Location'] == f'/dokument/{merged}'
    assert pdfs.texts(_latest(app, tenant, merged)[1]) == ['B1', 'B2', 'A1']


def test_sla_ihop_en_fil_ger_meddelande(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('A.pdf', pdfs.make('A', 1)))
    res = anna.post('/sla-ihop', data={'docs': [str(_doc_id(app, tenant, 'A.pdf'))], 'title': 'X.pdf'},
                    headers={'Referer': 'http://localhost/sla-ihop'})
    assert 'Välj minst två filer att slå ihop.' in anna.get(res.headers['Location']).get_data(as_text=True)


def test_dela_markerade_och_intervall(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Avtal.pdf', pdfs.make('S', 5)))
    doc_id = _doc_id(app, tenant, 'Avtal.pdf')
    assert anna.get(f'/dela/{doc_id}').get_data(as_text=True).count('name="pages"') == 5
    anna.post(f'/dela/{doc_id}', data={'mode': 'selected', 'pages': ['2', '4']})
    anna.post(f'/dela/{doc_id}', data={'mode': 'range', 'ranges': '5, 1-2'})
    res = anna.post(f'/dela/{doc_id}', data={'mode': 'each'})
    assert res.headers['Location'] == '/'
    assert pdfs.texts(_latest(app, tenant, _doc_id(app, tenant, 'Avtal – sidor 2, 4.pdf'))[1]) == ['S2', 'S4']
    assert pdfs.texts(_latest(app, tenant, _doc_id(app, tenant, 'Avtal – sidor 5, 1, 2.pdf'))[1]) == ['S5', 'S1', 'S2']
    assert pdfs.texts(_latest(app, tenant, _doc_id(app, tenant, 'Avtal – sida 3.pdf'))[1]) == ['S3']
    bad = anna.post(f'/dela/{doc_id}', data={'mode': 'range', 'ranges': '7'},
                    headers={'Referer': f'http://localhost/dela/{doc_id}'})
    assert 'Sidan 7 finns inte' in anna.get(bad.headers['Location']).get_data(as_text=True)


def test_sida_i_storre_format_med_zoom_och_bladdring(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Zoom.pdf', pdfs.make('Z', 3)))
    doc_id = _doc_id(app, tenant, 'Zoom.pdf')
    page = anna.get(f'/dokument/{doc_id}/v1/sida-2?dpi=150').get_data(as_text=True)
    assert 'Sida 2 av 3' in page
    assert f'/dokument/{doc_id}/v1/sida-2.png?dpi=150' in page
    assert f'/dokument/{doc_id}/v1/sida-1?dpi=150' in page and f'/dokument/{doc_id}/v1/sida-3?dpi=150' in page
    assert '208 %' in page and 'aria-current="true">208 %' in page
    assert anna.get(f'/dokument/{doc_id}/v1/sida-4').status_code == 404
    assert anna.get(f'/dokument/{doc_id}/v1/sida-1?dpi=999').status_code == 400
    small, large = (anna.get(f'/dokument/{doc_id}/v1/sida-1.png?dpi={d}').data for d in (72, 150))
    assert len(large) > len(small)


def test_sok_i_dokumentets_text(app: Flask, tenant: TestTenant, anna: FlaskClient) -> None:
    _upload(anna, ('Sök.pdf', pdfs.make('Belopp', 4)))
    doc_id = _doc_id(app, tenant, 'Sök.pdf')
    page = anna.get(f'/dokument/{doc_id}?sok=BELOPP3').get_data(as_text=True)
    assert '”BELOPP3” finns på sidan 3.' in page
    assert page.count('thumb-hit') == 1
    all_pages = anna.get(f'/dokument/{doc_id}?sok=belopp').get_data(as_text=True)
    assert '”belopp” finns på sidorna 1, 2, 3, 4.' in all_pages
    none = anna.get(f'/dokument/{doc_id}?sok=saknas').get_data(as_text=True)
    assert 'Ingen träff på ”saknas”.' in none


def test_kommande_funktioner_sager_vilken_fas(anna: FlaskClient) -> None:
    assert 'byggs i fas 3' in anna.get('/kommer-snart/fraga-ai').get_data(as_text=True)
    assert anna.get('/kommer-snart/okand').status_code == 404


def test_alla_formular_skyddas_av_csrf(app: Flask, tenant: TestTenant) -> None:
    """Med CSRF påslaget: varje formulär på sidorna bär sin nyckel, och ett anrop utan den nekas."""
    protected = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': True})
    client = protected.test_client()
    with app.app_context(), tenant.context():
        user = db.session.scalars(select(User).where(User.username == 'anna')).one()
        doc = documents.upload(user, 'Skyddad.pdf', pdfs.make('C', 2))
        db.session.commit()
        documents.change(user, doc.id, lambda d: d)   # två versioner, så att formuläret Återställ visas
        db.session.commit()
        doc_id, user_id = doc.id, user.id
    with client.session_transaction() as sess:
        sess['tenant_id'], sess['username'], sess['_user_id'] = tenant.tenant_id, 'anna', str(user_id)
    for path, expected in (('/', 2), (f'/dokument/{doc_id}', 4), ('/sla-ihop', 2), (f'/dela/{doc_id}', 2)):
        page = client.get(path).get_data(as_text=True)
        forms = len(re.findall(r'<form method="post"', page))
        assert forms == expected, path   # utloggning + sidans formulär; räknas så att inget formulär glöms bort
        assert page.count('name="csrf_token"') == forms, path
    assert client.post(f'/dokument/{doc_id}/sidor', data={'action': 'ta-bort', 'pages': ['1']}).status_code == 400

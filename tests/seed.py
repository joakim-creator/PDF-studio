"""
Testdata för bolagsdatabasen (F0-07): rader i **varje** tabell, så att åtkomstproven har något att se och inte se.

Personerna och vad de får:

| Användare | Roll | Äger | Ser dessutom | Tillägg |
|---|---|---|---|---|
| anna | vanlig | Offert Kund AB, Anteckningar | – | – |
| bertil | vanlig | Faktura oktober | Offert Kund AB (delad) | – |
| cecilia | administratör | – | – | gdpr.besluta, utdelat uttryckligen av erik (administratör får inget automatiskt) |
| david | inaktiverad | Gammal rapport | – | – |
| erik | vanlig | Hyresavtal L25 | – | dokument.radera, konton.hantera |

Inloggning: anna, cecilia, david och erik har lokala konton (`PASSWORDS`); bertil loggar bara in med Microsoft
(`BERTIL_OID`). Ingen har registrerat engångskoden än.

Lagringsnycklarna börjar med bolagets slug; mallen använder `mall` och fixturen byter till provbolagets.
"""

from decimal import Decimal

from werkzeug.security import generate_password_hash

from extensions import db
from models import (
    AiUsage,
    Annotation,
    AuditEvent,
    Document,
    DocumentShare,
    DocumentVersion,
    Job,
    LoginEvent,
    User,
    UserPermission,
)

DOCUMENTS = {
    'Offert Kund AB': 'anna',
    'Anteckningar': 'anna',
    'Faktura oktober': 'bertil',
    'Gammal rapport': 'david',
    'Hyresavtal L25': 'erik',
}


PASSWORDS = {
    'anna': 'anna-losenord-1234',
    'cecilia': 'cecilia-losenord-12',
    'david': 'david-losenord-123',
    'erik': 'erik-losenord-1234',
}
BERTIL_OID = '00000000-0000-0000-0000-00000000b3r7'
SEED_IP = '198.51.100.250'   # seedens rad i inloggningsloggen; proven bortser från den adressen


def _sha(n: int) -> str:
    return f'{n:064x}'


def seed_all(slug: str) -> None:
    users = {
        'anna': User(username='anna', display_name='Anna Andersson', email='anna@prov.invalid'),
        'bertil': User(username='bertil', display_name='Bertil Berg', email='bertil@prov.invalid',
                       entra_oid=BERTIL_OID),
        'cecilia': User(username='cecilia', display_name='Cecilia Ceder', is_admin=True),
        'david': User(username='david', display_name='David Dal', active=False),
        'erik': User(username='erik', display_name='Erik Ek'),
    }
    for name, password in PASSWORDS.items():
        users[name].password_hash = generate_password_hash(password)
    db.session.add_all(users.values())
    db.session.flush()

    for permission in ('dokument.radera', 'konton.hantera'):
        db.session.add(UserPermission(user_id=users['erik'].id, permission=permission,
                                      granted_by=users['cecilia'].id))
    db.session.add(UserPermission(user_id=users['cecilia'].id, permission='gdpr.besluta',
                                  granted_by=users['erik'].id))

    docs: dict[str, Document] = {}
    versions: dict[str, DocumentVersion] = {}
    for n, (title, owner) in enumerate(DOCUMENTS.items(), start=1):
        doc = Document(title=title, owner_id=users[owner].id)
        db.session.add(doc)
        db.session.flush()
        version = DocumentVersion(document_id=doc.id, version_no=1, storage_key=f'{slug}/documents/{n:04d}.pdf',
                                  sha256=_sha(n), page_count=n, size_bytes=1000 * n, source='upload',
                                  created_by=users[owner].id)
        db.session.add(version)
        db.session.flush()
        docs[title], versions[title] = doc, version

    offert_v2 = DocumentVersion(document_id=docs['Offert Kund AB'].id, version_no=2,
                                parent_version_id=versions['Offert Kund AB'].id,
                                storage_key=f'{slug}/documents/0001-v2.pdf', sha256=_sha(99), page_count=1,
                                size_bytes=1100, source='annotate', created_by=users['anna'].id)
    db.session.add(offert_v2)
    db.session.add(DocumentShare(document_id=docs['Offert Kund AB'].id, user_id=users['bertil'].id,
                                 granted_by=users['anna'].id))
    db.session.flush()

    db.session.add(Annotation(version_id=offert_v2.id, page=1, kind='note',
                              geometry={'x': 72, 'y': 640, 'w': 300, 'h': 14},
                              body='Stämmer totalen?', author_id=users['anna'].id))
    job = Job(kind='ocr', status='done', version_id=versions['Faktura oktober'].id,
              requested_by=users['bertil'].id, cost_sek=Decimal('0.4200'))
    db.session.add(job)
    db.session.flush()
    db.session.add(AiUsage(user_id=users['bertil'].id, job_id=job.id, model='claude-opus-5-5',
                           input_tokens=3000, output_tokens=400, cost_sek=Decimal('0.4200')))
    db.session.add(LoginEvent(user_id=users['cecilia'].id, username='cecilia', method='password', outcome='ok',
                              ip=SEED_IP))
    db.session.add(AuditEvent(user_id=users['cecilia'].id, area='konton', action='tillagg',
                              description='erik fick dokument.radera'))
    db.session.commit()

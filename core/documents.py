"""
Dokument och versioner (F1-01, F1-02, F1-05–F1-08). Här möts åtkomstkontrollen, fillagringen och sidoperationerna.

- **Uppladdning:** filtypen kontrolleras på innehållet (`%PDF-` och att pikepdf kan öppna filen), aldrig på
  ändelsen; högst 32 MB. Filen får en ny nyckel `<bolag>/documents/<uuid>.pdf`; namnet användaren gav blir titeln.
- **Originalet rörs aldrig.** Varje ändring blir en ny version med föräldern som pekare. Att återställa en äldre
  version är också en ny version (källa `restore`).
- **Slå ihop och dela** ger nya dokument; källorna är oförändrade.
- Versionsnumret tas fram under radlås på dokumentet, så att två samtidiga ändringar inte får samma nummer.
"""

import hashlib
import uuid
from typing import Any

from flask import current_app, g
from sqlalchemy import func, select

from core import pdfops
from core.access import AccessDenied, get_document
from core.locking import lock
from core.storage import Storage
from extensions import db
from models import Document, DocumentVersion, User

MAX_BYTES = 32 * 1024 * 1024
MAX_TITLE = 255


class DocumentError(ValueError):
    """Användarens fel (fel filtyp, för stor fil, sida som inte finns). Meddelandet visas för användaren."""


def storage() -> Storage:
    return current_app.extensions['pdfstudio_storage']  # type: ignore[no-any-return]


def _slug() -> str:
    tenant = g.get('tenant')
    slug = getattr(tenant, 'slug', None)
    if not slug:
        raise RuntimeError('inget bolag valt — dokument kan bara hanteras inom ett bolag')
    return str(slug)


def _title(name: str) -> str:
    """Bara filnamnet, utan sökväg och styrtecken (radbrytningar i ett filnamn hör inte hemma i en rubrik)."""
    title = ''.join(c for c in (name or '') if c >= ' ' and c != '\x7f')
    title = title.strip().replace('\\', '/').rsplit('/', 1)[-1].strip()
    return (title or 'Namnlöst.pdf')[:MAX_TITLE]


def _checked(data: bytes) -> int:
    if len(data) > MAX_BYTES:
        raise DocumentError('Filen är större än 32 MB.')
    if not data:
        raise DocumentError('Filen är tom.')
    try:
        return pdfops.page_count(data)
    except pdfops.PdfError as error:
        raise DocumentError(str(error)) from None


def _new_version(user: User, document: Document, data: bytes, source: str,
                 parent: DocumentVersion | None) -> DocumentVersion:
    pages = _checked(data)
    key = f'{_slug()}/documents/{uuid.uuid4().hex}.pdf'
    storage().put(key, data)
    version = DocumentVersion(
        document_id=document.id, version_no=(parent.version_no + 1) if parent else 1,
        parent_version_id=parent.id if parent else None, storage_key=key, sha256=hashlib.sha256(data).hexdigest(),
        page_count=pages, size_bytes=len(data), source=source, created_by=user.id)
    db.session.add(version)
    db.session.flush()
    return version


def _create(user: User, title: str, data: bytes, source: str) -> Document:
    document = Document(title=_title(title), owner_id=user.id)
    db.session.add(document)
    db.session.flush()
    _new_version(user, document, data, source, None)
    return document


def latest(document: Document) -> DocumentVersion:
    return db.session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                              .order_by(DocumentVersion.version_no.desc()).limit(1)).one()


def versions(user: User, document_id: int) -> list[DocumentVersion]:
    document = get_document(user, document_id)
    return list(db.session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id)
                                   .order_by(DocumentVersion.version_no)))


def read(user: User, document_id: int, version_no: int | None = None) -> tuple[DocumentVersion, bytes]:
    """Innehållet i en version (den senaste om inget anges), efter åtkomstkontroll."""
    document = get_document(user, document_id)
    if version_no is None:
        version = latest(document)
    else:
        found = db.session.scalars(select(DocumentVersion).where(DocumentVersion.document_id == document.id,
                                                                 DocumentVersion.version_no == version_no)).one_or_none()
        if found is None:
            raise AccessDenied('Versionen finns inte.')
        version = found
    return version, storage().get(version.storage_key)


def upload(user: User, filename: str, data: bytes) -> Document:
    """Ett nytt dokument av en uppladdad fil. Anroparen committar."""
    return _create(user, filename, data, 'upload')


def change(user: User, document_id: int, operation: Any, source: str = 'pages') -> DocumentVersion:
    """Ny version av ett dokument: `operation(bytes) -> bytes` körs på den senaste versionen. Anroparen committar."""
    document = get_document(user, document_id)
    lock(db.session, Document, document.id)   # en ändring i taget per dokument
    parent = latest(document)
    try:
        data = operation(storage().get(parent.storage_key))
    except pdfops.PdfError as error:
        raise DocumentError(str(error)) from None
    return _new_version(user, document, data, source, parent)


def restore(user: User, document_id: int, version_no: int) -> DocumentVersion:
    """En äldre version blir den senaste — som en ny version, så att historiken finns kvar."""
    old, data = read(user, document_id, version_no)
    document = get_document(user, document_id)
    lock(db.session, Document, document.id)
    parent = latest(document)
    if parent.id == old.id:
        raise DocumentError('Det är redan den senaste versionen.')
    return _new_version(user, document, data, 'restore', parent)


def merge(user: User, document_ids: list[int], title: str) -> Document:
    """Ett nytt dokument av flera, i den ordning de anges. Anroparen committar."""
    if len(document_ids) < 2:
        raise DocumentError('Välj minst två filer att slå ihop.')
    files = [read(user, doc_id)[1] for doc_id in document_ids]
    try:
        return _create(user, title, pdfops.merge(files), 'merge')
    except pdfops.PdfError as error:
        raise DocumentError(str(error)) from None


def split(user: User, document_id: int, mode: str, ranges: str = '', pages: list[int] | None = None) -> list[Document]:
    """Nya dokument ur ett: `selected` (markerade sidor), `range` (t.ex. 1-3, 5) eller `each` (en fil per sida)."""
    version, data = read(user, document_id)
    base = db.session.get(Document, document_id).title.removesuffix('.pdf')  # type: ignore[union-attr]
    try:
        if mode == 'each':
            parts = pdfops.split_each(data)
            return [_create(user, f'{base} – sida {n}.pdf', part, 'split') for n, part in enumerate(parts, 1)]
        chosen = pdfops.parse_ranges(ranges, version.page_count) if mode == 'range' else list(pages or [])
        label = ', '.join(str(p) for p in chosen) if len(chosen) <= 5 else f'{len(chosen)} sidor'
        return [_create(user, f'{base} – sidor {label}.pdf', pdfops.extract(data, chosen), 'split')]
    except pdfops.PdfError as error:
        raise DocumentError(str(error)) from None


def count_versions(document_id: int) -> int:
    return db.session.scalar(select(func.count()).select_from(DocumentVersion)
                             .where(DocumentVersion.document_id == document_id)) or 0

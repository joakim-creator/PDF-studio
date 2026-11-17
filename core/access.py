"""
Åtkomstkontroll inom ett bolag (F0-06). Mellan bolag skiljer databaserna (B-004).

- En användare ser sina egna dokument och de som delats med hen.
- Inaktiverade konton ser ingenting.
- Radering kräver tillägget `dokument.radera`, även för administratörer, och lämnar en rad i händelseloggen.

Alla dokumentfrågor i appen ska gå via `visible_documents` och `get_document`, aldrig direkt mot `Document`
(vaktprov i tests/test_vakt.py).
"""

from sqlalchemy import or_, select
from sqlalchemy.sql import Select

from core.audit import log
from core.timeutil import utcnow
from extensions import db
from models import Document, DocumentShare, User, UserPermission

DELETE_DOCUMENT = 'dokument.radera'


class AccessDenied(Exception):
    """Användaren får inte göra det hen försökte. `permission` anger vilket tillägg som krävs, om något."""

    def __init__(self, message: str, permission: str | None = None) -> None:
        super().__init__(message)
        self.permission = permission


def has_permission(user: User, permission: str) -> bool:
    if not user.active:
        return False
    return db.session.get(UserPermission, (user.id, permission)) is not None


def visible_documents(user: User) -> Select:
    """Frågan för de dokument användaren får se, utan papperskorgen."""
    if not user.active:
        return select(Document).where(False)  # type: ignore[arg-type]
    shared = select(DocumentShare.document_id).where(DocumentShare.user_id == user.id)
    return (select(Document)
            .where(Document.deleted_at.is_(None))
            .where(or_(Document.owner_id == user.id, Document.id.in_(shared))))


def get_document(user: User, document_id: int) -> Document:
    """Ett dokument användaren får se. Okänt och otillåtet ger samma fel, så att id:n inte går att gissa."""
    doc = db.session.scalar(visible_documents(user).where(Document.id == document_id))
    if doc is None:
        raise AccessDenied('Dokumentet finns inte.')
    return doc


def require(user: User, permission: str, message: str) -> None:
    if not has_permission(user, permission):
        raise AccessDenied(message, permission)


def delete_document(user: User, document_id: int) -> None:
    """Flytta ett dokument till papperskorgen. Kräver tillägget och loggas."""
    doc = get_document(user, document_id)
    require(user, DELETE_DOCUMENT, 'Du saknar tillägget för att radera dokument.')
    doc.deleted_at = utcnow()
    log(user, 'dokument', 'radera', f'Dokument {doc.id} ”{doc.title}” flyttat till papperskorgen')

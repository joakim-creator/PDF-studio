"""
Bolagsdatabasens tabeller (F0-04, F0-05). Varje bolag har en egen databas med exakt de här tabellerna.

Regler som schemat själv upprätthåller:
- **Originalet rörs aldrig.** En ändring av ett dokument blir en ny rad i `document_versions` som pekar på sin
  förälder; versionsnumret är unikt per dokument.
- **Konton inaktiveras, raderas aldrig.** Allt som pekar på ett konto är spårbarheten; främmande nycklar utan
  kaskad gör att en radering av ett konto som skapat något stoppas av databasen.
- **Pengar är numeric**, aldrig flyttal (`cost_sek`).
- **Tid är timestamptz** (UTC).
- Varje främmande nyckel har ett index (vaktprov i tests/test_vakt.py).

Genererad SQL för migrationerna: migrations/tenant/. Ändras modellerna krävs en ny migration — vaktprovet
tests/test_schema_pg.py faller annars. Varje kolumn anger `nullable` uttryckligen, så att typannoteringen aldrig
ändrar schemat.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from flask_login import UserMixin
from sqlalchemy.orm import Mapped, mapped_column

from core.timeutil import utcnow
from extensions import db

VERSION_SOURCES = ('upload', 'merge', 'split', 'pages', 'annotate', 'ocr', 'compress')
ANNOTATION_KINDS = ('highlight', 'underline', 'freetext', 'note', 'ink', 'stamp')
JOB_KINDS = ('ocr', 'word', 'excel', 'podcast', 'compress', 'image')
JOB_STATUSES = ('queued', 'running', 'done', 'failed')
LOGIN_METHODS = ('password', 'totp', 'microsoft')

TS = DateTime(timezone=True)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(UserMixin, db.Model):  # type: ignore[name-defined]
    """En användare i bolaget. Entra är huvudvägen; lokala konton har lösenord och engångskod (F0-13)."""

    __tablename__ = 'users'
    __table_args__ = (CheckConstraint('failed_logins >= 0', name='ck_users_failed_logins'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entra_oid: Mapped[str | None] = mapped_column(String(36), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(Text, nullable=True)  # krypterad (Fernet), nyckeln i miljön
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)
    totp_enabled_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)   # appen registrerad (F0-13)
    last_login_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class LoginEvent(db.Model):  # type: ignore[name-defined]
    """Varje inloggningsförsök (F0-13): vem, metod, utfall, klientens adress. Även okända användarnamn."""

    __tablename__ = 'login_events'
    __table_args__ = (CheckConstraint(_in('method', LOGIN_METHODS), name='ck_login_events_method'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    ip: Mapped[str] = mapped_column(String(45), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)


class UserPermission(db.Model):  # type: ignore[name-defined]
    """Uttryckliga tillägg, till exempel `dokument.radera`. Administratör får inga automatiskt (backend-grund 7)."""

    __tablename__ = 'user_permissions'

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), primary_key=True)
    permission: Mapped[str] = mapped_column(String(64), primary_key=True)
    granted_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class Document(db.Model):  # type: ignore[name-defined]
    """Ett dokument. Innehållet ligger i versionerna; dokumentet är det som visas i listan."""

    __tablename__ = 'documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)    # i papperskorgen; töms efter 7 dagar
    purge_after: Mapped[datetime | None] = mapped_column(TS, nullable=True)   # gallras då (F0-16)


class DocumentVersion(db.Model):  # type: ignore[name-defined]
    """En version av ett dokument. Skrivs en gång och ändras aldrig."""

    __tablename__ = 'document_versions'
    __table_args__ = (
        UniqueConstraint('document_id', 'version_no', name='uq_document_versions_no'),
        CheckConstraint('version_no >= 1', name='ck_document_versions_no'),
        CheckConstraint('page_count >= 1', name='ck_document_versions_pages'),
        CheckConstraint('size_bytes >= 1', name='ck_document_versions_size'),
        CheckConstraint(_in('source', VERSION_SOURCES), name='ck_document_versions_source'),
        CheckConstraint('(version_no = 1) = (parent_version_id IS NULL)', name='ck_document_versions_parent'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey('documents.id'), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('document_versions.id'),
                                                          nullable=True, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # <bolag>/documents/<uuid>.pdf
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class DocumentShare(db.Model):  # type: ignore[name-defined]
    """Ett dokument som ägaren delat med en kollega i bolaget."""

    __tablename__ = 'document_shares'

    document_id: Mapped[int] = mapped_column(Integer, ForeignKey('documents.id'), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), primary_key=True, index=True)
    granted_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    granted_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class Annotation(db.Model):  # type: ignore[name-defined]
    """En kommentar eller markering på en sida i en version. Skrivs in i PDF:en som annotering vid sparande (F2)."""

    __tablename__ = 'annotations'
    __table_args__ = (
        CheckConstraint('page >= 1', name='ck_annotations_page'),
        CheckConstraint(_in('kind', ANNOTATION_KINDS), name='ck_annotations_kind'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey('document_versions.id'), nullable=False, index=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    geometry: Mapped[Any] = mapped_column(JSON, nullable=False)   # rektangel eller punkter i PDF-koordinater
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)


class Job(db.Model):  # type: ignore[name-defined]
    """Ett långt jobb i kön: OCR, Word, Excel, podcast, komprimering, bilder."""

    __tablename__ = 'jobs'
    __table_args__ = (
        CheckConstraint(_in('kind', JOB_KINDS), name='ck_jobs_kind'),
        CheckConstraint(_in('status', JOB_STATUSES), name='ck_jobs_status'),
        CheckConstraint('cost_sek >= 0', name='ck_jobs_cost'),
        Index('ix_jobs_status_created', 'status', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='queued')
    version_id: Mapped[int] = mapped_column(Integer, ForeignKey('document_versions.id'), nullable=False, index=True)
    result_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('document_versions.id'),
                                                          nullable=True, index=True)
    requested_by: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    cost_sek: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)


class AiUsage(db.Model):  # type: ignore[name-defined]
    """Kostnaden för varje AI-anrop. Underlaget för utgiftstaket (450 kr i koden, B-005)."""

    __tablename__ = 'ai_usage'
    __table_args__ = (
        CheckConstraint('input_tokens >= 0 AND output_tokens >= 0', name='ck_ai_usage_tokens'),
        CheckConstraint('cost_sek >= 0', name='ck_ai_usage_cost'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('jobs.id'), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_sek: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)


class AuditEvent(db.Model):  # type: ignore[name-defined]
    """Händelseloggen: vem, vad, när (backend-grund 7)."""

    __tablename__ = 'audit_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    area: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TS, nullable=False, default=utcnow, index=True)

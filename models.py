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
tests/test_schema_pg.py faller annars.
"""

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)

from core.timeutil import utcnow
from extensions import db

VERSION_SOURCES = ('upload', 'merge', 'split', 'pages', 'annotate', 'ocr', 'compress')
ANNOTATION_KINDS = ('highlight', 'underline', 'freetext', 'note', 'ink', 'stamp')
JOB_KINDS = ('ocr', 'word', 'excel', 'podcast', 'compress', 'image')
JOB_STATUSES = ('queued', 'running', 'done', 'failed')


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _ts(**kwargs):  # type: ignore[no-untyped-def]
    return Column(DateTime(timezone=True), **kwargs)


class User(db.Model):  # type: ignore[name-defined]
    """En användare i bolaget. Entra är huvudvägen; lokala konton har lösenord och engångskod (F0-13)."""

    __tablename__ = 'users'
    __table_args__ = (CheckConstraint('failed_logins >= 0', name='ck_users_failed_logins'),)

    id = Column(Integer, primary_key=True)
    username = Column(String(120), unique=True, nullable=False)
    display_name = Column(String(200), nullable=False)
    email = Column(String(255))
    entra_oid = Column(String(36), unique=True)
    password_hash = Column(String(255))
    totp_secret = Column(Text)  # krypterad (Fernet), nyckeln i miljön
    is_admin = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    failed_logins = Column(Integer, nullable=False, default=0)
    locked_until = _ts()
    created_at = _ts(nullable=False, default=utcnow)


class UserPermission(db.Model):  # type: ignore[name-defined]
    """Uttryckliga tillägg, till exempel `dokument.radera`. Administratör får inga automatiskt (backend-grund 7)."""

    __tablename__ = 'user_permissions'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    permission = Column(String(64), primary_key=True)
    granted_by = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    granted_at = _ts(nullable=False, default=utcnow)


class Document(db.Model):  # type: ignore[name-defined]
    """Ett dokument. Innehållet ligger i versionerna; dokumentet är det som visas i listan."""

    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = _ts(nullable=False, default=utcnow)
    deleted_at = _ts()      # i papperskorgen; töms efter 7 dagar
    purge_after = _ts()     # gallras då (F0-16)


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

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    parent_version_id = Column(Integer, ForeignKey('document_versions.id'), index=True)
    storage_key = Column(String(255), unique=True, nullable=False)   # <bolag>/documents/<uuid>.pdf
    sha256 = Column(String(64), nullable=False)
    page_count = Column(Integer, nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    source = Column(String(16), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = _ts(nullable=False, default=utcnow)


class DocumentShare(db.Model):  # type: ignore[name-defined]
    """Ett dokument som ägaren delat med en kollega i bolaget."""

    __tablename__ = 'document_shares'

    document_id = Column(Integer, ForeignKey('documents.id'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True, index=True)
    granted_by = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    granted_at = _ts(nullable=False, default=utcnow)


class Annotation(db.Model):  # type: ignore[name-defined]
    """En kommentar eller markering på en sida i en version. Skrivs in i PDF:en som annotering vid sparande (F2)."""

    __tablename__ = 'annotations'
    __table_args__ = (
        CheckConstraint('page >= 1', name='ck_annotations_page'),
        CheckConstraint(_in('kind', ANNOTATION_KINDS), name='ck_annotations_kind'),
    )

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey('document_versions.id'), nullable=False, index=True)
    page = Column(Integer, nullable=False)
    kind = Column(String(16), nullable=False)
    geometry = Column(JSON, nullable=False)   # rektangel eller punkter i PDF-koordinater
    body = Column(Text)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    created_at = _ts(nullable=False, default=utcnow)


class Job(db.Model):  # type: ignore[name-defined]
    """Ett långt jobb i kön: OCR, Word, Excel, podcast, komprimering, bilder."""

    __tablename__ = 'jobs'
    __table_args__ = (
        CheckConstraint(_in('kind', JOB_KINDS), name='ck_jobs_kind'),
        CheckConstraint(_in('status', JOB_STATUSES), name='ck_jobs_status'),
        CheckConstraint('cost_sek >= 0', name='ck_jobs_cost'),
        Index('ix_jobs_status_created', 'status', 'created_at'),
    )

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default='queued')
    version_id = Column(Integer, ForeignKey('document_versions.id'), nullable=False, index=True)
    result_version_id = Column(Integer, ForeignKey('document_versions.id'), index=True)
    requested_by = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    cost_sek = Column(Numeric(12, 4), nullable=False, default=0)
    error = Column(Text)
    created_at = _ts(nullable=False, default=utcnow)
    started_at = _ts()
    finished_at = _ts()


class AiUsage(db.Model):  # type: ignore[name-defined]
    """Kostnaden för varje AI-anrop. Underlaget för utgiftstaket (450 kr i koden, B-005)."""

    __tablename__ = 'ai_usage'
    __table_args__ = (
        CheckConstraint('input_tokens >= 0 AND output_tokens >= 0', name='ck_ai_usage_tokens'),
        CheckConstraint('cost_sek >= 0', name='ck_ai_usage_cost'),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey('jobs.id'), index=True)
    model = Column(String(64), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost_sek = Column(Numeric(12, 4), nullable=False)
    created_at = _ts(nullable=False, default=utcnow, index=True)


class AuditEvent(db.Model):  # type: ignore[name-defined]
    """Händelseloggen: vem, vad, när (backend-grund 7)."""

    __tablename__ = 'audit_events'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    area = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    description = Column(Text, nullable=False)
    created_at = _ts(nullable=False, default=utcnow, index=True)

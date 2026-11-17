"""
Gallring och registerutdrag (F0-16, backend-grund 10). Förlaga: pe-portal/core/retention.py.

Regeln (docs/GDPR.md):
- Ett dokument i papperskorgen gallras **7 dagar** efter att det lades där.
- Ett dokument vars gallringstid (`purge_after`) passerats står på tur.
- Ett dokument utan aktivitet (ny version eller kommentar) i **24 månader** prövas av GDPR-ansvarig, som beslutar:
  gallra, eller behåll med angiven anledning och ny prövning efter 24 månader.
- AI-kostnaderna sparas 24 månader, händelseloggen 36 månader och inloggningsloggen 12 månader.

`candidates()` ändrar ingenting (torrkörning). Bara `decide()` ändrar, kräver tillägget `gdpr.besluta` och loggas.

Modulen läser bolagets alla dokument utan att gå via core.access: GDPR-ansvarig ska kunna pröva dokument hen inte
själv får öppna. Den lämnar aldrig ut dokumentens innehåll.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from core.access import AccessDenied, require
from core.audit import log
from core.timeutil import utcnow
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

TRASH_DAYS = 7
INACTIVE_MONTHS = 24
AI_USAGE_MONTHS = 24
AUDIT_MONTHS = 36
LOGIN_MONTHS = 12
DECIDE = 'gdpr.besluta'

REASON_TRASH = 'papperskorgen'
REASON_EXPIRED = 'gallringstiden har gått ut'
REASON_INACTIVE = f'ingen aktivitet på {INACTIVE_MONTHS} månader'


@dataclass(frozen=True)
class Candidate:
    document_id: int
    title: str
    owner: str
    last_activity: datetime
    reason: str


def months_before(when: datetime, months: int) -> datetime:
    """Samma dag `months` månader tidigare (sista dagen i månaden om dagen inte finns)."""
    month = when.month - 1 - months
    year, month = when.year + month // 12, month % 12 + 1
    for day in (when.day, 30, 29, 28):
        try:
            return when.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError(when)


def _aware(when: datetime) -> datetime:
    """SQLite lämnar tillbaka tider utan tidszon; allt i databasen är UTC."""
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def last_activity(document: Document) -> datetime:
    versions = db.session.scalar(select(func.max(DocumentVersion.created_at))
                                 .where(DocumentVersion.document_id == document.id))
    notes = db.session.scalar(select(func.max(Annotation.created_at)).join(DocumentVersion)
                              .where(DocumentVersion.document_id == document.id))
    return max(_aware(w) for w in (document.created_at, versions, notes) if w is not None)


def candidates(now: datetime | None = None) -> list[Candidate]:
    """Dokument som står på tur, äldst först. Ändrar ingenting."""
    now = now or utcnow()
    owners = dict(db.session.execute(select(User.id, User.username)).tuples().all())
    rows = []
    for doc in db.session.scalars(select(Document)):
        last = last_activity(doc)
        if doc.deleted_at is not None:
            if _aware(doc.deleted_at) <= now - timedelta(days=TRASH_DAYS):
                rows.append(Candidate(doc.id, doc.title, owners[doc.owner_id], last, REASON_TRASH))
        elif doc.purge_after is not None:
            if _aware(doc.purge_after) <= now:
                rows.append(Candidate(doc.id, doc.title, owners[doc.owner_id], last, REASON_EXPIRED))
        elif last <= months_before(now, INACTIVE_MONTHS):
            rows.append(Candidate(doc.id, doc.title, owners[doc.owner_id], last, REASON_INACTIVE))
    return sorted(rows, key=lambda c: c.last_activity)


def log_rows_due(now: datetime | None = None) -> dict[str, int]:
    """Antal rader i AI-kostnaderna och händelseloggen som passerat sin tid. Ändrar ingenting."""
    now = now or utcnow()
    return {
        'ai_usage': db.session.scalar(select(func.count()).select_from(AiUsage)
                                      .where(AiUsage.created_at < months_before(now, AI_USAGE_MONTHS))) or 0,
        'audit_events': db.session.scalar(select(func.count()).select_from(AuditEvent)
                                          .where(AuditEvent.created_at < months_before(now, AUDIT_MONTHS))) or 0,
        'login_events': db.session.scalar(select(func.count()).select_from(LoginEvent)
                                          .where(LoginEvent.created_at < months_before(now, LOGIN_MONTHS))) or 0,
    }


def decide(actor: User, document_id: int, keep: bool, reason: str = '') -> None:
    """GDPR-ansvarigs beslut om ett dokument. Anroparen committar."""
    require(actor, DECIDE, 'Du saknar tillägget för att besluta om gallring.')
    doc = db.session.get(Document, document_id)
    if doc is None:
        raise AccessDenied('Dokumentet finns inte.')
    now = utcnow()
    if keep:
        if not reason.strip():
            raise ValueError('ett beslut att behålla kräver en anledning')
        doc.purge_after = months_before(now, -INACTIVE_MONTHS)   # ny prövning om 24 månader
        log(actor, 'gdpr', 'behall', f'Dokument {doc.id} ”{doc.title}” behålls: {reason.strip()}. '
                                     f'Ny prövning {doc.purge_after:%Y-%m-%d}')
    else:
        doc.deleted_at = doc.deleted_at or now
        log(actor, 'gdpr', 'gallra', f'Dokument {doc.id} ”{doc.title}” gallras (papperskorgen, töms efter '
                                     f'{TRASH_DAYS} dagar)')


# ── Registerutdrag ───────────────────────────────────────────────────────────

USER_FIELDS = ('id', 'username', 'display_name', 'email', 'entra_oid', 'is_admin', 'active', 'failed_logins',
               'locked_until', 'created_at')


def _value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat(timespec='minutes') if isinstance(value, datetime) else value.isoformat()
    return str(value) if hasattr(value, 'as_tuple') else value


def _row(obj: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {f: _value(getattr(obj, f)) for f in fields}


def extract(user: User) -> dict[str, Any]:
    """Allt appen har om användaren (artikel 15). Lösenordshash och engångskod lämnas inte ut, bara att de finns."""
    shared_ids = select(DocumentShare.document_id).where(DocumentShare.user_id == user.id)
    return {
        'konto': {**_row(user, USER_FIELDS), 'lösenord': user.password_hash is not None,
                  'engångskod': user.totp_secret is not None},
        'tillägg': [_row(p, ('permission', 'granted_at')) for p in
                    db.session.scalars(select(UserPermission).where(UserPermission.user_id == user.id))],
        'egna_dokument': [_row(d, ('id', 'title', 'created_at', 'deleted_at')) for d in
                          db.session.scalars(select(Document).where(Document.owner_id == user.id))],
        'delade_dokument': [_row(d, ('id', 'title')) for d in
                            db.session.scalars(select(Document).where(Document.id.in_(shared_ids)))],
        'kommentarer': [_row(a, ('id', 'page', 'kind', 'body', 'created_at')) for a in
                        db.session.scalars(select(Annotation).where(Annotation.author_id == user.id))],
        'jobb': [_row(j, ('id', 'kind', 'status', 'cost_sek', 'created_at')) for j in
                 db.session.scalars(select(Job).where(Job.requested_by == user.id))],
        'ai_kostnader': [_row(u, ('model', 'input_tokens', 'output_tokens', 'cost_sek', 'created_at')) for u in
                         db.session.scalars(select(AiUsage).where(AiUsage.user_id == user.id))],
        'händelser': [_row(e, ('area', 'action', 'description', 'created_at')) for e in
                      db.session.scalars(select(AuditEvent).where(AuditEvent.user_id == user.id))],
    }

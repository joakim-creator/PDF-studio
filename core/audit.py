"""
Händelseloggen (F0-15, backend-grund 7): vem gjorde vad och när. Anroparen committar, så att loggraden hör till samma
transaktion som händelsen — antingen finns båda eller ingen.
"""

import logging

from extensions import db
from models import AuditEvent, User

_log = logging.getLogger('pdfstudio.audit')


def log(user: User | None, area: str, action: str, description: str) -> None:
    db.session.add(AuditEvent(user_id=user.id if user else None, area=area, action=action, description=description))
    _log.info('händelse %s.%s: %s', area, action, description)

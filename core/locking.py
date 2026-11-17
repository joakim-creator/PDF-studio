"""
Radlås som läser om (F0-17, backend-grund 9).

`SELECT … FOR UPDATE` låser raden men uppdaterar inte ett objekt som sessionen redan har läst. I PE Portal såg den
andra av två samtidiga faktureringar därför "Utförd" fast raden nyss blivit "Fakturerad". Här används alltid
`lock()`, som låser och läser om (`populate_existing`). Provet: tests/test_schema_pg.py, två sessioner.
"""

from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session, scoped_session

T = TypeVar('T')


def lock(session: Session | scoped_session[Any], model: type[T], ident: Any) -> T | None:
    """Lås raden och returnera objektet med databasens värden just nu."""
    stmt = (select(model).where(model.id == ident)  # type: ignore[attr-defined]
            .with_for_update().execution_options(populate_existing=True))
    return session.scalars(stmt).one_or_none()

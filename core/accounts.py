"""
Konton och tillägg (F0-14, F0-15; backend-grund 5 och 7).

- **Konton inaktiveras, raderas aldrig.** Allt som pekar på kontot är spårbarheten. Ett inaktiverat konto ser inga
  dokument (core.access) och nekas inloggning (F0-13); pågående session upphör när inloggningen byggs.
- **Tillägg delas ut uttryckligen** av den som har tillägget `konton.hantera`. Administratör får inga tillägg
  automatiskt, och ingen kan ge sig själv ett tillägg.
- Varje ändring lämnar en rad i händelseloggen. Anroparen committar.
"""

from core.access import AccessDenied, require
from core.audit import log
from extensions import db
from models import User, UserPermission

MANAGE_ACCOUNTS = 'konton.hantera'
KNOWN_PERMISSIONS = ('dokument.radera', MANAGE_ACCOUNTS)


def deactivate(actor: User, user: User) -> None:
    require(actor, MANAGE_ACCOUNTS, 'Du saknar tillägget för att hantera konton.')
    if actor.id == user.id:
        raise AccessDenied('Du kan inte inaktivera ditt eget konto.')
    if not user.active:
        return
    user.active = False
    log(actor, 'konton', 'inaktivera', f'{user.username} inaktiverades')


def reactivate(actor: User, user: User) -> None:
    require(actor, MANAGE_ACCOUNTS, 'Du saknar tillägget för att hantera konton.')
    if user.active:
        return
    user.active = True
    log(actor, 'konton', 'ateraktivera', f'{user.username} återaktiverades')


def grant(actor: User, user: User, permission: str) -> None:
    if permission not in KNOWN_PERMISSIONS:
        raise ValueError(f'okänt tillägg: {permission}')
    require(actor, MANAGE_ACCOUNTS, 'Du saknar tillägget för att dela ut tillägg.')
    if actor.id == user.id:
        raise AccessDenied('Du kan inte ge dig själv ett tillägg.')
    if db.session.get(UserPermission, (user.id, permission)) is not None:
        return
    db.session.add(UserPermission(user_id=user.id, permission=permission, granted_by=actor.id))
    log(actor, 'konton', 'tillagg', f'{user.username} fick {permission}')


def revoke(actor: User, user: User, permission: str) -> None:
    require(actor, MANAGE_ACCOUNTS, 'Du saknar tillägget för att ta bort tillägg.')
    row = db.session.get(UserPermission, (user.id, permission))
    if row is None:
        return
    db.session.delete(row)
    log(actor, 'konton', 'tillagg_bort', f'{user.username} förlorade {permission}')

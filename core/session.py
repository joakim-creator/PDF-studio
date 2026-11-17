"""
Sessionen och bolaget (F0-13, F0-14).

Appen har en adress för alla bolag. Bolaget väljs vid inloggningen och står i sessionen (`tenant_id`); varje anrop
slår upp det i masterdatabasen och kör mot bolagets databas. Kakan är signerad med SECRET_KEY, och sessionen är
dessutom bunden till användarnamnet: samma användar-id i ett annat bolag räcker inte.

Ett inaktiverat konto gäller inte längre — inte heller en pågående session (F0-14).
"""

import os
from datetime import timedelta
from typing import Any

from flask import Flask, g, session
from sqlalchemy import select

from core.models_master import Tenant
from extensions import db, login_manager
from models import User

SESSION_HOURS = 12


def current_tenant() -> Tenant | None:
    return g.get('tenant')


def _load_tenant() -> None:
    g.tenant = None
    g.tenant_database_url = None
    tenant_id = session.get('tenant_id')
    if not tenant_id:
        return
    tenant = db.session.scalars(select(Tenant).where(Tenant.id == tenant_id, Tenant.active.is_(True))).one_or_none()
    if tenant is None:
        session.clear()
        return
    db.session.expunge(tenant)
    g.tenant = tenant
    g.tenant_database_url = tenant.database_url


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    tenant = current_tenant()
    if tenant is None or session.get('tenant_id') != tenant.id:
        return None
    user = db.session.get(User, int(user_id))
    if user is None or not user.active or session.get('username') != user.username:
        return None
    g.user = user
    return user


def init_app(app: Flask) -> None:
    secure = os.environ.get('SESSION_COOKIE_SECURE', '0' if app.config.get('TESTING') else '1') == '1'
    app.config.update(
        SESSION_COOKIE_SECURE=secure,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        REMEMBER_COOKIE_SECURE=secure,
        REMEMBER_COOKIE_HTTPONLY=True,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    )
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Logga in för att fortsätta.'

    @app.before_request
    def _tenant_from_session() -> None:
        _load_tenant()

    @app.teardown_request
    def _close(exc: Any = None) -> None:
        db.session.remove()

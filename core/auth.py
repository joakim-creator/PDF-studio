"""
Inloggning (F0-13; backend-grund 2 och 6). Förlaga: pe-portal/auth.py.

- **Microsoft (Entra ID)** är huvudvägen. Med `ENTRA_TENANT_ID` godtas bara den katalogen (B-011). Bolaget hittas
  via katalogens id (`tid`) i inloggningen; användaren via Microsofts fasta objekt-id (`oid`), eller första gången
  via e-postadressen, och binds då till det. Ingen användare skapas automatiskt.
- **Lokala konton** (reserv, externa konsulter): bolag, användarnamn, lösenord och sedan engångskod. Lösenord minst
  12 tecken; fem fel (lösenord eller kod) låser kontot i 15 minuter; tio misslyckade försök från samma adress på en
  minut ger 429.
- **Inloggningsloggen** får en rad för varje försök, även med okända användarnamn.
- Ett okänt bolag, en okänd användare och fel lösenord ger samma meddelande, så att inget går att gissa sig till.
"""

import os
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func, select
from werkzeug.security import check_password_hash, generate_password_hash

from core import totp
from core.models_master import Tenant
from core.timeutil import utcnow
from extensions import db
from models import LoginEvent, User

auth_bp = Blueprint('auth', __name__)

PASSWORD_MIN = 12
LOCK_AFTER = 5
LOCK_MINUTES = 15
ATTEMPTS_PER_MINUTE = 10
GENERIC_ERROR = 'Fel bolag, användarnamn eller lösenord.'


def set_password(user: User, password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise ValueError(f'Lösenordet måste ha minst {PASSWORD_MIN} tecken.')
    user.password_hash = generate_password_hash(password)


def safe_next(target: str | None) -> str | None:
    """Bara en relativ adress i appen — aldrig en annan webbplats."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith('/') or target.startswith('//'):
        return None
    return target


def _use_tenant(tenant: Tenant) -> None:
    db.session.expunge(tenant)
    g.tenant = tenant
    g.tenant_database_url = tenant.database_url


def record(username: str, method: str, outcome: str, user: User | None = None) -> None:
    """En rad i inloggningsloggen. Anroparen committar."""
    db.session.add(LoginEvent(user_id=user.id if user else None, username=(username or '-')[:120], method=method,
                              outcome=outcome, ip=(request.remote_addr or '-')[:45]))


def _locked(user: User) -> bool:
    if user.locked_until is None:
        return False
    until = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=utcnow().tzinfo)
    return until > utcnow()


def _failed(user: User, method: str, outcome: str) -> None:
    user.failed_logins += 1
    if user.failed_logins >= LOCK_AFTER:
        user.locked_until = utcnow() + timedelta(minutes=LOCK_MINUTES)
    record(user.username, method, outcome, user)
    db.session.commit()


def _too_many_attempts() -> bool:
    """Räknas i inloggningsloggen, så att spärren gäller alla processer utan en gemensam cache."""
    since = utcnow() - timedelta(minutes=1)
    failed = db.session.scalar(select(func.count()).select_from(LoginEvent).where(
        LoginEvent.ip == (request.remote_addr or '-')[:45], LoginEvent.created_at >= since,
        LoginEvent.outcome != 'ok'))
    return (failed or 0) >= ATTEMPTS_PER_MINUTE


def _sign_in(user: User, tenant_id: int) -> None:
    session.clear()
    session.permanent = True
    session['tenant_id'] = tenant_id
    session['username'] = user.username
    login_user(user)
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, utcnow()
    db.session.commit()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login() -> ResponseReturnValue:
    if current_user.is_authenticated:
        return redirect(url_for('pages.home'))
    if request.method == 'POST':
        slug = request.form.get('tenant', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        tenant = db.session.scalars(select(Tenant).where(Tenant.slug == slug, Tenant.active.is_(True))).one_or_none()
        if tenant is None:
            flash(GENERIC_ERROR, 'error')
            return render_template('login.html', entra=entra_configured()), 200
        _use_tenant(tenant)
        if _too_many_attempts():
            abort(429)
        user = db.session.scalars(select(User).where(User.username == username)).one_or_none()
        if user is None:
            record(username, 'password', 'okand')
            db.session.commit()
            flash(GENERIC_ERROR, 'error')
        elif not user.active:
            record(username, 'password', 'inaktiverad', user)
            db.session.commit()
            flash('Kontot är inaktiverat. Kontakta en administratör.', 'error')
        elif _locked(user):
            record(username, 'password', 'last', user)
            db.session.commit()
            flash(f'Kontot är tillfälligt låst efter för många försök. Försök igen om {LOCK_MINUTES} minuter.',
                  'error')
        elif user.password_hash is None:
            record(username, 'password', 'inget_losenord', user)
            db.session.commit()
            flash(GENERIC_ERROR, 'error')
        elif not check_password_hash(user.password_hash, password):
            _failed(user, 'password', 'fel_losenord')
            flash(GENERIC_ERROR, 'error')
        else:
            record(username, 'password', 'ok', user)
            if not user.totp_secret:
                user.totp_secret, user.totp_enabled_at = totp.encrypt(totp.new_secret()), None
            db.session.commit()
            session['totp_pending'] = {'tenant_id': tenant.id, 'user_id': user.id,
                                       'next': safe_next(request.args.get('next'))}
            return redirect(url_for('auth.login_code'))
    return render_template('login.html', entra=entra_configured())


@auth_bp.route('/login/kod', methods=['GET', 'POST'])
def login_code() -> ResponseReturnValue:
    """Steg två för lokala konton. Första gången visas nyckeln att registrera i appen."""
    pending: dict[str, Any] = session.get('totp_pending') or {}
    tenant = db.session.get(Tenant, pending.get('tenant_id') or 0)
    if tenant is None or not tenant.active:
        session.pop('totp_pending', None)
        return redirect(url_for('auth.login'))
    tenant_id = tenant.id
    _use_tenant(tenant)
    user = db.session.get(User, pending.get('user_id') or 0)
    if user is None or not user.active:
        session.pop('totp_pending', None)
        return redirect(url_for('auth.login'))
    secret = totp.decrypt(user.totp_secret)
    if secret is None:   # krypteringsnyckeln har bytts — ny registrering
        secret = totp.new_secret()
        user.totp_secret, user.totp_enabled_at = totp.encrypt(secret), None
        db.session.commit()
    enrolling = user.totp_enabled_at is None
    if request.method == 'POST':
        if _locked(user):
            record(user.username, 'totp', 'last', user)
            db.session.commit()
            flash(f'Kontot är tillfälligt låst efter för många försök. Försök igen om {LOCK_MINUTES} minuter.',
                  'error')
        elif not totp.verify(secret, request.form.get('code', '')):
            _failed(user, 'totp', 'fel_kod')
            flash('Fel kod. Koden byts var 30:e sekund; kontrollera att telefonens klocka går rätt.', 'error')
        else:
            if enrolling:
                user.totp_enabled_at = utcnow()
            record(user.username, 'totp', 'ok', user)
            next_url = safe_next(pending.get('next'))
            _sign_in(user, tenant_id)
            return redirect(next_url or url_for('pages.home'))
        return redirect(url_for('auth.login_code'))
    return render_template('login_kod.html', username=user.username, enrolling=enrolling,
                           secret=totp.grouped(secret) if enrolling else None,
                           otpauth=totp.otpauth_uri(secret, user.username) if enrolling else None)


# ── Microsoft (Entra ID, OIDC) ───────────────────────────────────────────────

def entra_configured() -> bool:
    return all(os.environ.get(k) for k in ('ENTRA_CLIENT_ID', 'ENTRA_CLIENT_SECRET'))


def entra_tenant() -> str | None:
    """Katalogen appen är registrerad i (B-011). Satt: bara den katalogen godtas. Tom: flera organisationer (B-007)."""
    return os.environ.get('ENTRA_TENANT_ID', '').strip().lower() or None


def entra_authority() -> str:
    return f'https://login.microsoftonline.com/{entra_tenant() or "organizations"}'


def entra_app() -> Any:
    """MSAL-klienten. Byts ut i proven — de anropar aldrig Microsoft."""
    import msal
    return msal.ConfidentialClientApplication(
        os.environ['ENTRA_CLIENT_ID'], client_credential=os.environ['ENTRA_CLIENT_SECRET'],
        authority=entra_authority())


def _redirect_uri() -> str:
    host = request.host
    scheme = 'http' if host.split(':')[0] in ('localhost', '127.0.0.1') else 'https'
    return f'{scheme}://{host}{url_for("auth.microsoft_callback")}'


@auth_bp.route('/auth/microsoft')
def microsoft_login() -> ResponseReturnValue:
    if not entra_configured():
        abort(404)
    flow = entra_app().initiate_auth_code_flow(scopes=[], redirect_uri=_redirect_uri(), prompt='select_account')
    session['entra_flow'] = flow
    session['entra_next'] = safe_next(request.args.get('next'))
    return redirect(flow['auth_uri'])


def _deny(message: str, username: str = '', user: User | None = None, outcome: str = 'nekad') -> ResponseReturnValue:
    if g.get('tenant_database_url'):
        record(username or '(microsoft)', 'microsoft', outcome, user)
        db.session.commit()
    flash(message, 'error')
    return redirect(url_for('auth.login'))


@auth_bp.route('/auth/microsoft/callback')
def microsoft_callback() -> ResponseReturnValue:
    if not entra_configured():
        abort(404)
    flow = session.pop('entra_flow', None)
    next_url = session.pop('entra_next', None)
    if not flow:
        return _deny('Inloggningen gick ut eller startades inte här. Försök igen.')
    # MSAL kontrollerar state, nonce, PKCE och id-tokenets mottagare, utfärdare och giltighetstid.
    result = entra_app().acquire_token_by_auth_code_flow(flow, request.args.to_dict())
    if 'error' in result:
        return _deny('Microsoft-inloggningen avbröts eller misslyckades. Försök igen.')
    claims = result.get('id_token_claims') or {}
    tid, oid = claims.get('tid'), claims.get('oid')
    if entra_tenant() and str(tid or '').lower() != entra_tenant():
        return _deny('Organisationen är inte ansluten till PDF-studio.')
    email = (claims.get('preferred_username') or claims.get('email') or '').strip().lower()
    tenant = db.session.scalars(select(Tenant).where(Tenant.entra_tenant_id == tid,
                                                     Tenant.active.is_(True))).one_or_none() if tid else None
    if tenant is None or not oid:
        return _deny('Organisationen är inte ansluten till PDF-studio.')
    tenant_id = tenant.id
    _use_tenant(tenant)
    user = db.session.scalars(select(User).where(User.entra_oid == oid)).one_or_none()
    if user is None and email:
        user = db.session.scalars(select(User).where(func.lower(User.email) == email,
                                                     User.entra_oid.is_(None))).one_or_none()
        if user is not None:
            user.entra_oid = oid   # bind vid första inloggningen
    if user is None:
        return _deny(f'Microsoft-kontot {email or "(okänt)"} är inte upplagt i PDF-studio. Kontakta en '
                     'administratör.', email)
    if not user.active:
        return _deny('Kontot är inaktiverat. Kontakta en administratör.', email, user, 'inaktiverad')
    record(user.username, 'microsoft', 'ok', user)
    _sign_in(user, tenant_id)
    return redirect(safe_next(next_url) or url_for('pages.home'))


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout() -> ResponseReturnValue:
    logout_user()
    session.clear()
    return redirect(url_for('auth.login'))

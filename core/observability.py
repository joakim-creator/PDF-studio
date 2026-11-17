"""
Ärendenummer, logg, felsida, hälsosida och felrapportering (F0-03, F0-11; backend-grund 3).
Förlaga: pe-portal/core/observability.py.

- **Ärendenummer** (`X-Request-ID`): varje anrop får ett. Nginx kan skicka sitt eget, annars skapas ett här. Det står
  i svaret, i varje loggrad, på felsidan och i felrapporten.
- **Loggen**: en rad per anrop (metod, adress, status, tid, ärendenummer) och fel med stack, till stderr.
  ``PDF_LOG_REQUESTS=0`` stänger av raden per anrop.
- **Felsidan** är fristående (visas även när databasen är nere) och visar inga interna detaljer.
- **Felrapportering** till GlitchTip (samma bibliotek som Sentry) när ``GLITCHTIP_DSN`` finns, aldrig i proven.
  Rapporten tvättas: bara stack, adress, metod, ärendenummer och användare — inga kakor, formulärdata, huvuden,
  frågesträngar eller lokala variabler. Tak i koden: ``ERROR_REPORT_HOURLY_MAX`` per timme och process (standard
  50); taket på kontot sätts i GlitchTip (driftsattning.md).
- **Hälsosidan** ``/health``: publik, utan detaljer. ``ok`` när masterdatabasen och alla aktiva bolagsdatabaser svarar
  och inga migrationer väntar, annars 503.
"""

import logging
import os
import re
import secrets
import sys
import threading
import time
from typing import Any

from flask import Blueprint, Flask, Response, g, has_request_context, jsonify, render_template, request
from flask.typing import ResponseReturnValue
from sqlalchemy import select, text
from sqlalchemy.engine import Engine

REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9-]{1,64}$')
FORMAT = '%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s'
HOURLY_DEFAULT = 50

health_bp = Blueprint('health', __name__)
log = logging.getLogger('pdfstudio.request')


# ── Ärendenummer ─────────────────────────────────────────────────────────────

def request_id() -> str:
    """Anropets ärendenummer (skapas vid första frågan)."""
    if not has_request_context():
        return '-'
    rid = g.get('request_id')
    if rid is None:
        given = request.headers.get('X-Request-ID', '')
        rid = given if REQUEST_ID_RE.match(given) else secrets.token_hex(8)
        g.request_id = rid
    return rid


def _user_label() -> str:
    user = g.get('user') if has_request_context() else None
    return getattr(user, 'username', None) or '-'


class ContextFilter(logging.Filter):
    """Lägger ärendenumret på varje loggrad."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id()
        return True


# ── Felrapportering (GlitchTip via sentry-sdk) ───────────────────────────────

_reporting = {'enabled': False}
_cap = {'window': 0, 'count': 0}
_cap_lock = threading.Lock()


def hourly_max() -> int:
    try:
        return max(int(os.environ.get('ERROR_REPORT_HOURLY_MAX', HOURLY_DEFAULT)), 0)
    except ValueError:
        return HOURLY_DEFAULT


def reset_report_cap() -> None:
    with _cap_lock:
        _cap['window'], _cap['count'] = 0, 0


def _within_cap(now: float | None = None) -> bool:
    window = int((now or time.time()) // 3600)
    with _cap_lock:
        if _cap['window'] != window:
            _cap['window'], _cap['count'] = window, 0
        if _cap['count'] >= hourly_max():
            return False
        _cap['count'] += 1
        return True


def scrub(event: dict[str, Any], hint: Any = None) -> dict[str, Any] | None:
    """Tvättar en felrapport innan den lämnar servern. None när taket är nått."""
    if not _within_cap():
        return None
    req = event.get('request')
    if isinstance(req, dict):
        url = str(req.get('url', '')).split('?')[0]
        event['request'] = {'url': url, 'method': req.get('method')}
    event.pop('breadcrumbs', None)
    event.pop('_meta', None)
    event.pop('extra', None)
    event['user'] = {'id': _user_label()}
    event.setdefault('tags', {})['arende'] = request_id()
    return event


def init_error_reporting(dsn: str, transport: Any = None) -> None:
    """Kopplar på felrapporteringen. `transport` byts i proven — de når aldrig nätet."""
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    sentry_sdk.init(
        dsn=dsn, transport=transport, integrations=[FlaskIntegration()], default_integrations=False,
        before_send=scrub,  # type: ignore[arg-type]
        include_local_variables=False,
        traces_sample_rate=0, max_breadcrumbs=0,
        environment=os.environ.get('PDF_ENV', 'prod'), release=os.environ.get('PDF_RELEASE') or None,
    )
    _reporting['enabled'] = True


def disable_error_reporting() -> None:
    import sentry_sdk
    sentry_sdk.init(dsn=None, default_integrations=False)
    _reporting['enabled'] = False


# ── Hälsosidan ───────────────────────────────────────────────────────────────

def _check(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True
    except Exception:  # noqa: BLE001 — svaret säger bara ok/fel; orsaken står i loggen
        log.warning('hälsokontroll: databasen svarar inte', exc_info=True)
        return False


def _migrated(engine: Engine, kind: str) -> bool:
    from core import migrations
    if engine.dialect.name != 'postgresql':
        return True   # SQLite (lokalt och i proven) byggs från modellerna
    try:
        return all(state == 'körd' for _, state in migrations.status(engine, kind))
    except Exception:  # noqa: BLE001
        log.warning('hälsokontroll: migrationsstatus kunde inte läsas', exc_info=True)
        return False


@health_bp.get('/health')
def health() -> ResponseReturnValue:
    from core.db_routing import MASTER_BIND, get_engine
    from core.models_master import Tenant
    from extensions import db

    master_engine = db.engines[MASTER_BIND]
    master_ok = _check(master_engine) and _migrated(master_engine, 'master')
    total = healthy = 0
    if master_ok:
        urls = db.session.scalars(select(Tenant.database_url).where(Tenant.active.is_(True))).all()
        db.session.remove()
        total = len(urls)
        healthy = sum(1 for url in urls if _check(get_engine(url)) and _migrated(get_engine(url), 'tenant'))
    ok = master_ok and healthy == total
    response = jsonify(status='ok' if ok else 'fel', master='ok' if master_ok else 'fel',
                       bolag=f'{healthy}/{total}')
    response.headers['Cache-Control'] = 'no-store'
    return response, (200 if ok else 503)


# ── Koppla in i appen ────────────────────────────────────────────────────────

def init_app(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(ContextFilter())
    root = logging.getLogger('pdfstudio')
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)

    log_requests = os.environ.get('PDF_LOG_REQUESTS', '1') != '0'

    @app.before_request
    def _start_timer() -> None:
        g.started = time.perf_counter()
        request_id()

    @app.after_request
    def _stamp(response: Response) -> Response:
        response.headers['X-Request-ID'] = request_id()
        if log_requests:
            ms = (time.perf_counter() - g.get('started', time.perf_counter())) * 1000
            log.info('%s %s %s %.0fms', request.method, request.path, response.status_code, ms)
        return response

    @app.errorhandler(500)
    def _internal_error(error: Exception) -> ResponseReturnValue:
        """Flask har redan loggat felet med stack. Användaren får ärendenumret, inga detaljer."""
        if request.path.startswith('/api/'):
            return jsonify(error='internt fel', arende=request_id()), 500
        return render_template('error.html', request_id=request_id()), 500

    app.register_blueprint(health_bp)

    dsn = os.environ.get('GLITCHTIP_DSN')
    if dsn and not app.config.get('TESTING'):
        init_error_reporting(dsn)
        log.info('felrapportering: GlitchTip påkopplad (tak %d per timme)', hourly_max())

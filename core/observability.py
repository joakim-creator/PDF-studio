"""
Ärendenummer, logg per anrop och hälsosida (F0-03, förlaga pe-portal/core/observability.py).

- **Ärendenummer** (`X-Request-ID`): varje anrop får ett. Nginx kan skicka sitt eget, annars skapas ett här.
  Det står i svaret och i varje loggrad, så att den som felsöker hittar raden.
- **Loggen**: en rad per anrop (metod, adress, status, tid, ärendenummer) till stderr. ``PDF_LOG_REQUESTS=0``
  stänger av raden per anrop.
- **Hälsosidan** ``/health``: publik, utan detaljer. Kontrollerar än så länge bara att appen svarar; databasen och
  migrationerna läggs till i F0-04 och F0-11.

Felsidan och felrapporteringen till GlitchTip kommer i F0-11.
"""

import logging
import os
import re
import secrets
import sys
import time

from flask import Blueprint, Flask, g, has_request_context, jsonify, request
from flask.typing import ResponseReturnValue

REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9-]{1,64}$')
FORMAT = '%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s'

health_bp = Blueprint('health', __name__)
log = logging.getLogger('pdfstudio.request')


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


class ContextFilter(logging.Filter):
    """Lägger ärendenumret på varje loggrad."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id()
        return True


@health_bp.get('/health')
def health() -> ResponseReturnValue:
    return jsonify({'app': 'ok'}), 200


def init_app(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT))
    handler.addFilter(ContextFilter())
    root = logging.getLogger('pdfstudio')
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)

    log_requests = os.environ.get('PDF_LOG_REQUESTS', '1') != '0'

    @app.before_request
    def _start_timer() -> None:
        g.started = time.perf_counter()
        request_id()

    @app.after_request
    def _stamp(response):  # type: ignore[no-untyped-def]
        response.headers['X-Request-ID'] = request_id()
        if log_requests:
            ms = (time.perf_counter() - g.get('started', time.perf_counter())) * 1000
            log.info('%s %s %s %.0fms', request.method, request.path, response.status_code, ms)
        return response

    app.register_blueprint(health_bp)

"""
PDF-studio — Flask-appen (F0-03, F0-04).

    venv\\Scripts\\python -m flask --app app run --debug
"""

import os
from typing import Any

from flask import Flask

from core import observability, security
from core.db_routing import MASTER_BIND, master_engine_options
from extensions import db


def create_app(config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    master_url = (config or {}).get('MASTER_DATABASE_URL') or os.environ.get('MASTER_DATABASE_URL', '')
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', ''),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # samma gräns som Claude tar per anrop (spec 7)
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] and not app.config.get('TESTING') and not app.debug:
        raise RuntimeError('SECRET_KEY saknas i miljön (se .env.example).')
    if not master_url:
        raise RuntimeError('MASTER_DATABASE_URL saknas i miljön (se .env.example).')
    app.config['SQLALCHEMY_BINDS'] = {MASTER_BIND: {'url': master_url, **master_engine_options(master_url)}}

    db.init_app(app)
    import core.models_master  # noqa: F401 — registrerar mastertabellerna
    import models  # noqa: F401 — registrerar bolagstabellerna

    observability.init_app(app)
    security.init_app(app)
    return app

"""
PDF-studio — Flask-appen (F0-03).

    venv\\Scripts\\python -m flask --app app run --debug
"""

import os

from flask import Flask

from core import observability


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', ''),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024,  # samma gräns som Claude tar per anrop (spec 7)
    )
    if config:
        app.config.update(config)
    if not app.config['SECRET_KEY'] and not app.config.get('TESTING') and not app.debug:
        raise RuntimeError('SECRET_KEY saknas i miljön (se .env.example).')

    observability.init_app(app)
    return app

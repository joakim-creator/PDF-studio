"""Ingången för gunicorn på servern (F0-20): `gunicorn wsgi:app`. Miljön kommer från systemd (EnvironmentFile)."""

from app import create_app

app = create_app()

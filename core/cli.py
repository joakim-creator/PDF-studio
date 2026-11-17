"""
Kommandon för systemägaren (`flask --app app <kommando>`). Förlaga: pe-portal/app.py.

    gdpr-kandidater --tenant <slug>              torrkörning av gallringsregeln (F0-16)
    gdpr-utdrag <användarnamn> --tenant <slug>   registerutdrag som JSON (F0-16)
"""

import json

import click
from flask import Flask
from sqlalchemy import select

from core import retention
from core.models_master import Tenant
from core.tenant import tenant_context
from extensions import db
from models import User


def _tenant(slug: str) -> Tenant:
    tenant = db.session.scalars(select(Tenant).where(Tenant.slug == slug)).one_or_none()
    if tenant is None:
        raise click.ClickException(f'det finns inget bolag med slug {slug}')
    return tenant


def register(app: Flask) -> None:

    @app.cli.command('gdpr-kandidater')
    @click.option('--tenant', 'slug', required=True, help='Bolaget som ska prövas.')
    def gdpr_candidates(slug: str) -> None:
        """Dokument och loggrader som står på tur för gallring. Torrkörning: inget ändras."""
        tenant = _tenant(slug)
        with tenant_context(tenant):
            rows = retention.candidates()
            due = retention.log_rows_due()
        click.echo(f'{tenant.slug}: {len(rows)} dokument på tur (torrkörning — inget ändrat)')
        for row in rows:
            click.echo(f'  {row.document_id:>6}  {row.title:<40} {row.owner:<16} '
                       f'{row.last_activity:%Y-%m-%d}  {row.reason}')
        click.echo(f'  AI-kostnader äldre än {retention.AI_USAGE_MONTHS} månader: {due["ai_usage"]}')
        click.echo(f'  Händelser äldre än {retention.AUDIT_MONTHS} månader: {due["audit_events"]}')

    @app.cli.command('gdpr-utdrag')
    @click.argument('username')
    @click.option('--tenant', 'slug', required=True, help='Bolaget där användaren finns.')
    def gdpr_extract(username: str, slug: str) -> None:
        """Registerutdrag (artikel 15) för USERNAME som JSON."""
        tenant = _tenant(slug)
        with tenant_context(tenant):
            user = db.session.scalars(select(User).where(User.username == username)).one_or_none()
            if user is None:
                raise click.ClickException(f'det finns ingen användare {username} i {tenant.slug}')
            data = retention.extract(user)
        click.echo(json.dumps(data, ensure_ascii=False, indent=2))

"""
Kommandon för systemägaren (`flask --app app <kommando>`). Förlaga: pe-portal/app.py.

    bolag-skapa <slug> <namn> --databas <url>     lägger till ett bolag och bygger dess databas (F0-13)
    konto-skapa <användarnamn> --tenant <slug>    lokalt konto med lösenord; engångskoden vid första inloggningen
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

    @app.cli.command('bolag-skapa')
    @click.argument('slug')
    @click.argument('name')
    @click.option('--databas', 'database_url', required=True, help='Bolagets egen databas (PostgreSQL, eller SQLite '
                                                                    'lokalt).')
    @click.option('--entra-katalog', 'entra_tenant_id', default=None, help='Bolagets katalog-id i Entra.')
    def create_tenant(slug: str, name: str, database_url: str, entra_tenant_id: str | None) -> None:
        """Lägger till ett bolag i masterdatabasen och bygger dess databas med migrationerna."""
        from core import migrations
        from core.db_routing import get_engine
        from core.tenant import create_tenant_schema
        if db.session.scalars(select(Tenant).where(Tenant.slug == slug)).one_or_none() is not None:
            raise click.ClickException(f'bolaget {slug} finns redan')
        engine = get_engine(database_url)
        if engine.dialect.name == 'postgresql':
            ran = migrations.migrate(engine, 'tenant')
            click.echo(f'{migrations.masked(database_url)}: {len(ran)} migrationer körda')
        else:
            create_tenant_schema(database_url)   # bara lokalt; dev och prod kör PostgreSQL
            click.echo('SQLite: tabellerna skapade från modellerna (bara för lokal utveckling)')
        db.session.add(Tenant(slug=slug, name=name, database_url=database_url, entra_tenant_id=entra_tenant_id))
        db.session.commit()
        click.echo(f'Bolaget {slug} är tillagt.')

    @app.cli.command('konto-skapa')
    @click.argument('username')
    @click.option('--tenant', 'slug', required=True, help='Bolaget kontot hör till.')
    @click.option('--namn', 'display_name', required=True, help='Namnet som visas.')
    @click.option('--epost', 'email', default=None, help='Används för att koppla Microsoft-kontot.')
    @click.option('--admin', is_flag=True, help='Administratör (ger inga tillägg automatiskt).')
    @click.password_option('--losenord', 'password', help=f'Minst {12} tecken.')
    def create_account(username: str, slug: str, display_name: str, email: str | None, admin: bool,
                       password: str) -> None:
        """Lokalt konto med lösenord. Engångskoden registreras vid första inloggningen."""
        from core.auth import set_password
        tenant = _tenant(slug)
        with tenant_context(tenant):
            if db.session.scalars(select(User).where(User.username == username)).one_or_none() is not None:
                raise click.ClickException(f'användaren {username} finns redan i {tenant.slug}')
            user = User(username=username, display_name=display_name, email=email, is_admin=admin)
            try:
                set_password(user, password)
            except ValueError as error:
                raise click.ClickException(str(error)) from error
            db.session.add(user)
            db.session.commit()
        click.echo(f'Kontot {username} är skapat i {slug}.')

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
        click.echo(f'  Inloggningsförsök äldre än {retention.LOGIN_MONTHS} månader: {due["login_events"]}')

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

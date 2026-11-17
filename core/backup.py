"""
Kopior av databaserna (F0-20, och grunden för F0-12). Förlaga: pe-portal/core/backup.py.

`flask backup-dump <mapp>` tar pg_dump (custom-format) av masterdatabasen och varje aktivt bolags databas. Lösenordet
lämnas i miljön (PGPASSWORD), aldrig på kommandoraden, så att det inte syns i processlistan. Databaser som inte är
PostgreSQL (lokalt och i proven) hoppas över med besked.

Utläggningen kör kommandot före migrationerna (deploy/pdf-deploy-root.sh). Den nattliga backupen med uppladdning till
en egen lagringsbehållare i Azure byggs i F0-12.
"""

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import select

NAME_RE = re.compile(r'[^A-Za-z0-9._-]+')


def safe_name(name: str) -> str:
    return NAME_RE.sub('_', Path(name).name).strip('._') or 'kopia'


def pg_dump_command(label: str, url: str, dest: str) -> tuple[list[str], dict[str, str], Path]:
    """(kommando, miljö, fil) för pg_dump — lösenordet i PGPASSWORD, inte i kommandot."""
    parts = urlsplit(url.replace('postgresql+psycopg2://', 'postgresql://'))
    netloc = parts.netloc
    if parts.password is not None:
        hostport = netloc.rsplit('@', 1)[1]
        netloc = f'{parts.username}@{hostport}' if parts.username else hostport
    clean = urlunsplit((parts.scheme, netloc, parts.path, parts.query, ''))
    path = Path(dest) / f'{safe_name(label)}.dump'
    cmd = ['pg_dump', '--format=custom', '--no-owner', '--no-privileges', '--file', str(path), clean]
    env = dict(os.environ)
    if parts.password:
        env['PGPASSWORD'] = parts.password
    return cmd, env, path


def targets() -> list[tuple[str, str]]:
    """(etikett, databas-URL) för master och varje aktivt bolag."""
    from core.db_routing import MASTER_BIND
    from core.models_master import Tenant
    from extensions import db
    rows = [('master', str(db.engines[MASTER_BIND].url.render_as_string(hide_password=False)))]
    rows += [(t.slug, t.database_url) for t in
             db.session.scalars(select(Tenant).where(Tenant.active.is_(True)).order_by(Tenant.slug))]
    return rows


def dump_databases(dest: str) -> Iterator[tuple[str, str]]:
    """Kör pg_dump för varje databas. Ger (etikett, besked). Kastar RuntimeError om en kopia misslyckas."""
    Path(dest).mkdir(parents=True, exist_ok=True)
    for label, url in targets():
        if not url.startswith('postgresql'):
            yield label, 'hoppas över (inte PostgreSQL)'
            continue
        cmd, env, path = pg_dump_command(label, url, dest)
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f'{label}: pg_dump misslyckades: {result.stderr.strip()[:300]}')
        yield label, f'{path.name} ({path.stat().st_size} byte)'

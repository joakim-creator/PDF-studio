"""
Versionerade SQL-migrationer per databas (F0-04). Förlaga: pe-portal/core/migrations.py, utan
baslinjeregistreringen (här byggs varje databas med migrationerna från början).

Varje databas — masterdatabasen och varje bolagsdatabas — har en tabell
`schema_migrations` som listar vilka migrationer som körts och med vilken
kontrollsumma. Migrationerna ligger som SQL-filer:

    migrations/master/<tidsstämpel>_<namn>.sql        (+ .down.sql)
    migrations/tenant/<tidsstämpel>_<namn>.sql        (+ .down.sql)

Regler som koden upprätthåller:
- En migration utan återställningsfil (.down.sql) godtas inte.
- En migration som ändrats efter att den körts stoppar allt (kontrollsumman skiljer).
- En körd migration vars fil saknas stoppar allt.
- Varje migration körs i en egen transaktion och registreras i samma transaktion.
- En databas som har tabeller men ingen migrationshistorik rörs inte.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, text

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / 'migrations'
KINDS = ('master', 'tenant')
TABLE = 'schema_migrations'

_FILENAME = re.compile(r'^(\d{12})_([a-z0-9_]+)\.sql$')


class MigrationError(RuntimeError):
    """Något är fel med migrationerna eller databasens migrationsstatus. Inget har körts."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    down_path: Path

    @property
    def checksum(self):
        return file_checksum(self.path)

    @property
    def label(self):
        return f'{self.version}_{self.name}'


def file_checksum(path):
    """sha256 av filen med LF-radslut, så att en Windows-utcheckning ger samma summa."""
    data = Path(path).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def discover(kind, directory=None):
    """Alla migrationer av en sort, i körordning. Kastar MigrationError vid felaktiga filer."""
    if kind not in KINDS:
        raise ValueError(f'okänd migrationssort: {kind}')
    base = Path(directory) if directory else MIGRATIONS_DIR / kind
    migrations = []
    for path in sorted(base.glob('*.sql')):
        if path.name.endswith('.down.sql'):
            continue
        match = _FILENAME.match(path.name)
        if not match:
            raise MigrationError(
                f'{path.name}: filnamnet ska vara <12 siffror>_<namn med a-z, 0-9, _>.sql')
        down = path.with_name(path.name[:-4] + '.down.sql')
        if not down.exists():
            raise MigrationError(f'{path.name}: återställningsfil saknas ({down.name})')
        migrations.append(Migration(match.group(1), match.group(2), path, down))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise MigrationError(f'{kind}: två migrationer har samma tidsstämpel')
    return migrations


# ── Status ────────────────────────────────────────────────────────────────────

def _ensure_table(conn):
    conn.execute(text(f'''
        CREATE TABLE IF NOT EXISTS {TABLE} (
            version    VARCHAR(12)  PRIMARY KEY,
            name       VARCHAR(200) NOT NULL,
            checksum   VARCHAR(64)  NOT NULL,
            applied_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    '''))


def has_migration_table(engine):
    return inspect(engine).has_table(TABLE)


def applied(engine):
    """{version: checksum} för körda migrationer. Tom om tabellen saknas."""
    if not has_migration_table(engine):
        return {}
    with engine.connect() as conn:
        rows = conn.execute(text(f'SELECT version, checksum FROM {TABLE}')).all()
    return {version: checksum for version, checksum in rows}


def status(engine, kind, directory=None):
    """Lista av (etikett, tillstånd). Tillstånd: körd, väntar, ÄNDRAD, SAKNAS."""
    done = applied(engine)
    result = []
    files = discover(kind, directory)
    for m in files:
        if m.version not in done:
            result.append((m.label, 'väntar'))
        elif done[m.version] != m.checksum:
            result.append((m.label, 'ÄNDRAD'))
        else:
            result.append((m.label, 'körd'))
    known = {m.version for m in files}
    for version in sorted(set(done) - known):
        result.append((version, 'SAKNAS'))
    return result


def verify(engine, kind, directory=None):
    """Kasta MigrationError om någon körd migration ändrats eller saknas."""
    problems = [(label, state) for label, state in status(engine, kind, directory)
                if state in ('ÄNDRAD', 'SAKNAS')]
    if problems:
        lines = '\n'.join(f'  {label}: {state}' for label, state in problems)
        raise MigrationError(
            'Körda migrationer stämmer inte med filerna — inget körs:\n' + lines +
            '\nEn körd migration får aldrig ändras; rätta med en ny migration.')


# ── Körning ───────────────────────────────────────────────────────────────────

def _run_sql(conn, sql):
    # psycopg2 kör flera satser i ett anrop, inom transaktionen.
    conn.exec_driver_sql(sql)


def migrate(engine, kind, directory=None):
    """Kör väntande migrationer i ordning. Returnerar etiketterna för de som kördes."""
    if engine.dialect.name != 'postgresql':
        raise MigrationError('migrationerna är skrivna för PostgreSQL')
    files = discover(kind, directory)
    if files and not has_migration_table(engine) and has_any_tables(engine):
        raise MigrationError(
            'Databasen har tabeller men ingen migrationshistorik — inget körs. '
            'Den har inte byggts med migrationerna och måste undersökas för hand.')
    verify(engine, kind, directory)
    done = applied(engine)
    ran = []
    for m in files:
        if m.version in done:
            continue
        with engine.begin() as conn:
            _ensure_table(conn)
            _run_sql(conn, m.path.read_text(encoding='utf-8'))
            conn.execute(
                text(f'INSERT INTO {TABLE} (version, name, checksum) VALUES (:v, :n, :c)'),
                {'v': m.version, 'n': m.name, 'c': m.checksum})
        ran.append(m.label)
    return ran


def rollback(engine, kind, version, directory=None):
    """Återställ den senast körda migrationen. Bara den senaste får återställas."""
    verify(engine, kind, directory)
    done = applied(engine)
    if not done:
        raise MigrationError('inga körda migrationer att återställa')
    latest = max(done)
    if version != latest:
        raise MigrationError(f'bara den senaste migrationen ({latest}) kan återställas')
    m = next(m for m in discover(kind, directory) if m.version == version)
    with engine.begin() as conn:
        _run_sql(conn, m.down_path.read_text(encoding='utf-8'))
        conn.execute(text(f'DELETE FROM {TABLE} WHERE version = :v'), {'v': version})
    return m.label


# ── Schemat mot modellerna ────────────────────────────────────────────────────

def has_any_tables(engine):
    existing = set(inspect(engine).get_table_names())
    return bool(existing - {TABLE})


def schema_diff(engine, metadata):
    """
    Jämför databasens schema med modellerna. Returnerar dict med:
      missing_tables, missing_columns  — det koden förutsätter men databasen saknar
      extra_tables, extra_columns      — det databasen har men koden inte känner till
    """
    insp = inspect(engine)
    existing = set(insp.get_table_names()) - {TABLE}
    expected = {t.name: t for t in metadata.sorted_tables}
    diff = {'missing_tables': sorted(set(expected) - existing),
            'extra_tables': sorted(existing - set(expected)),
            'missing_columns': [], 'extra_columns': []}
    for name in sorted(set(expected) & existing):
        db_cols = {c['name'] for c in insp.get_columns(name)}
        model_cols = {c.name for c in expected[name].columns}
        diff['missing_columns'] += [f'{name}.{c}' for c in sorted(model_cols - db_cols)]
        diff['extra_columns'] += [f'{name}.{c}' for c in sorted(db_cols - model_cols)]
    return diff


def masked(url):
    """Databas-URL utan lösenord, för utskrift."""
    return re.sub(r'://([^:/@]+):[^@]*@', r'://\1:***@', str(url))

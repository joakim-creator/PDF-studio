"""
verify.py — hela verify-kedjan i ett kommando (F0-09): lint + typkontroll + prov.
Förlaga: pe-portal/scripts/verify.py.

    venv\\Scripts\\python scripts\\verify.py          (Windows)
    venv/bin/python scripts/verify.py               (Linux, CI)

Databasproven (från F0-04) kräver PostgreSQL. Sätt PG_TEST_URL, t.ex. mot en tillfällig Docker-container:

    docker run -d --name pdf-studio-pg-test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 127.0.0.1:5453:5432 postgres:16
    PG_TEST_URL=postgresql://postgres:test@127.0.0.1:5453/test

Utan PG_TEST_URL hoppas de proven över, och det sägs tydligt. I CI körs skriptet med --require-pg, och då faller
kedjan i stället — ett prov som tyst hoppas över bevisar inget.

--coverage kör proven med coverage och skriver ut täckningen per fil sist. Bara en rapport: den fäller inget.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    ('Lint (ruff)', ['-m', 'ruff', 'check', '.']),
    ('Typkontroll (mypy)', ['-m', 'mypy']),
    ('Prov (pytest)', ['-m', 'pytest']),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n')[1])
    parser.add_argument('--require-pg', action='store_true',
                        help='Fall om PostgreSQL-proven inte kan köras (används i CI).')
    parser.add_argument('--coverage', action='store_true',
                        help='Kör proven med coverage och skriv ut täckningen (rapport, fäller inget).')
    args = parser.parse_args()
    steps = list(STEPS)
    if args.coverage:
        steps[-1] = ('Prov (pytest, med täckning)', ['-m', 'coverage', 'run', '-m', 'pytest'])

    env = dict(os.environ)
    if args.require_pg:
        env['REQUIRE_PG'] = '1'
    if not env.get('PG_TEST_URL'):
        print('OBS: PG_TEST_URL saknas — databasproven hoppas över.'
              + (' (--require-pg: de kommer att falla)' if args.require_pg else ''))

    failed = []
    for label, cmd in steps:
        print(f'\n== {label}', flush=True)
        if subprocess.run([sys.executable, *cmd], cwd=ROOT, env=env).returncode != 0:
            failed.append(label)

    if args.coverage:
        print('\n== Täckning (rapport — fäller inget)', flush=True)
        subprocess.run([sys.executable, '-m', 'coverage', 'report', '--skip-covered', '--sort=cover'],
                       cwd=ROOT, env=env)

    print()
    if failed:
        print(f'RÖTT: {", ".join(failed)}')
        sys.exit(1)
    print('GRÖNT: lint, typkontroll och prov gick igenom.')


if __name__ == '__main__':
    main()

"""Utläggning och släpp (F0-20, F0-21): skripten, arbetsflödena och databaskommandona."""

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from sqlalchemy import create_engine

from app import create_app
from core import backup, migrations
from core.models_master import Tenant
from extensions import db

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / 'deploy'
SHA = 'a' * 40


def _bash() -> str:
    bash = shutil.which('bash')
    assert bash is not None, 'bash behövs för att pröva utläggningsskripten'
    return bash


# ── Skripten ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('script', sorted(p.name for p in DEPLOY.glob('*.sh')))
def test_skripten_har_giltig_syntax_och_lf(script: str) -> None:
    path = DEPLOY / script
    assert b'\r\n' not in path.read_bytes(), 'skript med Windows-radslut går inte att köra på servern'
    result = subprocess.run([_bash(), '-n', path.as_posix()], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _forced(command: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Kör det tvingade kommandot med en låtsas-sudo som bara skriver ut vad den ombads köra."""
    fake = tmp_path / 'sudo'
    fake.write_text('#!/usr/bin/env bash\necho "SUDO $*"\n', encoding='utf-8', newline='\n')
    fake.chmod(0o755)
    env = {**os.environ, 'SSH_ORIGINAL_COMMAND': command, 'PATH': f'{tmp_path.as_posix()}:{os.environ.get("PATH", "")}'}
    script = (DEPLOY / 'pdf-deploy.sh').read_text(encoding='utf-8').replace('exec sudo', f'exec {fake.as_posix()}')
    copy = tmp_path / 'pdf-deploy.sh'
    copy.write_text(script, encoding='utf-8', newline='\n')
    return subprocess.run([_bash(), copy.as_posix()], capture_output=True, text=True, env=env)


def test_tvingade_kommandot_slapper_bara_status_och_deploy_med_sha(tmp_path: Path) -> None:
    status = _forced('status', tmp_path)
    assert status.stdout.strip() == 'SUDO -n /usr/local/sbin/pdf-deploy-root status'
    deploy = _forced(f'deploy {SHA}', tmp_path)
    assert deploy.stdout.strip() == f'SUDO -n /usr/local/sbin/pdf-deploy-root deploy {SHA}'
    for refused in ('deploy', 'bash', f'deploy {SHA}; rm -rf /', f'deploy {SHA[:39]}', 'status --force', ''):
        result = _forced(refused, tmp_path)
        assert result.returncode == 2, refused
        assert 'SUDO' not in result.stdout


def test_sudo_regeln_tillater_exakt_status_och_deploy_med_fyrtio_tecken() -> None:
    install = (DEPLOY / 'install_deploy_access.sh').read_text(encoding='utf-8')
    rule = next(line for line in install.splitlines() if line.startswith('pdfdeploy ALL=(root) NOPASSWD:'))
    assert rule == ('pdfdeploy ALL=(root) NOPASSWD: /usr/local/sbin/pdf-deploy-root status, '
                    '/usr/local/sbin/pdf-deploy-root deploy ' + '?' * 40)


def _code(path: Path) -> str:
    """Filen utan kommentarsrader — kommentarerna får nämna PE Portals namn för att förklara varför de inte används."""
    return '\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                     if not line.lstrip().startswith('#'))


def test_delar_inte_anvandare_port_eller_namn_med_pe_portal() -> None:
    """Dev körs på pe-portal-dev bredvid PE Portal (B-010). PE Portal har användaren deploy (vars authorized_keys
    installationsskriptet skulle skriva över), port 8000, www-data, default_server i Nginx och namnen pe-*."""
    install = _code(DEPLOY / 'install_deploy_access.sh')
    assert 'DEPLOY_USER=pdfdeploy' in install
    assert re.findall(r'(?<![\w$/-])deploy:|/home/deploy\b|-u deploy\b|^deploy ALL', install, re.MULTILINE) == []
    for workflow in ('verify.yml', 'release.yml'):
        text = (ROOT / '.github' / 'workflows' / workflow).read_text(encoding='utf-8')
        assert ' deploy@' not in text and ' pdfdeploy@' in text, workflow
    service = _code(DEPLOY / 'pdf-studio.service')
    assert 'User=pdfstudio' in service and 'www-data' not in service
    assert 'default_server' not in _code(DEPLOY / 'nginx.conf')
    all_code = ' '.join(_code(p) for p in DEPLOY.iterdir())
    assert re.findall(r'\bpe-(?:deploy|backup)\b', all_code) == []


def test_databasen_fore_koden_och_kopia_fore_migrationerna() -> None:
    root = (DEPLOY / 'pdf-deploy-root.sh').read_text(encoding='utf-8')
    order = [root.index(step) for step in (
        'if [[ "$ACTION" == "deploy" && "$TARGET" != "$EXPECTED" ]]',   # provad commit först
        'git worktree add',
        'backup-dump',
        'db-migrate --yes',
        'git checkout -q -B "$BRANCH" "$TARGET"',
        'restart_service\nif health; then',
    )]
    assert order == sorted(order)
    assert 'git reset -q --keep "$PREV"' in root   # återgången


def test_appen_lyssnar_bara_lokalt_bakom_en_proxy() -> None:
    service = (DEPLOY / 'pdf-studio.service').read_text(encoding='utf-8')
    nginx = (DEPLOY / 'nginx.conf').read_text(encoding='utf-8')
    install = (DEPLOY / 'install_deploy_access.sh').read_text(encoding='utf-8')
    root = (DEPLOY / 'pdf-deploy-root.sh').read_text(encoding='utf-8')
    # Samma port överallt, och inte PE Portals 8000 (B-010).
    port = re.search(r'--bind 127\.0\.0\.1:(\d+) ', service)
    assert port is not None
    assert port.group(1) != '8000'
    assert f'proxy_pass http://127.0.0.1:{port.group(1)};' in nginx
    assert f'APP_PORT={port.group(1)} ' in install and f'APP_PORT=${{APP_PORT:-{port.group(1)}}}' in root
    assert '"http://127.0.0.1:$APP_PORT/health"' in root and '127.0.0.1:8000' not in root
    for header in ('X-Forwarded-For $proxy_add_x_forwarded_for', 'X-Forwarded-Proto $scheme',
                   'X-Request-ID $request_id'):
        assert f'proxy_set_header {header};' in nginx
    limit_mb = int(nginx.split('client_max_body_size ')[1].split('M;')[0])
    assert limit_mb * 1024 * 1024 == create_app({'TESTING': True}).config['MAX_CONTENT_LENGTH']


# ── Arbetsflödena ────────────────────────────────────────────────────────────

def test_dev_laggs_ut_bara_efter_grona_prov_och_med_provad_commit() -> None:
    verify = (ROOT / '.github' / 'workflows' / 'verify.yml').read_text(encoding='utf-8')
    job = verify.split('  deploy-dev:')[1]
    assert '    needs: verify' in job
    assert "github.ref == 'refs/heads/dev'" in job and "vars.DEV_HOST != ''" in job
    assert '"deploy ${{ github.sha }}"' in job
    assert 'python scripts/verify.py --require-pg' in verify.split('  deploy-dev:')[0]


def test_slapp_bara_fran_main_med_slapp_och_efter_prov() -> None:
    release = (ROOT / '.github' / 'workflows' / 'release.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in release and 'push:' not in release
    assert '"$GITHUB_REF" != "refs/heads/main"' in release
    assert '"$BEKRAFTA" != "SLAPP"' in release
    assert release.index('scripts/verify.py --require-pg') < release.index('"deploy ${{ github.sha }}"')


# ── Kommandona ───────────────────────────────────────────────────────────────

def test_kopian_lamnar_losenordet_i_miljon(tmp_path: Path) -> None:
    cmd, env, path = backup.pg_dump_command('bolag', 'postgresql://pdf:hemligt-losen@db.prov.invalid:5432/bolag',
                                            str(tmp_path))
    assert 'hemligt-losen' not in ' '.join(cmd)
    assert cmd[-1] == 'postgresql://pdf@db.prov.invalid:5432/bolag'
    assert env['PGPASSWORD'] == 'hemligt-losen'
    assert path == tmp_path / 'bolag.dump'


def test_backup_dump_hoppar_over_sqlite(app: Flask, tenant: Any, tmp_path: Path) -> None:
    result = app.test_cli_runner().invoke(args=['backup-dump', str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert 'master: hoppas över (inte PostgreSQL)' in result.output
    assert f'{tenant.slug}: hoppas över (inte PostgreSQL)' in result.output


def test_db_kommandona_mot_postgresql(pg_database: Callable[[], str], tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    master_url, tenant_url = pg_database(), pg_database()
    pg_app = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False, 'MASTER_DATABASE_URL': master_url})
    runner = pg_app.test_cli_runner()
    first = runner.invoke(args=['db-migrate', '--yes'])
    assert first.exit_code == 0, first.output
    assert 'master: körd 202611162200_baslinje' in first.output
    with pg_app.app_context():
        db.session.add(Tenant(slug='pgbolag', name='PG-bolaget', database_url=tenant_url))
        db.session.commit()
    pending = runner.invoke(args=['db-status'])
    assert 'väntar  202611162200_baslinje' in pending.output
    assert pg_app.test_client().get('/health').status_code == 503
    second = runner.invoke(args=['db-migrate', '--yes'])
    assert second.exit_code == 0, second.output
    assert [line.strip() for line in second.output.splitlines() if 'körd' in line] == [
        f'pgbolag: körd {m.label}' for m in migrations.discover('tenant')]
    status = runner.invoke(args=['db-status'])
    assert 'väntar' not in status.output and 'SAKNAD' not in status.output
    assert pg_app.test_client().get('/health').status_code == 200

    calls: list[list[str]] = []

    def fake_pg_dump(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        Path(cmd[5]).write_bytes(b'x')
        return subprocess.CompletedProcess(cmd, 0, '', '')
    monkeypatch.setattr(backup.subprocess, 'run', fake_pg_dump)
    dump = runner.invoke(args=['backup-dump', str(tmp_path)])
    assert dump.exit_code == 0, dump.output
    assert [c[5].rsplit('/', 1)[-1].rsplit('\\', 1)[-1] for c in calls] == ['master.dump', 'pgbolag.dump']
    assert all('test' not in c[-1].split('@')[0].split(':')[-1] for c in calls)   # lösenordet inte i adressen
    with pg_app.app_context():
        db.session.remove()
    create_engine(master_url).dispose()

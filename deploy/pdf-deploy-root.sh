#!/usr/bin/env bash
# pdf-deploy-root — driftsätter på den här servern (F0-20; förlaga pe-portal/deploy).
#
# Installeras till /usr/local/sbin av install_deploy_access.sh och körs via sudo av
# användaren deploy, vars SSH-nyckel (i GitHub Actions) bara får köra /usr/local/bin/pdf-deploy.
#
#   pdf-deploy-root status          visar migrationsstatus för det som skulle läggas ut — ändrar inget
#   pdf-deploy-root deploy <sha>    dev: lägger ut grenen dev.  prod: släpper main.
#
# Släppet är bundet till den provade commiten (backend-grund 12): CI skickar sitt commit-id, och skriptet vägrar om
# grenen på GitHub pekar någon annanstans — någon kan ha pushat efter att proven kördes.
#
# Ordningen följer "databasen före koden": migrationerna körs från den nya koden i en
# tillfällig mapp medan den gamla koden fortfarande kör, därefter byts koden och tjänsten
# startas om. Klarar den nya koden inte hälsokontrollen läggs den gamla tillbaka.
#
# Inställningar i /etc/pdf-studio/deploy.conf (skrivs av installationsskriptet):
#   PDF_DEPLOY_ENV  dev | prod
#   APP_DIR         /var/www/pdf-studio
#   SERVICE         systemd-tjänsten: pdf-studio-dev eller pdf-studio
#   BRANCH          dev | main
#   HEALTH_HOST     domänen, för hälsokontrollen
#   ENV_FILE        miljöfilen (/etc/pdf-studio/<miljö>.env); tom = läs miljön från den körande tjänsten

set -euo pipefail

CONF=/etc/pdf-studio/deploy.conf
[[ -f $CONF ]] || { echo "FEL: $CONF saknas — kör install_deploy_access.sh" >&2; exit 1; }
# shellcheck source=/dev/null
source "$CONF"

ACTION=${1:-}
EXPECTED=${2:-}
case "$ACTION" in
    status) ;;
    deploy)
        [[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]] \
            || { echo "FEL: deploy kräver den provade commitens id (40 hexadecimala tecken)" >&2; exit 2; } ;;
    *) echo "FEL: tillåtna åtgärder är status och deploy <sha>" >&2; exit 2 ;;
esac

exec 9>/var/lock/pdf-deploy.lock
flock -n 9 || { echo "FEL: en annan driftsättning pågår redan" >&2; exit 1; }

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

load_env() {
    if [[ -n "${ENV_FILE:-}" ]]; then
        set -a
        # shellcheck source=/dev/null
        source "$ENV_FILE"
        set +a
        return
    fi
    local pid
    pid=$(systemctl show -p MainPID --value "$SERVICE")
    if [[ -z "$pid" || "$pid" == "0" ]]; then
        echo "FEL: $SERVICE kör inte — miljön kan inte läsas. Starta tjänsten först." >&2
        exit 1
    fi
    while IFS= read -r line; do
        export "$line"
    done < <(tr '\0' '\n' < "/proc/$pid/environ" | grep -E \
        '^(SECRET_KEY|MASTER_DATABASE_URL|TENANT_POOL_SIZE|MASTER_POOL_SIZE|TOTP_KEY|PDF_ENV)=')
}

health() {
    # /health (F0-11) svarar 200 bara när masterdatabasen och alla bolagsdatabaser nås och inga migrationer väntar.
    local code=000
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 3
        code=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $HEALTH_HOST" \
               http://127.0.0.1:8000/health || true)
        [[ "$code" == "200" ]] && return 0
    done
    echo "FEL: hälsokontrollen fick inte 200 från /health (senaste svar: $code)" >&2
    return 1
}

cd "$APP_DIR"
git fetch -q --prune origin
TARGET=$(git rev-parse "origin/$BRANCH")
PREV=$(git rev-parse HEAD)
log "Miljö:      $PDF_DEPLOY_ENV ($APP_DIR, tjänst $SERVICE)"
log "Kör nu:     $(git log --oneline -1 "$PREV")"
log "Läggs ut:   $(git log --oneline -1 "$TARGET")"

if [[ "$ACTION" == "deploy" && "$TARGET" != "$EXPECTED" ]]; then
    echo "FEL: origin/$BRANCH är $TARGET men proven kördes på $EXPECTED — något har pushats efter proven." >&2
    echo "     Inget är ändrat. Kör om arbetsflödet på den senaste commiten." >&2
    exit 1
fi

if [[ "$PDF_DEPLOY_ENV" == "prod" ]]; then
    [[ "$(git rev-parse --abbrev-ref HEAD)" == "$BRANCH" ]] \
        || { echo "FEL: produktionen står inte på $BRANCH" >&2; exit 1; }
    git merge-base --is-ancestor "$PREV" "$TARGET" \
        || { echo "FEL: $BRANCH på GitHub bygger inte vidare på det som kör — avbryter" >&2; exit 1; }
fi

WT=$(mktemp -d /tmp/pdf-release.XXXXXX)
rmdir "$WT"
git worktree add -q --detach "$WT" "$TARGET"

# Paketen (lärdom från PE Portals granskning 2026-11-17, G3-DRIFT-01/03): före en installation sparas listan över det som är installerat, så
# att ett avbrott före kodbytet och återgången efter en misslyckad hälsokontroll lägger tillbaka både kod och paket.
STATE=/var/lib/pdf-studio
install -d -m 700 "$STATE"
FREEZE="$STATE/freeze-fore-slapp.txt"
PIP="$APP_DIR/venv/bin/pip"
FLASK="$APP_DIR/venv/bin/flask"
PKG_CHANGED=0
CODE_SWITCHED=0

restore_packages() {
    [[ "$PKG_CHANGED" == "1" && -s "$FREEZE" ]] || return 0
    log "Lägger tillbaka föregående versions paket"
    "$PIP" install -q -r "$FREEZE" \
        || log "VARNING: paketen kunde inte läggas tillbaka — listan finns i $FREEZE"
    PKG_CHANGED=0
}

cleanup() {
    local code=$?
    trap - EXIT
    if [[ $code -ne 0 && "$CODE_SWITCHED" == "0" ]]; then
        restore_packages   # avbrott före kodbytet (t.ex. en migration som faller): gammal kod ska ha sina paket
    fi
    git -C "$APP_DIR" worktree remove --force "$WT" 2>/dev/null || true
    exit "$code"
}
trap cleanup EXIT

deps_current() {
    # Har servern redan exakt de versioner den nya kodens requirements.txt låser? Läser bara.
    "$APP_DIR/venv/bin/python" - "$WT/requirements.txt" <<'PY'
import re
import sys
from importlib import metadata

ok = True
for line in open(sys.argv[1], encoding='utf-8'):
    requirement, _, marker = line.split('#')[0].strip().partition(';')
    if 'win32' in marker and '!=' not in marker:
        continue
    match = re.match(r'^([A-Za-z0-9_.-]+)==(\S+)$', requirement.strip())
    if not match:
        continue
    try:
        ok = ok and metadata.version(match.group(1)) == match.group(2)
    except metadata.PackageNotFoundError:
        ok = False
sys.exit(0 if ok else 1)
PY
}

restart_service() {
    # En omstart som direkt ger fel får inte avsluta skriptet (set -e) före återgången — hälsokontrollen avgör
    # (lärdom från PE Portals granskning 2026-11-17, C-DRIFT-03).
    STARTED=$(date '+%Y-%m-%d %H:%M:%S')
    systemctl restart "$SERVICE" || log "VARNING: omstarten av $SERVICE gav fel — hälsokontrollen avgör"
}

load_env
export PYTHONWARNINGS=ignore   # biblioteksvarningar skymmer annars loggen

if deps_current; then
    log "Beroenden: servern har redan den nya kodens versioner"
elif [[ "$ACTION" == "status" ]]; then
    # Den nya koden kan kräva paket som inte finns än (G3-DRIFT-01: första steget föll med ModuleNotFoundError). Status
    # ska inte ändra något på servern, så den körs i en tillfällig miljö som tas bort med arbetsmappen.
    log "Beroenden: den nya koden kräver andra paket — status körs i en tillfällig miljö, inget på servern ändras"
    "$APP_DIR/venv/bin/python" -m venv "$WT/.venv"
    "$WT/.venv/bin/pip" install -q -r "$WT/requirements.txt"
    FLASK="$WT/.venv/bin/flask"
else
    log "1/5 Beroenden (listan över nuvarande paket sparas i $FREEZE)"
    "$PIP" freeze > "$FREEZE"
    PKG_CHANGED=1
    "$PIP" install -q -r "$WT/requirements.txt" gunicorn
fi

log "Databasstatus med den nya koden:"
STATUS=$(cd "$WT" && "$FLASK" --app app db-status)
echo "$STATUS"

if [[ "$ACTION" == "status" ]]; then
    log "Endast status — inget ändrat."
    exit 0
fi

if [[ "$PREV" == "$TARGET" ]]; then
    log "Redan senaste versionen — startar ändå om och kontrollerar."
fi

# Kopia före migrationerna (lärdom från PE Portals granskning 2026-11-17, G3-DRIFT-02): återgången backar koden, aldrig databasen. Väntar
# migrationer tas därför pg_dump av master och varje bolag med den nya kodens kommando, innan något ändras. Misslyckas
# kopian avbryts släppet med databasen orörd. SKIP_PRE_MIGRATION_DUMP=1 i deploy.conf hoppar över steget (uttryckligt
# val, t.ex. när en fork av databasen just tagits hos leverantören).
if grep -q 'väntar' <<<"$STATUS"; then
    if [[ "${SKIP_PRE_MIGRATION_DUMP:-0}" == "1" ]]; then
        log "2/5 Kopia före migrationerna: överhoppad (SKIP_PRE_MIGRATION_DUMP=1 i deploy.conf)"
    else
        DUMP="${BACKUP_DIR:-/var/backups/pdf-studio}/fore-slapp-$(date +%F-%H%M%S)"
        log "2/5 Kopia av databaserna före migrationerna → $DUMP"
        install -d -m 700 "$DUMP"
        if ! (cd "$WT" && "$FLASK" --app app backup-dump "$DUMP"); then
            echo "FEL: kopian före migrationerna misslyckades — databasen är orörd och släppet avbryts." >&2
            echo "     Kontrollera att pg_dump finns och är minst lika ny som databasservern (driftsattning.md steg 3)." >&2
            exit 1
        fi
    fi
else
    log "2/5 Inga migrationer väntar — ingen kopia behövs"
fi

log "3/5 Databasen (före koden)"
(cd "$WT" && "$FLASK" --app app db-migrate --yes)

log "4/5 Koden"
if [[ "$PDF_DEPLOY_ENV" == "prod" ]]; then
    git merge -q --ff-only "$TARGET"          # behåller lokala ändringar i orörda filer
else
    git checkout -q -B "$BRANCH" "$TARGET"    # dev har inga lokala ändringar
fi
CODE_SWITCHED=1

log "5/5 Omstart och hälsokontroll"
restart_service
if health; then
    log "KLART: $(git log --oneline -1 HEAD) kör i $PDF_DEPLOY_ENV."
    exit 0
fi

log "Lägger tillbaka föregående version $(git log --oneline -1 "$PREV")"
git reset -q --keep "$PREV"
restore_packages
restart_service
if health; then
    log "ÅTERSTÄLLD: föregående version kör igen med sina paket. Databasändringarna ligger kvar"
    log "            (kopian före migrationerna: ${DUMP:-ingen togs})."
else
    log "VARNING: även föregående version svarar dåligt — kontrollera: journalctl -u $SERVICE -n 50"
fi
exit 1

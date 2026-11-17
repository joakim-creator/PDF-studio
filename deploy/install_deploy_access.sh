#!/usr/bin/env bash
# install_deploy_access.sh — ger GitHub Actions en smal väg att driftsätta (F0-20; förlaga pe-portal/deploy).
#
# Körs som root på servern, från repots mapp:
#
#     bash deploy/install_deploy_access.sh dev <domän>                 (dev, på pe-portal-dev bredvid PE Portal)
#     bash deploy/install_deploy_access.sh prod <domän>                (produktionen)
#     bash deploy/install_deploy_access.sh prod <domän> --rotate-key   (byt nyckel)
#
# Gör:
#   1. Skapar användaren pdfdeploy (inget lösenord). Inte "deploy": den användaren är PE Portals på samma
#      server, och dess authorized_keys skulle skrivas över (B-010).
#   2. Installerar pdf-deploy (tvingat kommando) och pdf-deploy-root (själva driftsättningen).
#   3. sudo-regel: pdfdeploy får köra exakt "pdf-deploy-root status" och "pdf-deploy-root deploy <40 tecken>".
#   4. Skriver /etc/pdf-studio/deploy.conf för miljön, med appens port (8010; PE Portal har 8000).
#   5. Första gången (eller med --rotate-key): skapar ett nyckelpar. Den publika delen
#      läggs i deploy-användarens authorized_keys, låst till pdf-deploy. Den privata delen
#      skrivs ut EN gång för att klistras in i GitHub — och raderas sedan från servern.
#
# Kan köras om för att uppdatera skripten; nyckeln behålls då.

set -euo pipefail

ENVIRONMENT=${1:-}
HEALTH_HOST=${2:-}
ROTATE=${3:-}
DEPLOY_USER=pdfdeploy
APP_PORT=8010   # samma port som i pdf-studio.service och nginx.conf (vaktprov i tests/test_driftsattning.py)
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if [[ $EUID -ne 0 ]]; then echo "FEL: kör som root." >&2; exit 1; fi

case "$ENVIRONMENT" in
    dev)  APP_DIR=/var/www/pdf-studio; SERVICE=pdf-studio-dev; BRANCH=dev;  ENV_FILE=/etc/pdf-studio/dev.env ;;
    prod) APP_DIR=/var/www/pdf-studio; SERVICE=pdf-studio;     BRANCH=main; ENV_FILE=/etc/pdf-studio/prod.env ;;
    *)
        echo "Användning: bash deploy/install_deploy_access.sh dev|prod <domän> [--rotate-key]" >&2; exit 2 ;;
esac
[[ -n "$HEALTH_HOST" ]] || { echo "FEL: ange domänen, t.ex. dev.pdf.exempel.se" >&2; exit 2; }

[[ -d $APP_DIR/.git ]] || { echo "FEL: hittar inget repo i $APP_DIR" >&2; exit 1; }
[[ -x $APP_DIR/venv/bin/flask ]] || { echo "FEL: hittar inte $APP_DIR/venv/bin/flask" >&2; exit 1; }

echo "== 1/5 Användaren $DEPLOY_USER"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    useradd --system --create-home --shell /bin/bash "$DEPLOY_USER"
fi
passwd -l "$DEPLOY_USER" >/dev/null

echo "== 2/5 Skript"
install -o root -g root -m 755 "$REPO_DIR/deploy/pdf-deploy.sh" /usr/local/bin/pdf-deploy
install -o root -g root -m 700 "$REPO_DIR/deploy/pdf-deploy-root.sh" /usr/local/sbin/pdf-deploy-root
# Den nattliga säkerhetskopieringen installeras här när den finns (F0-12).

echo "== 3/5 sudo-regel"
SUDOERS=/etc/sudoers.d/pdf-deploy
cat > "$SUDOERS.tmp" <<RULE
# Skriven av install_deploy_access.sh (F0-20; förlaga pe-portal/deploy). pdfdeploy får bara köra driftsättningen.
pdfdeploy ALL=(root) NOPASSWD: /usr/local/sbin/pdf-deploy-root status, /usr/local/sbin/pdf-deploy-root deploy ????????????????????????????????????????
RULE
chmod 440 "$SUDOERS.tmp"
visudo -cf "$SUDOERS.tmp" >/dev/null
mv "$SUDOERS.tmp" "$SUDOERS"

echo "== 4/5 Inställningar för $ENVIRONMENT"
install -d -m 700 /etc/pdf-studio
cat > /etc/pdf-studio/deploy.conf <<CONF
# Skriven av install_deploy_access.sh (F0-20; förlaga pe-portal/deploy). Läses av pdf-deploy-root.
PDF_DEPLOY_ENV=$ENVIRONMENT
APP_DIR=$APP_DIR
SERVICE=$SERVICE
BRANCH=$BRANCH
HEALTH_HOST=$HEALTH_HOST
APP_PORT=$APP_PORT
ENV_FILE=$ENV_FILE
CONF
chmod 600 /etc/pdf-studio/deploy.conf

echo "== 5/5 Nyckel för GitHub Actions"
AUTH=/home/$DEPLOY_USER/.ssh/authorized_keys
install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" -m 700 "/home/$DEPLOY_USER/.ssh"
if [[ -s $AUTH && "$ROTATE" != "--rotate-key" ]]; then
    echo "   nyckel finns redan — behålls (byt med --rotate-key)"
else
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    ssh-keygen -q -t ed25519 -N "" -C "github-actions-$ENVIRONMENT" -f "$TMP/key"
    echo "restrict,command=\"/usr/local/bin/pdf-deploy\" $(cat "$TMP/key.pub")" > "$AUTH"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH"
    chmod 600 "$AUTH"
    UPPER=$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')
    echo
    echo "=============================================================================="
    echo " Lägg in i GitHub: PDF-studio → Settings → Secrets and variables → Actions"
    echo
    echo " Fliken Secrets → New repository secret"
    echo "   Name:   ${UPPER}_DEPLOY_KEY"
    echo "   Secret: raden mellan strecken nedan — EN lång rad, kopiera hela"
    echo "------------------------------------------------------------------------------"
    base64 -w0 "$TMP/key"
    echo
    echo "------------------------------------------------------------------------------"
    echo " Fliken Variables → New repository variable"
    echo "   Name:   ${UPPER}_HOST_KEY"
    echo "   Value:  $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
    echo
    echo " Den privata nyckeln raderas från servern nu. Klistra INTE in den i chatten."
    echo "=============================================================================="
    shred -u "$TMP/key" 2>/dev/null || rm -f "$TMP/key"
fi

echo
echo "Klart. Prova utan att ändra något:  sudo -u $DEPLOY_USER sudo -n /usr/local/sbin/pdf-deploy-root status"

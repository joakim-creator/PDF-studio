#!/usr/bin/env bash
# ci_write_key.sh — skriver deploy-nyckeln från en GitHub-hemlighet till ~/.ssh (F0-20; förlaga pe-portal/deploy).
#
# Används av arbetsflödena verify (deploy-dev) och release. Läser miljövariablerna
# KEY (hemligheten), HOST och HOST_KEY. Godtar nyckeln både som en enda base64-rad
# (det installationsskriptet skriver ut) och som vanligt flerradigt block; Windows-
# radslut och mellanslag från kopiering tas bort. Nyckeln provas innan den används.
set -euo pipefail

: "${KEY:?hemligheten med deploy-nyckeln saknas}"
: "${HOST:?variabeln med serverns adress saknas}"
: "${HOST_KEY:?variabeln med serverns värdnyckel saknas}"

install -m 700 -d ~/.ssh
umask 077
if printf '%s' "$KEY" | grep -q 'BEGIN OPENSSH PRIVATE KEY'; then
    printf '%s\n' "$KEY" | tr -d '\r' > ~/.ssh/deploy
else
    printf '%s' "$KEY" | tr -d ' \r\n\t' | base64 -d > ~/.ssh/deploy 2>/dev/null || true
fi

if ! ssh-keygen -y -f ~/.ssh/deploy >/dev/null 2>&1; then
    echo "FEL: deploy-nyckeln i GitHub-hemligheten går inte att läsa."
    echo "Skapa en ny på servern med:  bash deploy/install_deploy_access.sh <dev|prod> --rotate-key"
    echo "och klistra in den nya raden (en enda rad) i hemligheten."
    exit 1
fi

printf '%s %s\n' "$HOST" "$(printf '%s' "$HOST_KEY" | tr -d '\r')" > ~/.ssh/known_hosts
echo "Deploy-nyckeln är inläst."

#!/usr/bin/env bash
# pdf-deploy — tvingat kommando för pdfdeploy-användarens SSH-nyckel (F0-20; förlaga pe-portal/deploy).
# Installeras till /usr/local/bin. Nyckeln kan inte ge ett skal; det enda som går att be om är "status" eller
# "deploy <sha>" (den provade commiten, 40 hexadecimala tecken), och då körs pdf-deploy-root via sudo.
set -euo pipefail
COMMAND=${SSH_ORIGINAL_COMMAND:-}
if [[ "$COMMAND" == "status" ]]; then
    exec sudo -n /usr/local/sbin/pdf-deploy-root status
elif [[ "$COMMAND" =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
    exec sudo -n /usr/local/sbin/pdf-deploy-root deploy "${BASH_REMATCH[1]}"
fi
echo "Tillåtna kommandon: status, deploy <sha>" >&2
exit 2

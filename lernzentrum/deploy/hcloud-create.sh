#!/usr/bin/env bash
# Optional: creates the server via the Hetzner Cloud API (needs HCLOUD_TOKEN – only if you want automatic creation).
#   HCLOUD_TOKEN=… LZ_DOMAIN=lernen.example.de REPO=https://github.com/<you>/<repo>.git ./deploy/hcloud-create.sh
set -euo pipefail
: "${HCLOUD_TOKEN:?HCLOUD_TOKEN fehlt}" "${LZ_DOMAIN:?}" "${REPO:?}"
NAME=${NAME:-lernzentrum}; TYPE=${TYPE:-cx22}; LOCATION=${LOCATION:-nbg1}
USERDATA=$(cat <<CLOUD
#cloud-config
runcmd:
  - [bash, -c, "curl -fsSL https://get.docker.com | sh"]
  - [bash, -c, "git clone $REPO /opt/lernzentrum && LZ_DOMAIN=$LZ_DOMAIN REPO=$REPO bash /opt/lernzentrum/lernzentrum/deploy/hetzner-setup.sh"]
CLOUD
)
curl -fsS -X POST https://api.hetzner.cloud/v1/servers -H "Authorization: Bearer $HCLOUD_TOKEN" -H "Content-Type: application/json" \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"name":sys.argv[1],"server_type":sys.argv[2],"location":sys.argv[3],"image":"ubuntu-24.04","user_data":sys.argv[4]}))' "$NAME" "$TYPE" "$LOCATION" "$USERDATA")" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print("Server:",d["server"]["public_net"]["ipv4"]["ip"],"– jetzt A-Record für die Domain setzen.")'

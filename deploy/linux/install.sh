#!/usr/bin/env sh
# Linux (a PC, server or VPS): install the agent in a virtualenv and run it as a systemd user
# service that starts at boot and restarts when it stops.
#   cd <the folder with agent.toml and .env>
#   sh <Ultron>/deploy/linux/install.sh       (ULTRON_SPEC=... to install another copy)
set -eu
DIR=$(pwd)
HERE=$(cd "$(dirname "$0")" && pwd)          # this script's folder in the Ultron checkout
ROOT=$(cd "$HERE/../.." && pwd)               # the Ultron checkout itself
[ -f agent.toml ] || { echo "run this in the folder that holds agent.toml"; exit 1; }
[ -f .env ] || echo "note: no .env here yet - put the secrets in $DIR/.env (see Ultron's README.md)"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install "${ULTRON_SPEC:-$ROOT[full]}"
.venv/bin/ultron check

mkdir -p "$HOME/.config/systemd/user"
sed "s#@DIR@#$DIR#g" "$HERE/ultron.service" > "$HOME/.config/systemd/user/ultron.service"
systemctl --user daemon-reload
systemctl --user enable --now ultron
# keep the user's services running when nobody is logged in (a VPS)
loginctl enable-linger "$(id -un)" 2>/dev/null || echo "note: run 'sudo loginctl enable-linger $(id -un)' to start at boot without a login"
echo "running. log: journalctl --user -u ultron -f   stop: systemctl --user stop ultron"

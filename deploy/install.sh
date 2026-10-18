#!/bin/bash
# Install or update diarystats as a system service. Run as root from the repo:
#   sudo deploy/install.sh "$(command -v uv)"
#
# The script does not change an existing config or env file, and it does not
# enable the timer. You can run it again after each git pull.
set -euo pipefail

UV="${1:?usage: sudo deploy/install.sh PATH_TO_UV}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
STATE=/var/lib/diarystats
ETC=/etc/diarystats
VENV=/opt/diarystats/venv
# Ubuntu 24.04 has Python 3.12. Do not use a Python that uv keeps below /home:
# ProtectHome=yes hides /home from the job.
PYTHON=/usr/bin/python3

if [[ $EUID -ne 0 ]]; then
    echo "install.sh: run as root" >&2
    exit 1
fi
if [[ ! -f $REPO/uv.lock ]]; then
    echo "install.sh: no uv.lock. Run 'uv lock' as your user and commit it." >&2
    exit 1
fi

# 1. The system user. Its home is the state directory.
if ! id diarystats >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$STATE" --shell /usr/sbin/nologin diarystats
fi

# 2. Directories.
# Others may pass through the state directory, but not list it: www-data
# must reach the rendered pages. The archive and the tokens stay closed.
install -d -o diarystats -g diarystats -m 0711 "$STATE"
install -d -o diarystats -g diarystats -m 0750 "$STATE/lifelog"
install -d -o diarystats -g diarystats -m 0700 "$STATE/garmin-tokens"
# www-data reads the rendered pages. The setgid bit gives new subdirectories
# the same group.
install -d -o diarystats -g www-data -m 2750 "$STATE/rendered"
install -d -o root -g diarystats -m 0750 "$ETC"

# 3. Config and secrets. Create them only if they do not exist.
if [[ ! -e $ETC/config.toml ]]; then
    sed -e "s|^archive_dir = .*|archive_dir = \"$STATE/lifelog\"|" \
        -e "s|^tokenstore = .*|tokenstore = \"$STATE/garmin-tokens\"|" \
        -e "s|^dir = .*|dir = \"$STATE/rendered\"|" \
        "$REPO/config.example.toml" > "$ETC/config.toml"
    chown root:diarystats "$ETC/config.toml"
    chmod 0640 "$ETC/config.toml"
    echo "install.sh: created $ETC/config.toml"
fi
if [[ ! -e $ETC/env ]]; then
    install -o root -g diarystats -m 0640 /dev/null "$ETC/env"
    echo "install.sh: created $ETC/env. Add DIARYSTATS_RESCUETIME_KEY=..."
fi

# 4. The virtual environment, outside /home. --no-editable copies the code,
# so the service does not read the git checkout.
install -d -m 0755 "$(dirname "$VENV")"
(
    cd "$REPO"
    UV_PROJECT_ENVIRONMENT="$VENV" UV_CACHE_DIR=/var/cache/diarystats-uv \
        "$UV" sync --locked --no-dev --no-editable --python "$PYTHON"
)

# 5. The publish script and the systemd units. Put local changes to the units
# into drop-ins (systemctl edit ...). This script overwrites the unit files.
install -D -o root -g root -m 0755 "$REPO/deploy/diarystats-publish" \
    /usr/local/lib/diarystats/diarystats-publish
install -o root -g root -m 0644 \
    "$REPO/deploy/diarystats.service" \
    "$REPO/deploy/diarystats-publish.service" \
    "$REPO/deploy/diarystats.timer" \
    /etc/systemd/system/
systemctl daemon-reload

echo "install.sh: done. The timer is not enabled. See the README for the next steps."

# diarystats

Fetches daily Garmin and RescueTime data and archives the raw JSON in
`~/lifelog` (a local git repo). It then renders a DokuWiki snippet for the
diary stats subpage. Design: `../HANDOVER-diary-stats.md`.

For now the rendered snippets go to files in
`~/.local/share/diarystats/rendered/`. The DokuWiki writer comes later.

## Commands

```sh
diarystats login-garmin                        # once, interactive
diarystats dry-run --date 2026-10-16 [--dump DIR]   # fetch + print, write nothing
diarystats run [--days 3]                      # daily: D-1..D-N
diarystats backfill --from 2026-07-01 --to 2026-10-16
diarystats render --date D | --from D --to D | --all  [--write]   # offline
```

## Server setup

There is no remote yet. One way that keeps the code off third-party hosts is a bare
repo on the server:

```sh
# server
git init --bare ~/git/diarystats.git
# local
git remote add server michael-grosse.net:git/diarystats.git
git push server main
# server
git clone ~/git/diarystats.git ~/diarystats
```

Then, on the server, as the user that runs the job:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: pipx install uv
cd ~/diarystats && uv sync --no-dev

mkdir -p ~/.config/diarystats && chmod 700 ~/.config/diarystats
cp config.example.toml ~/.config/diarystats/config.toml
install -m 600 /dev/null ~/.config/diarystats/env
"${EDITOR:-nano}" ~/.config/diarystats/env   # add DIARYSTATS_RESCUETIME_KEY=...

.venv/bin/diarystats login-garmin
.venv/bin/diarystats dry-run --date "$(date -d yesterday +%F)" --dump /tmp/diarystats-fixtures
```

Check the dry-run output and the dumped JSON before you continue. The Garmin field
names in `diarystats/metrics.py` are not verified yet.

Enable the timer:

```sh
sudo loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
ln -sf ~/diarystats/deploy/diarystats.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now diarystats.timer
systemctl --user list-timers diarystats.timer
journalctl --user -u diarystats -n 50
```

Update: `git pull && uv sync --no-dev`.

## Development

```sh
uv lock            # once, then commit uv.lock: it pins garminconnect exactly
uv run pytest      # or: python3 -m pytest
```

garminconnect gets new releases every few days. Update on purpose with
`uv lock --upgrade-package garminconnect`, then do a `dry-run` before the next timer run.

This repository is public. Secrets live only in `~/.config/diarystats/`, and real
data lives only in `~/lifelog`. The test fixtures are synthetic. Never commit real API
responses (see `tests/fixtures/README.md`).

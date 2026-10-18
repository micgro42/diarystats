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
diarystats import-rescuetime rt-interval-*.json   # see below
```

### RescueTime history

The free plan keeps about 3 months of history. `daily_summary_feed` covers only
about 14 days. Older days come from `/anapi/data` exports, one file per kind
(`productivity`, `overview`, `category`, `activity`), named
`rt-interval-<kind>-<date>.json`. RescueTime allows about one such request every
5 minutes. The import computes the same numbers as the feed. If both exist for a
day, the feed wins.

## Server setup

The job runs as its own system user `diarystats`, not as your user. It runs a
fast-changing unofficial library every day, so it must not have access to your
SSH keys or other files. A second unit saves the pages in DokuWiki as `www-data`.
No step needs sudo while the job runs.

```
diarystats.timer → diarystats.service          User=diarystats  fetch, archive, render to files
                   └ diarystats-publish.service User=www-data    changed files → bin/dwpage.php
```

| Path | Content |
|---|---|
| `/opt/diarystats/venv` | the installed code |
| `/etc/diarystats/config.toml`, `env` | config and secrets (root:diarystats 0640) |
| `/var/lib/diarystats/lifelog` | the raw archive, a local git repo |
| `/var/lib/diarystats/garmin-tokens` | Garmin tokens (0700) |
| `/var/lib/diarystats/rendered` | the rendered pages, readable by www-data |

### Install and update

```sh
git clone https://github.com/micgro42/diarystats.git ~/git/diarystats
curl -LsSf https://astral.sh/uv/install.sh | sh     # once, for your user
cd ~/git/diarystats && uv lock                      # once; commit uv.lock
sudo deploy/install.sh "$(command -v uv)"
which php                                           # dwpage.php needs php-cli
```

After a `git pull`, run `sudo deploy/install.sh "$(command -v uv)"` again. It does
not change an existing config or env file. It overwrites the unit files, so put
local changes into drop-ins (`sudo systemctl edit diarystats-publish`).

Put the RescueTime key into `/etc/diarystats/env`:

```sh
sudoedit /etc/diarystats/env     # DIARYSTATS_RESCUETIME_KEY=...
```

If the diary is in a farmer animal, tell the publish unit:

```sh
sudo systemctl edit diarystats-publish
# [Service]
# Environment=animal=<animal name>
# Environment=PAGES_DIR=<farm dir>/<animal>/data/pages
# ReadWritePaths=<farm dir>/<animal>/data
```

### Manual commands

Run them as the `diarystats` user:

```sh
alias ds='sudo -u diarystats /opt/diarystats/venv/bin/diarystats'
ds login-garmin                                   # once, interactive
ds dry-run --date "$(date -d yesterday +%F)"
ds backfill --from 2026-10-10 --to 2026-10-16
ds render --all --write                           # re-render from the archive
sudo systemctl start diarystats-publish           # save changed pages in the wiki
```

`login-garmin` can log warnings about HTTP 429. The library tries several login
methods in turn, and Cloudflare blocks some of them. Only a failure of all of them
is an error.

To read the archive as your user, add yourself to the group and mark the repo as
safe for git:

```sh
sudo usermod -aG diarystats "$USER"               # log in again after this
git config --global --add safe.directory /var/lib/diarystats/lifelog
git -C /var/lib/diarystats/lifelog log --oneline | head
```

### Enable the timer

```sh
sudo systemctl enable --now diarystats.timer
systemctl list-timers diarystats.timer
sudo journalctl -u diarystats -u diarystats-publish -n 50
sudo journalctl -u diarystats -u diarystats-publish | grep ALERT:
```

### Move from the per-user setup

If you used the first version as your own user, move the data and remove the rest:

```sh
sudo rsync -a ~/lifelog/ /var/lib/diarystats/lifelog/
sudo rsync -a ~/.config/diarystats/garmin-tokens/ /var/lib/diarystats/garmin-tokens/
sudo chown -R diarystats:diarystats /var/lib/diarystats/lifelog /var/lib/diarystats/garmin-tokens
sudo install -o root -g diarystats -m 0640 ~/.config/diarystats/env /etc/diarystats/env
ds render --all --write                           # also checks that all of it works
# when all is good:
rm -rf ~/lifelog ~/.config/diarystats ~/.local/share/diarystats ~/git/diarystats/.venv
```

The archive is the only copy of RescueTime days older than 3 months. Keep
`~/lifelog-import` until there is a backup.

## Development

```sh
uv lock            # once, then commit uv.lock: it pins garminconnect exactly
uv run pytest      # or: python3 -m pytest
```

garminconnect gets new releases every few days. Update on purpose with
`uv lock --upgrade-package garminconnect`, run `deploy/install.sh` again, then do a
`dry-run` before the next timer run.

This repository is public. Secrets live only in `/etc/diarystats/env` and
`/var/lib/diarystats/garmin-tokens`, and real data lives only in `/var/lib/diarystats`. The test fixtures are synthetic. Never commit real API
responses (see `tests/fixtures/README.md`).

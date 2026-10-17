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

On the server, as the user that runs the job:

```sh
git clone https://github.com/micgro42/diarystats.git ~/git/diarystats
curl -LsSf https://astral.sh/uv/install.sh | sh   # or: pipx install uv
cd ~/git/diarystats && uv sync --no-dev

mkdir -p ~/.config/diarystats && chmod 700 ~/.config/diarystats
cp config.example.toml ~/.config/diarystats/config.toml
install -m 600 /dev/null ~/.config/diarystats/env
"${EDITOR:-nano}" ~/.config/diarystats/env   # add DIARYSTATS_RESCUETIME_KEY=...

.venv/bin/diarystats login-garmin
.venv/bin/diarystats dry-run --date "$(date -d yesterday +%F)" --dump /tmp/diarystats-fixtures
```

Check the dry-run output and the dumped JSON before you continue. The Garmin field
names in `diarystats/metrics.py` match the library's typed models, but not yet live data.

`login-garmin` can log warnings about HTTP 429. The library tries several login
methods in turn, and Cloudflare blocks some of them. Only a failure of all of them
is an error.

Enable the timer:

```sh
sudo loginctl enable-linger "$USER"
mkdir -p ~/.config/systemd/user
ln -sf ~/git/diarystats/deploy/diarystats.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now diarystats.timer
systemctl --user list-timers diarystats.timer
journalctl --user -u diarystats -n 50
```

Update: `git pull && uv sync --no-dev`.

### Writing to DokuWiki

With `kind = "dwpage"` in `[sink]`, the job saves each stats page with DokuWiki's
own `bin/dwpage.php`, as the web server user. This needs no remote API and no
new HTTP endpoint. Each change is a normal minor edit by "diarystats" with the
summary "auto: daily stats". Unchanged pages are not saved again.

```sh
sudo install -o root -g root -m 755 deploy/diarystats-wiki-commit /usr/local/bin/
echo "$USER ALL=(www-data) NOPASSWD: /usr/local/bin/diarystats-wiki-commit" \
  | sudo tee /etc/sudoers.d/diarystats && sudo chmod 440 /etc/sudoers.d/diarystats
sudo visudo -c
which php      # dwpage.php needs the PHP command line program (php-cli)
```

The wrapper accepts only page IDs that end in `:stats`. Do not allow `dwpage.php`
itself through sudo: its `checkout` command can write to any file that www-data
can write to. Then set `kind = "dwpage"` and run `diarystats render --all --write`
to save all archived days.

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

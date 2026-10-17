"""Command line interface. Run `diarystats --help`."""

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config as config_mod
from .alert import Alerter
from .archive import Archive, DayData
from .config import Config
from .fetch.garmin import GarminSource, library_version, login_interactive
from .fetch.rescuetime import RescueTimeSource
from .importer import ImportError_, import_rescuetime
from .pipeline import Fetcher, check_missing, day_range, process, render_day, write_rendered
from .sink import FileSink

log = logging.getLogger("diarystats")


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _today(cfg: Config) -> date:
    return datetime.now(cfg.timezone).date()


def _fetcher(cfg: Config, alerter: Alerter, pause: float = 1.0) -> Fetcher:
    key = config_mod.rescuetime_key()
    if key is None:
        log.warning("%s is not set. Skip RescueTime.", config_mod.RESCUETIME_KEY_VAR)
    return Fetcher(
        garmin=GarminSource(cfg.garmin_tokenstore, pause=pause),
        rescuetime=RescueTimeSource(key) if key else None,
        alerter=alerter,
        garmin_info={"library_version": library_version()},
    )


def cmd_run(cfg: Config, args: argparse.Namespace) -> int:
    alerter = Alerter(cfg.alert_backends)
    today = _today(cfg)
    days = day_range(today - timedelta(days=args.days), today - timedelta(days=1))
    archive = Archive(cfg.archive_dir)
    ok = process(cfg, days, _fetcher(cfg, alerter), archive, FileSink(cfg.sink_dir), alerter)
    check_missing(archive, alerter, today)
    return 0 if ok else 1


def cmd_backfill(cfg: Config, args: argparse.Namespace) -> int:
    alerter = Alerter(cfg.alert_backends)
    days = day_range(args.start, args.end)
    log.info("backfill %d days, %s..%s", len(days), args.start, args.end)
    archive = Archive(cfg.archive_dir)
    ok = process(
        cfg,
        days,
        _fetcher(cfg, alerter),
        archive,
        FileSink(cfg.sink_dir),
        alerter,
        throttle=cfg.throttle_seconds,
    )
    return 0 if ok else 1


def cmd_render(cfg: Config, args: argparse.Namespace) -> int:
    archive = Archive(cfg.archive_dir)
    if args.all:
        days = list(archive.days())
    elif args.date:
        days = [args.date]
    else:
        days = day_range(args.start, args.end)

    sink = FileSink(cfg.sink_dir)
    for day in days:
        if args.write:
            write_rendered(cfg, archive, sink, day)
        else:
            print(f"--- {cfg.page_id(day)}")
            print(render_day(cfg, archive, day, archive.load(day)))
    return 0


def cmd_dry_run(cfg: Config, args: argparse.Namespace) -> int:
    alerter = Alerter(cfg.alert_backends)
    fetcher = _fetcher(cfg, alerter)
    results = fetcher.fetch_day(args.date)
    if args.dump:
        for source, result in results.items():
            for name, obj in (result.files or {}).items():
                path = args.dump / f"{source}_{name}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
                log.info("dump: %s", path)
    data = DayData.from_results(results)
    print(f"--- {cfg.page_id(args.date)}")
    print(render_day(cfg, Archive(cfg.archive_dir), args.date, data))
    return 1 if fetcher.failed else 0


def cmd_import_rescuetime(cfg: Config, args: argparse.Namespace) -> int:
    archive = Archive(cfg.archive_dir)
    try:
        days = import_rescuetime(archive, args.files)
    except ImportError_ as e:
        log.error("%s", e)
        return 1
    if not days:
        log.warning("import: no rows")
        return 0
    sink = FileSink(cfg.sink_dir)
    for day in days:
        write_rendered(cfg, archive, sink, day)
    archive.commit(f"lifelog: import rescuetime {days[0]}..{days[-1]}")
    log.info("import: %d days, %s..%s", len(days), days[0], days[-1])
    return 0


def cmd_login_garmin(cfg: Config, args: argparse.Namespace) -> int:
    email = args.email or input("Garmin email: ").strip()
    login_interactive(cfg.garmin_tokenstore, email)
    print(f"Tokens stored in {cfg.garmin_tokenstore}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="diarystats", description=__doc__)
    parser.add_argument("--config", type=Path, help="config file (default: %(default)s)")
    parser.add_argument("--env-file", type=Path, default=config_mod.DEFAULT_ENV_FILE)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="daily run: fetch, archive and render the last N days")
    p.add_argument("--days", type=int, default=3)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("backfill", help="fetch, archive and render a date range")
    p.add_argument("--from", dest="start", type=_date, required=True)
    p.add_argument("--to", dest="end", type=_date, required=True)
    p.set_defaults(func=cmd_backfill)

    p = sub.add_parser("render", help="render from the archive only, no network")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", type=_date)
    group.add_argument("--from", dest="start", type=_date)
    group.add_argument("--all", action="store_true")
    p.add_argument("--to", dest="end", type=_date)
    p.add_argument("--write", action="store_true", help="write to the sink, do not print")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("dry-run", help="fetch and render one day, write nothing")
    p.add_argument("--date", type=_date, required=True)
    p.add_argument("--dump", type=Path, help="also save the raw responses in this directory")
    p.set_defaults(func=cmd_dry_run)

    p = sub.add_parser(
        "import-rescuetime", help="import /anapi/data exports (rt-interval-<kind>-*.json)"
    )
    p.add_argument("files", type=Path, nargs="+")
    p.set_defaults(func=cmd_import_rescuetime)

    p = sub.add_parser("login-garmin", help="interactive one-time Garmin login")
    p.add_argument("--email")
    p.set_defaults(func=cmd_login_garmin)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.command == "render" and args.start and not args.end:
        log.error("render --from needs --to")
        return 2
    try:
        cfg = config_mod.load(args.config)
    except config_mod.ConfigError as e:
        log.error("%s", e)
        return 2
    config_mod.load_env_file(args.env_file)
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())

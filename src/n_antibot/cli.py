"""Command line: n-antibot generate | check | install | report | serve | test-agent | test-ip | presets | init."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, api, claims, installer, report
from .config import FORMATS, Config, ConfigError, load
from .core import blocklist
from .presets import NETWORK_PRESETS, ROBOT_PRESETS
from .ranges import FetchError
from .render import render, strip_header

EXAMPLE = (Path(__file__).parent / "example.toml").read_text(encoding="utf-8")


def _config(a: argparse.Namespace) -> Config:
    cfg = load(a.config)
    if getattr(a, "format", None):
        cfg = replace(cfg, format=a.format).validate()
    return cfg


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def cmd_generate(a: argparse.Namespace) -> int:
    cfg = _config(a)
    bl = blocklist(cfg)
    text = render(bl, cfg)
    if a.output in (None, "-"):
        sys.stdout.write(text)
    else:
        _write_atomic(Path(a.output), text)
    print(
        f"n-antibot: {len(bl.v4)} IPv4 + {len(bl.v6)} IPv6 ranges, {len(bl.agents)} robots -> {a.output or 'stdout'}",
        file=sys.stderr,
    )
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    cfg = _config(a)
    path = Path(a.output)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    fresh = render(blocklist(cfg), cfg)
    if strip_header(current) == strip_header(fresh):
        print(f"{path}: up to date")
        return 0
    print(f"{path}: out of date, run: n-antibot generate -o {path}")
    return 1


def cmd_test_agent(a: argparse.Namespace) -> int:
    cfg = _config(a)
    hit = cfg.blocks_agent(a.user_agent)
    print(f"BLOCKED by {hit!r}" if hit else "allowed")
    return 0 if hit else 2


def cmd_test_ip(a: argparse.Namespace) -> int:
    cfg = _config(a)
    ip = ipaddress.ip_address(a.ip)
    bl = blocklist(cfg)
    hit = next((r for r in bl.v4 + bl.v6 if ip in ipaddress.ip_network(r)), None)
    print(f"BLOCKED by {hit}" if hit else "allowed")
    return 0 if hit else 2


def _day(text: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ValueError(f"{text!r} is not a date like 2026-11-12") from None


def cmd_report(a: argparse.Namespace) -> int:
    cfg = _config(a)
    classifier = report.Classifier.from_config(cfg)
    rep = report.analyze(
        report.read_logs(a.logs),
        classifier,
        since=_day(a.since) if a.since else None,
        until=_day(a.until) + timedelta(days=1) if a.until else None,
        min_repeat=a.min_repeat,
    )
    if a.json:
        print(json.dumps(report.as_dict(rep), indent=2))
    else:
        sys.stdout.write(report.render_text(rep))
    if a.csv:
        path = Path(a.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            rows = report.write_csv(rep, f, include_clean=a.all_clicks)
        print(f"n-antibot: {rows} ad clicks written to {path}", file=sys.stderr)
    if a.claim_dir:
        packs = claims.write_packs(rep, a.claim_dir)
        for p in packs:
            how = "" if p["has_process"] else " (the platform documents no process for invalid clicks)"
            print(
                f"n-antibot: {p['name']}: {p['clicks']} clicks ({p['within_deadline']} within the deadline) "
                f"-> {Path(a.claim_dir) / p['files'][0]}{how}",
                file=sys.stderr,
            )
        if not packs:
            print("n-antibot: no bot or suspicious ad clicks: no claim files written", file=sys.stderr)
    return 0


def cmd_install(a: argparse.Namespace) -> int:
    say = lambda text: print(f"n-antibot: {text}", flush=True)  # noqa: E731
    server = a.server
    if server != "nftables" and not a.site:
        raise ValueError("--site is required (the address of the site as written in your server's configuration)")
    config_file = Path(a.config_file) if a.config_file else None
    if server is None:
        found = installer.detect(a.site)
        if not found:
            raise ValueError(
                f"no Caddy, nginx or Apache configuration declaring {a.site} was found in the usual places. "
                "Say which server and file: n-antibot install nginx --site SITE --config-file FILE"
            )
        if len(found) > 1:
            names = ", ".join(f"{s} ({c})" for s, c in found)
            raise ValueError(
                f"{a.site} is declared in more than one server: {names}. Say which: n-antibot install SERVER ..."
            )
        server, config_file = found[0]
        say(f"found {a.site} in {config_file} ({server})")
    cfg = replace(load(a.config), format=server).validate()
    text = None if a.uninstall else render(blocklist(cfg), cfg)
    try:
        if server == "nftables":
            dest = Path(a.dest or "/etc/nftables.d/n-antibot.nft")
            installer.apply_nftables(
                text or "", cfg.nftables_table, dest, uninstall=a.uninstall, dry_run=a.dry_run, say=say
            )
            return 0
        if config_file is None:
            config_file = installer.find_config(server, a.site)
            if config_file is None:
                raise ValueError(f"no {server} configuration declaring {a.site} was found: pass --config-file FILE")
        p = installer.plan(server, config_file, prefix=cfg.nginx_prefix, dest=Path(a.dest) if a.dest else None)
        agents = cfg.agents()
        installer.apply(
            p,
            a.site,
            text,
            backup_dir=Path(a.backup_dir),
            check_url=a.check_url,
            blocked_agent=agents[0] if agents else None,
            uninstall=a.uninstall,
            dry_run=a.dry_run,
            say=say,
        )
    except installer.InstallError as e:
        print(f"n-antibot: not installed: {e}", file=sys.stderr)
        return 5
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    cfg = _config(a)
    token = os.environ.get("N_ANTIBOT_TOKEN") or None
    if a.token_file:
        token = Path(a.token_file).read_text(encoding="utf-8").strip() or None
    service = api.Service(cfg, a.logs, ranges_ttl=a.refresh_hours * 3600)
    server = api.make_server(service, a.host, a.port, token, a.cors_origin)
    host, port = server.server_address[:2]
    print(
        f"n-antibot: API on http://{host}:{port} ({'token required' if token else 'no token: local use only'})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_presets(_: argparse.Namespace) -> int:
    for title, presets in (
        ("Networks ([networks] presets)", NETWORK_PRESETS),
        ("Robots ([robots] presets)", ROBOT_PRESETS),
    ):
        print(title)
        for p in presets.values():
            mark = "default" if p.default else "opt-in "
            print(f"  {p.name:<24} {mark}  {p.description}")
            print(f"  {'':<24}          {', '.join(p.members)}")
        print()
    return 0


def cmd_init(a: argparse.Namespace) -> int:
    if a.output in (None, "-"):
        sys.stdout.write(EXAMPLE)
        return 0
    path = Path(a.output)
    if path.exists():
        print(f"{path} already exists: not overwritten", file=sys.stderr)
        return 1
    _write_atomic(path, EXAMPLE)
    print(f"written {path}", file=sys.stderr)
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="n-antibot",
        description="Block bot networks and scrapers: Caddy, nginx, Apache, nftables, Cloudflare or JSON.",
    )
    ap.add_argument("--version", action="version", version=f"n-antibot {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser, fmt: bool = True) -> None:
        p.add_argument("-c", "--config", help="TOML configuration (defaults if omitted)")
        if fmt:
            p.add_argument("-f", "--format", choices=FORMATS, help="override output.format")

    p = sub.add_parser("generate", help="download ranges and write the snippet")
    common(p)
    p.add_argument("-o", "--output", help="file to write (stdout if omitted); written atomically")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("check", help="exit 1 if the file is out of date")
    common(p)
    p.add_argument("-o", "--output", required=True, help="file to compare")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("test-agent", help="would this User-Agent be blocked? (exit 0 blocked, 2 allowed)")
    common(p, fmt=False)
    p.add_argument("user_agent")
    p.set_defaults(func=cmd_test_agent)

    p = sub.add_parser("test-ip", help="would this IP be blocked? (exit 0 blocked, 2 allowed)")
    common(p, fmt=False)
    p.add_argument("ip")
    p.set_defaults(func=cmd_test_ip)

    p = sub.add_parser("report", help="read access logs: bots, and paid ad clicks made by bots")
    common(p, fmt=False)
    p.add_argument(
        "logs", nargs="+", help="access logs: Caddy JSON, nginx or Apache combined; .gz allowed; - for stdin"
    )
    p.add_argument("--since", metavar="YYYY-MM-DD", help="first day to include (UTC)")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="last day to include (UTC)")
    p.add_argument("--csv", metavar="FILE", help="write the bot and suspicious ad clicks to a CSV file")
    p.add_argument("--all-clicks", action="store_true", help="with --csv: include the clean clicks too")
    p.add_argument(
        "--claim-dir", metavar="DIR", help="write one claim file per ad platform with what each one asks for"
    )
    p.add_argument("--json", action="store_true", help="print the summary as JSON")
    p.add_argument(
        "--min-repeat", type=int, default=3, metavar="N", help="ad clicks from one IP to call it repeated (3)"
    )
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "install", help="install on Caddy, nginx, Apache or nftables: backup, validate, reload, check, roll back"
    )
    p.add_argument(
        "server", nargs="?", choices=["caddy", "nginx", "apache", "nftables"], help="found automatically if omitted"
    )
    p.add_argument("-c", "--config", help="n-antibot TOML configuration (defaults if omitted)")
    p.add_argument("--site", help="the site to protect, as written in the server configuration (example.com)")
    p.add_argument("--config-file", metavar="FILE", help="server configuration file that declares the site")
    p.add_argument("--dest", metavar="FILE", help="where to put the generated file")
    p.add_argument("--check-url", metavar="URL", help="check the live site afterwards, and roll back if it fails")
    p.add_argument("--backup-dir", metavar="DIR", default="/var/backups/n-antibot", help="where backups go")
    p.add_argument("--dry-run", action="store_true", help="show what would change and change nothing")
    p.add_argument("--uninstall", action="store_true", help="remove it and reload")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("serve", help="read-only JSON API with the report data")
    common(p, fmt=False)
    p.add_argument(
        "logs", nargs="+", help="access logs to read on every request; quote globs: '/var/log/nginx/access.log*'"
    )
    p.add_argument("--host", default="127.0.0.1", help="address to listen on (127.0.0.1)")
    p.add_argument("--port", type=int, default=8787, help="port to listen on (8787)")
    p.add_argument("--token-file", metavar="FILE", help="file with the access token (or set N_ANTIBOT_TOKEN)")
    p.add_argument("--cors-origin", metavar="ORIGIN", help="allow a browser dashboard on this origin to call the API")
    p.add_argument(
        "--refresh-hours", type=float, default=24, metavar="H", help="refresh the network ranges every H hours (24)"
    )
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("presets", help="list built-in network and robot presets")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("init", help="print or write an example configuration")
    p.add_argument("-o", "--output", help="file to create (stdout if omitted)")
    p.set_defaults(func=cmd_init)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.func(a)
    except ConfigError as e:
        print(f"n-antibot: configuration error: {e}", file=sys.stderr)
        return 3
    except FetchError as e:
        print(f"n-antibot: {e}. Nothing was written.", file=sys.stderr)
        return 4
    except ValueError as e:
        print(f"n-antibot: {e}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"n-antibot: {e.filename or ''}: {e.strerror or e}", file=sys.stderr)
        return 3

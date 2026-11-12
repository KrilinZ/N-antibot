"""Command line: n-antibot generate | check | test-agent | test-ip | presets | init."""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from . import __version__
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

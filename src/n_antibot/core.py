"""One call: configuration in, rendered blocklist out."""

from __future__ import annotations

import time
from collections.abc import Callable

from . import ranges
from .config import Config
from .render import Blocklist, render


def blocklist(
    cfg: Config, *, fetch: Callable[..., list[str]] = ranges.fetch_all, today: str | None = None
) -> Blocklist:
    asns = cfg.all_asns()
    # Cloudflare matches by ASN itself: no need to download and expand the ranges.
    prefixes = fetch(asns) if asns and cfg.format != "cloudflare" else []
    v4, v6 = ranges.build(prefixes, cfg.block_cidrs, cfg.allow_cidrs)
    b4, b6 = ranges.build([], cfg.block_cidrs, [])
    a4, a6 = ranges.build([], cfg.allow_cidrs, [])
    return Blocklist(
        v4=v4,
        v6=v6,
        agents=cfg.agents(),
        asns=asns,
        generated_on=today or time.strftime("%Y-%m-%d"),
        manual_block=tuple(b4 + b6),
        manual_allow=tuple(a4 + a6),
    )


def generate(cfg: Config, *, fetch: Callable[..., list[str]] = ranges.fetch_all, today: str | None = None) -> str:
    """Rendered snippet for cfg.format. Raises FetchError if any ASN cannot be downloaded."""
    return render(blocklist(cfg, fetch=fetch, today=today), cfg)

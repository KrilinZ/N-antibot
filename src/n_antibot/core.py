"""One call: configuration in, rendered blocklist out."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from . import ai, ranges, stealth
from .config import Config
from .render import Blocklist, render


def _warn(text: str) -> None:
    print(f"n-antibot: warning: {text}", file=sys.stderr)


def blocklist(
    cfg: Config,
    *,
    fetch: Callable[..., list[str]] = ranges.fetch_all,
    today: str | None = None,
    warn: Callable[[str], None] | None = None,
    chrome: Callable[[], dict[str, int]] | None = None,
) -> Blocklist:
    asns = cfg.all_asns()
    # Cloudflare matches by ASN itself: no need to download and expand the ranges.
    prefixes = fetch(asns) if asns and cfg.format != "cloudflare" else []
    allow = list(cfg.allow_cidrs)
    wants_stealth = cfg.has_stealth()
    if cfg.ai_protect and cfg.format != "cloudflare" and (prefixes or cfg.block_cidrs or cfg.ads_cut or wants_stealth):
        # The published addresses of AI crawlers and search engines are never cut, whatever network they sit in.
        published, failed = ai.protected_ranges()
        for ranges_of_one in published.values():
            allow += ranges_of_one
        for problem in failed:
            (warn or _warn)(
                f"could not download an AI crawler's address list ({problem}): it is not kept open by address"
            )
    v4, v6 = ranges.build(prefixes, cfg.block_cidrs, allow)
    b4, b6 = ranges.build([], cfg.block_cidrs, [])
    a4, a6 = ranges.build([], cfg.allow_cidrs, [])
    rules: tuple[stealth.Rule, ...] = ()
    keep: tuple[str, ...] = ()
    if wants_stealth:
        # Raises FetchError when Google's version history cannot be read: nothing is written then.
        versions = (chrome or stealth.chrome_versions)() if cfg.needs_chrome_versions() else None
        rules = cfg.stealth_rules(versions)
        k4, k6 = ranges.build([], allow, [])  # AI crawlers, search engines and your own allow list
        keep = tuple(k4 + k6)
    ads_asns = cfg.ads_asn_list() if cfg.ads_cut else ()
    ads_prefixes = fetch(ads_asns) if ads_asns and cfg.format != "cloudflare" else []
    ads4, ads6 = ranges.build(ads_prefixes, [], allow) if ads_prefixes else ([], [])
    return Blocklist(
        ads_v4=tuple(ads4),
        ads_v6=tuple(ads6),
        ads_asns=ads_asns,
        v4=v4,
        v6=v6,
        agents=cfg.agents(),
        asns=asns,
        generated_on=today or time.strftime("%Y-%m-%d"),
        manual_block=tuple(b4 + b6),
        manual_allow=tuple(a4 + a6),
        stealth=rules,
        keep_open=keep,
        declared=cfg.declared_regex() if rules else "",
    )


def generate(
    cfg: Config,
    *,
    fetch: Callable[..., list[str]] = ranges.fetch_all,
    today: str | None = None,
    chrome: Callable[[], dict[str, int]] | None = None,
) -> str:
    """Rendered snippet for cfg.format. Raises FetchError if any ASN (or Chrome's version history) cannot be read."""
    return render(blocklist(cfg, fetch=fetch, today=today, chrome=chrome), cfg)

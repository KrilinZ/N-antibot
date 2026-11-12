"""IP ranges: download announced prefixes per ASN from RIPEstat, merge them and subtract allowed ranges."""

from __future__ import annotations

import ipaddress
import json
import os
import random
import time
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Union

Network = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]

RIPESTAT_URL = "https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}&sourceapp=n-antibot"
USER_AGENT = "n-antibot (+https://github.com/KrilinZ/N-antibot)"


class FetchError(RuntimeError):
    """RIPEstat could not be read. Nothing is generated: a partial blocklist is worse than none."""


def _get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def parse_ripestat(asn: str, payload: Any) -> list[str]:
    """Validate the shape of a RIPEstat 'announced-prefixes' answer and return its prefixes."""
    try:
        prefixes = payload["data"]["prefixes"]
        out = [str(p["prefix"]) for p in prefixes]
    except (KeyError, TypeError) as e:
        raise FetchError(f"{asn}: unexpected RIPEstat answer (missing {e})") from None
    if not out:
        raise FetchError(f"{asn}: RIPEstat returned no prefixes")
    for p in out:
        try:
            ipaddress.ip_network(p, strict=False)
        except ValueError:
            raise FetchError(f"{asn}: RIPEstat returned an invalid prefix {p!r}") from None
    return out


def fetch_asn(
    asn: str,
    *,
    timeout: float = 30,
    attempts: int = 4,
    get_json: Callable[[str, float], Any] = _get_json,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Prefixes announced by one ASN. Retries with exponential backoff and jitter, then raises FetchError."""
    last: Exception | None = None
    for n in range(attempts):
        try:
            return parse_ripestat(asn, get_json(RIPESTAT_URL.format(asn=asn), timeout))
        except Exception as e:
            last = e
            if n < attempts - 1:
                sleep(2**n + random.random())
    raise FetchError(f"RIPEstat {asn}: {last}") from last


def fetch_all(asns: Iterable[str], **kw: Any) -> list[str]:
    out: list[str] = []
    for asn in asns:
        out += fetch_asn(asn, **kw)
    return out


def collapse(prefixes: Iterable[str]) -> tuple[list[Network], list[Network]]:
    """Remove duplicates and merge adjacent or nested ranges. Returns (IPv4, IPv6), sorted."""
    v4: list[ipaddress.IPv4Network] = []
    v6: list[ipaddress.IPv6Network] = []
    for p in prefixes:
        net = ipaddress.ip_network(p.strip(), strict=False)
        if isinstance(net, ipaddress.IPv4Network):
            v4.append(net)
        else:
            v6.append(net)
    return list(ipaddress.collapse_addresses(v4)), list(ipaddress.collapse_addresses(v6))


def subtract(blocked: Iterable[Network], allowed: Iterable[Network]) -> list[Network]:
    """Blocked ranges minus allowed ones (an allowed /32 inside a blocked /16 splits it)."""
    result = list(blocked)
    for a in allowed:
        nxt: list[Network] = []
        for b in result:
            if b.version != a.version or not b.overlaps(a):
                nxt.append(b)
            elif b.subnet_of(a):  # type: ignore[arg-type]
                continue
            else:
                nxt += list(b.address_exclude(a))  # type: ignore[arg-type]
        result = nxt
    return sorted(ipaddress.collapse_addresses(result)) if result else []  # type: ignore[type-var]


def build(asn_prefixes: Iterable[str], block: Iterable[str], allow: Iterable[str]) -> tuple[list[str], list[str]]:
    """Final (IPv4, IPv6) lists as strings: ASN prefixes + manual blocks, minus allowed ranges."""
    v4, v6 = collapse([*asn_prefixes, *block])
    a4, a6 = collapse(allow)
    return [str(n) for n in subtract(v4, a4)], [str(n) for n in subtract(v6, a6)]


# ---- a small on-disk cache, for the commands that read many networks (report, serve) ---------------------------
def cache_dir() -> Path | None:
    """Where downloaded ranges are kept. N_ANTIBOT_CACHE=off disables it; any other value is the folder to use."""
    value = os.environ.get("N_ANTIBOT_CACHE", "")
    if value.lower() == "off":
        return None
    if value:
        return Path(value)
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "n-antibot"


def fetch_asn_cached(asn: str, *, ttl: float = 24 * 3600) -> list[str]:
    """Prefixes of one ASN, from the cache when it is younger than `ttl` seconds.

    If the download fails and an older copy exists, the older copy is used: a report with yesterday's ranges is
    better than no report.
    """
    folder = cache_dir()
    if folder is None:
        return fetch_asn(asn)
    path = folder / f"{asn.upper()}.json"
    try:
        if time.time() - path.stat().st_mtime < ttl:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(cached, list) and cached and all(isinstance(p, str) for p in cached):
                return cached
    except (OSError, ValueError):
        pass
    try:
        fresh = fetch_asn(asn)
    except FetchError:
        try:
            stale = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stale, list) and stale:
                return stale
        except (OSError, ValueError):
            pass
        raise
    try:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(fresh), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # a read-only home is not a reason to fail
    return fresh

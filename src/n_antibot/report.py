"""Traffic report from access logs: how many requests came from bots, and how many paid ad clicks were bots.

Reads Caddy JSON logs and the "combined" format of nginx and Apache (plain or .gz). Nothing is sent anywhere: the
only network use is downloading the blocked ranges, exactly as `generate` does.
"""

from __future__ import annotations

import bisect
import csv
import gzip
import io
import ipaddress
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from . import ranges
from .config import Config
from .presets import NETWORK_PRESETS

COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<uri>\S+)[^"]*" (?P<status>\d{3}) \S+'
    r'(?: "(?P<referer>[^"]*)" "(?P<ua>[^"]*)")?'
)
# Statuses that mean "this request was cut off": Caddy abort (0), nginx 444, Apache 403.
CUT_STATUSES = {0, 403, 444}
ASSET = re.compile(r"\.(css|js|mjs|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|map)$", re.I)

# Click identifiers that ad platforms append to the landing URL.
AD_CLICK_IDS = {
    "gclid": "google",
    "gbraid": "google",
    "wbraid": "google",
    "msclkid": "microsoft",
    "ttclid": "tiktok",
    "twclid": "x",
    "li_fat_id": "linkedin",
}
# utm_source spellings of the same platform.
SOURCES = {
    "facebook": "meta",
    "fb": "meta",
    "instagram": "meta",
    "ig": "meta",
    "meta": "meta",
    "adwords": "google",
    "googleads": "google",
    "bing": "microsoft",
    "msn": "microsoft",
    "twitter": "x",
}
# Where campaign details travel in a landing URL: UTM first, then each platform's usual parameter names.
AD_FIELDS = {
    "campaign": ("utm_campaign", "gad_campaignid", "campaignid", "campaign_id", "utm_id"),
    "ad_group": ("utm_adgroup", "adgroupid", "adgroup_id", "adset_id", "utm_adset"),
    "ad_id": ("adid", "ad_id", "creative", "utm_content"),
    "keyword": ("utm_term", "keyword"),
}
PAID_MEDIUMS = {"cpc", "ppc", "paid", "paidsearch", "paid-search", "paidsocial", "paid-social", "display", "cpm"}


@dataclass(frozen=True)
class Hit:
    ts: datetime | None
    ip: str
    method: str
    uri: str
    status: int
    ua: str


def _caddy(obj: dict[str, Any]) -> Hit | None:
    req = obj.get("request")
    if not isinstance(req, dict) or "uri" not in req:
        return None
    ip = req.get("client_ip") or req.get("remote_ip") or str(req.get("remote_addr", "")).rsplit(":", 1)[0]
    headers = req.get("headers") or {}
    ua = headers.get("User-Agent") or headers.get("user-agent") or [""]
    ts = obj.get("ts")
    when = None
    if isinstance(ts, (int, float)):
        when = datetime.fromtimestamp(ts, tz=timezone.utc)
    elif isinstance(ts, str):
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            when = None
    return Hit(
        when,
        str(ip).strip("[]"),
        str(req.get("method", "")),
        str(req["uri"]),
        int(obj.get("status", 0) or 0),
        str(ua[0] if isinstance(ua, list) and ua else ua or ""),
    )


def parse_line(line: str) -> Hit | None:
    """One log line -> Hit, or None when the line is not an access-log entry."""
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            obj = json.loads(line)
        except ValueError:
            return None
        return _caddy(obj) if isinstance(obj, dict) else None
    m = COMBINED.match(line)
    if not m:
        return None
    try:
        when = datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z").astimezone(timezone.utc)
    except ValueError:
        when = None
    return Hit(when, m["ip"], m["method"], m["uri"], int(m["status"]), m["ua"] or "")


def read_logs(paths: Iterable[str]) -> Iterator[str]:
    """Lines of every file ("-" is standard input, *.gz is decompressed)."""
    for path in paths:
        if path == "-":
            yield from sys.stdin
        elif str(path).endswith(".gz"):
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
                yield from f
        else:
            with open(path, encoding="utf-8", errors="replace") as f:
                yield from f


def ad_click(uri: str) -> tuple[str, str] | None:
    """(platform, click id) when the URL carries a paid-click identifier, else None."""
    query = urlsplit(uri).query
    if not query:
        return None
    params = parse_qs(query, keep_blank_values=False)
    for name, platform in AD_CLICK_IDS.items():
        if params.get(name):
            return platform, params[name][0]
    medium = (params.get("utm_medium") or [""])[0].lower()
    if medium in PAID_MEDIUMS:
        source = (params.get("utm_source") or ["other"])[0].lower()
        return SOURCES.get(source, source), ""
    return None


def ad_fields(uri: str) -> dict[str, str]:
    """Campaign, ad group, ad and keyword, when the landing URL carries them (UTM or the platform's own parameters)."""
    params = parse_qs(urlsplit(uri).query)
    return {
        field: next((params[name][0] for name in names if params.get(name)), "") for field, names in AD_FIELDS.items()
    }


class Classifier:
    """Says whether a visitor is a bot according to a configuration: by network (with its ASN) or by User-Agent."""

    def __init__(self, cfg: Config, labelled: Iterable[tuple[str, str]], allow: Iterable[str] = ()):
        self.cfg = cfg
        by_label: dict[str, list[Any]] = defaultdict(list)
        for label, prefix in labelled:
            by_label[label].append(ipaddress.ip_network(prefix.strip(), strict=False))
        rows: dict[int, list[tuple[int, int, str]]] = {4: [], 6: []}
        for label, nets in by_label.items():
            for version in (4, 6):
                for net in ipaddress.collapse_addresses(n for n in nets if n.version == version):
                    rows[version].append((int(net.network_address), int(net.broadcast_address), f"{label} {net}"))
        # Keep the ranges disjoint (drop one nested in another label's range) so a single bisect is exact.
        self._v: dict[int, list[tuple[int, int, str]]] = {4: [], 6: []}
        for version in (4, 6):
            for row in sorted(rows[version], key=lambda r: (r[0], -r[1])):
                if not self._v[version] or row[0] > self._v[version][-1][1]:
                    self._v[version].append(row)
        self._starts = {v: [r[0] for r in found] for v, found in self._v.items()}
        self._allow = [ipaddress.ip_network(a, strict=False) for a in allow]
        self._cache: dict[str, str | None] = {}

    @classmethod
    def from_config(cls, cfg: Config, fetch_asn: Callable[[str], list[str]] | None = None) -> Classifier:
        fetch_asn = fetch_asn or ranges.fetch_asn
        names = {asn: p.name for p in NETWORK_PRESETS.values() for asn in p.members}
        labelled: list[tuple[str, str]] = []
        for asn in cfg.all_asns():
            label = f"{asn} ({names[asn]})" if asn in names else asn
            labelled += [(label, prefix) for prefix in fetch_asn(asn)]
        labelled += [("manual", c) for c in cfg.block_cidrs]
        return cls(cfg, labelled, cfg.allow_cidrs)

    def network(self, ip: str) -> str | None:
        if ip in self._cache:
            return self._cache[ip]
        found = None
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            addr = None
        if addr is not None:
            if addr.version == 6 and addr.ipv4_mapped:
                addr = addr.ipv4_mapped
            if not any(addr.version == a.version and addr in a for a in self._allow):
                rows, value = self._v[addr.version], int(addr)
                i = bisect.bisect_right(self._starts[addr.version], value) - 1
                if i >= 0 and rows[i][1] >= value:
                    found = rows[i][2]
        self._cache[ip] = found
        return found

    def verdict(self, ip: str, ua: str) -> tuple[str, str] | None:
        """('network', 'AS132203 (tencent-cloud) 43.173.0.0/16') | ('agent', 'Bytespider') | None."""
        net = self.network(ip)
        if net:
            return "network", net
        agent = self.cfg.blocks_agent(ua)
        if agent:
            return "agent", agent
        return None


@dataclass
class AdClick:
    platform: str
    click_id: str
    first: Hit
    reason: str = ""  # network | agent | repeated | no-resources | ""
    detail: str = ""
    cut: bool = False
    raw: str = ""  # the log line of the click, as evidence


@dataclass
class Report:
    lines: int = 0
    parsed: int = 0
    first: datetime | None = None
    last: datetime | None = None
    requests: int = 0
    ips: int = 0
    bot_requests: int = 0
    bot_cut: int = 0
    bot_served: int = 0
    bot_ips: int = 0
    by_reason: Counter = field(default_factory=Counter)
    by_detail: Counter = field(default_factory=Counter)
    clicks: list[AdClick] = field(default_factory=list)
    top_unblocked: list[tuple[str, int, int, str]] = field(default_factory=list)  # ip, requests, assets, sample UA

    def clicks_by(self, platform: str | None = None) -> dict[str, int]:
        rows = [c for c in self.clicks if platform in (None, c.platform)]
        out = Counter(c.reason or "clean" for c in rows)
        out["total"] = len(rows)
        return dict(out)

    def platforms(self) -> list[str]:
        return sorted({c.platform for c in self.clicks}, key=lambda p: (p != "google", p))


def analyze(
    lines: Iterable[str],
    classifier: Classifier,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    min_repeat: int = 3,
    top: int = 10,
) -> Report:
    rep = Report()
    per_ip: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # requests, asset requests
    sample_ua: dict[str, str] = {}
    bot_ips: set[str] = set()
    clicks: dict[tuple[str, str], AdClick] = {}
    clicks_per_ip: dict[str, set[tuple[str, str]]] = defaultdict(set)
    anonymous = 0

    for line in lines:
        rep.lines += 1
        hit = parse_line(line)
        if hit is None:
            continue
        rep.parsed += 1
        if hit.ts is not None:
            if (since and hit.ts < since) or (until and hit.ts >= until):
                continue
            rep.first = hit.ts if rep.first is None or hit.ts < rep.first else rep.first
            rep.last = hit.ts if rep.last is None or hit.ts > rep.last else rep.last
        rep.requests += 1
        stats = per_ip[hit.ip]
        stats[0] += 1
        path = urlsplit(hit.uri).path
        if ASSET.search(path):
            stats[1] += 1
        sample_ua.setdefault(hit.ip, hit.ua)

        verdict = classifier.verdict(hit.ip, hit.ua)
        cut = hit.status in CUT_STATUSES
        if verdict:
            rep.bot_requests += 1
            rep.bot_cut += cut
            rep.bot_served += not cut
            rep.by_reason[verdict[0]] += 1
            rep.by_detail[verdict[1].rsplit(" ", 1)[0] if verdict[0] == "network" else verdict[1]] += 1
            bot_ips.add(hit.ip)

        ad = ad_click(hit.uri)
        if ad:
            platform, click_id = ad
            if not click_id:  # paid visit without a click id: count each landing request once per IP and URL
                anonymous += 1
                click_id = f"(no id) {hit.ip} {path}"
            key = (platform, click_id)
            if key not in clicks:
                clicks[key] = AdClick(platform, click_id, hit, raw=line.strip())
                clicks_per_ip[hit.ip].add(key)
            click = clicks[key]
            if verdict and not click.reason:
                click.reason, click.detail = verdict
            click.cut = click.cut or (bool(verdict) and cut)

    # Hints for clicks that no list caught. They are indications, not proof.
    any_assets = any(s[1] for s in per_ip.values())
    for click in clicks.values():
        if click.reason:
            continue
        ip = click.first.ip
        if len(clicks_per_ip[ip]) >= min_repeat:
            click.reason, click.detail = "repeated", f"{len(clicks_per_ip[ip])} ad clicks from this IP"
        elif any_assets and per_ip[ip][0] == 1:
            click.reason, click.detail = (
                "no-resources",
                "one single request: the page, but no images, styles or scripts",
            )

    rep.ips = len(per_ip)
    rep.bot_ips = len(bot_ips)
    rep.clicks = sorted(clicks.values(), key=lambda c: c.first.ts or datetime.min.replace(tzinfo=timezone.utc))
    unblocked = [(ip, s[0], s[1], sample_ua.get(ip, "")) for ip, s in per_ip.items() if ip not in bot_ips]
    rep.top_unblocked = sorted(unblocked, key=lambda r: -r[1])[:top]
    return rep


REASONS = {
    "network": "from a blocked network",
    "agent": "blocked robot or scraper",
    "repeated": "same IP clicked several ads (hint)",
    "no-resources": "loaded no page resources (hint)",
}


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "0.0%"


def render_text(rep: Report) -> str:
    out: list[str] = []
    period = "unknown period"
    if rep.first and rep.last:
        period = f"{rep.first:%Y-%m-%d %H:%M} to {rep.last:%Y-%m-%d %H:%M} UTC"
    out += [
        "N-antibot traffic report",
        f"  Period:    {period}",
        f"  Requests:  {rep.requests} from {rep.ips} IP addresses ({rep.lines - rep.parsed} unreadable lines)",
        "",
        "Bots",
        f"  Requests from bots: {rep.bot_requests} ({_pct(rep.bot_requests, rep.requests)}) from {rep.bot_ips} IPs",
        f"    cut off:  {rep.bot_cut}",
        f"    served:   {rep.bot_served}" + ("   <- N-antibot is not stopping these yet" if rep.bot_served else ""),
    ]
    for name, n in rep.by_detail.most_common(8):
        out.append(f"    {n:>7}  {name}")
    out += ["", "Paid ad clicks"]
    if not rep.clicks:
        out.append("  None found (no gclid, msclkid... or utm_medium=cpc in the logged URLs).")
    for platform in rep.platforms():
        c = rep.clicks_by(platform)
        bots = c.get("network", 0) + c.get("agent", 0)
        hints = c.get("repeated", 0) + c.get("no-resources", 0)
        out += [
            f"  {platform}: {c['total']} clicks",
            f"    bots:        {bots} ({_pct(bots, c['total'])})"
            f"  [network {c.get('network', 0)}, robot {c.get('agent', 0)}]",
            f"    suspicious:  {hints} ({_pct(hints, c['total'])})"
            f"  [repeated IP {c.get('repeated', 0)}, no resources {c.get('no-resources', 0)}]",
            f"    clean:       {c.get('clean', 0)}",
        ]
    flagged = Counter()
    why: dict[str, str] = {}
    for c in rep.clicks:
        if c.reason:
            flagged[c.first.ip] += 1
            why.setdefault(c.first.ip, c.detail if c.reason in ("network", "agent") else REASONS[c.reason])
    if flagged:
        out += ["", "IP addresses behind bot and suspicious ad clicks (clicks, IP, why)"]
        for ip, n in flagged.most_common(15):
            out.append(f"  {n:>5}  {ip:<39}  {why[ip]}")
        if len(flagged) > 15:
            out.append(f"  ... and {len(flagged) - 15} more: use --csv for the full list")
    if rep.top_unblocked:
        out += ["", "Busiest visitors that are NOT blocked (review them: requests, page resources, user agent)"]
        for ip, n, assets, ua in rep.top_unblocked:
            out.append(f"  {n:>7}  {assets:>6}  {ip:<39}  {ua[:60]}")
    return "\n".join(out) + "\n"


CSV_HEADER = [
    "date_utc",
    "time_utc",
    "platform",
    "click_id",
    "ip",
    "verdict",
    "reason",
    "detail",
    "cut_off",
    "status",
    "user_agent",
    "campaign",
    "ad_group",
    "ad_id",
    "keyword",
    "url",
]


def write_csv(rep: Report, target: io.TextIOBase, *, include_clean: bool = False) -> int:
    """Ad clicks as CSV (bots and suspicious ones; every click with include_clean). Returns the number of rows."""
    w = csv.writer(target, lineterminator="\n")
    w.writerow(CSV_HEADER)
    rows = 0
    for c in rep.clicks:
        if not c.reason and not include_clean:
            continue
        verdict = "bot" if c.reason in ("network", "agent") else ("suspicious" if c.reason else "clean")
        ts = c.first.ts
        w.writerow(
            [
                f"{ts:%Y-%m-%d}" if ts else "",
                f"{ts:%H:%M:%S}" if ts else "",
                c.platform,
                c.click_id,
                c.first.ip,
                verdict,
                REASONS.get(c.reason, ""),
                c.detail,
                "yes" if c.cut else "no",
                c.first.status,
                c.first.ua,
                *ad_fields(c.first.uri).values(),
                c.first.uri,
            ]
        )
        rows += 1
    return rows


def as_dict(rep: Report) -> dict[str, Any]:
    return {
        "period": {
            "from": rep.first.isoformat() if rep.first else None,
            "to": rep.last.isoformat() if rep.last else None,
        },
        "requests": rep.requests,
        "ips": rep.ips,
        "unreadable_lines": rep.lines - rep.parsed,
        "bots": {
            "requests": rep.bot_requests,
            "ips": rep.bot_ips,
            "cut_off": rep.bot_cut,
            "served": rep.bot_served,
            "by": dict(rep.by_detail.most_common()),
        },
        "ad_clicks": {p: rep.clicks_by(p) for p in rep.platforms()},
        "top_unblocked": [
            {"ip": ip, "requests": n, "resources": a, "user_agent": ua} for ip, n, a, ua in rep.top_unblocked
        ],
    }


def click_verdict(c: AdClick) -> str:
    return "bot" if c.reason in ("network", "agent") else ("suspicious" if c.reason else "clean")


def click_dict(c: AdClick) -> dict[str, Any]:
    """One ad click as plain data (the JSON twin of a CSV row)."""
    ts = c.first.ts
    return {
        "timestamp": ts.isoformat() if ts else None,
        "date_utc": f"{ts:%Y-%m-%d}" if ts else None,
        "time_utc": f"{ts:%H:%M:%S}" if ts else None,
        "platform": c.platform,
        "click_id": c.click_id,
        "ip": c.first.ip,
        "verdict": click_verdict(c),
        "reason": REASONS.get(c.reason),
        "detail": c.detail or None,
        "cut_off": c.cut,
        "status": c.first.status,
        "user_agent": c.first.ua,
        **{k: v or None for k, v in ad_fields(c.first.uri).items()},
        "url": c.first.uri,
    }

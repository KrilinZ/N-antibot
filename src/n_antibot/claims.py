"""Where and how each ad platform lets you dispute invalid clicks, and one claim file per platform.

Every entry was read on the platform's own pages on the date in `checked`; `source` is that page. Platforms change
their rules: check the source before filing.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import report

CHECKED = "2026-11-12"


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    has_process: bool  # is there a documented way to dispute invalid clicks?
    where: str
    url: str
    window_days: int | None
    asks: tuple[str, ...]  # what the platform says it needs
    outcome: str
    source: str
    checked: str = CHECKED


PLATFORMS: dict[str, Platform] = {
    p.key: p
    for p in [
        Platform(
            "google",
            "Google Ads",
            True,
            "Click Quality Form",
            "https://support.google.com/google-ads/contact/click_quality",
            60,
            (
                "Date range of the suspicious activity (within the past 60 days)",
                "Campaign and ad group names",
                "Suspicious keywords",
                "Web server logs: IP addresses with repetitive clicks or clicks without conversions",
                "Web server logs: browser or device information",
                "Web server logs: GCLIDs of the suspicious clicks",
                "A brief explanation of why the traffic is suspicious",
            ),
            "Specialists review the last 60 days and email the findings; if more invalid traffic is found, Google "
            "notifies you of the credit. It does not confirm click by click.",
            "https://support.google.com/google-ads/answer/11182074",
        ),
        Platform(
            "microsoft",
            "Microsoft Advertising",
            True,
            "Contact Microsoft Advertising Support and say it is a traffic quality / invalid click issue",
            "https://go.microsoft.com/fwlink?LinkId=398371",
            60,
            (
                "A note that it is a traffic quality, click quality or invalid click issue",
                "Affected ad group and ad group number",
                "Affected ad ID and keywords",
                "Date range of the issue",
                "A brief description of the trends in your reports or web server logs that make you suspect",
                "A sample of your web server log file, if Support asks for it",
            ),
            "Best filed within 30 days; no investigation after 60 days. Microsoft tries to finish within nine days and "
            "recommends reimbursement if the traffic is found to be invalid.",
            "https://help.ads.microsoft.com/#apex/ads/en/60220/0",
        ),
        Platform(
            "linkedin",
            "LinkedIn Ads",
            True,
            "Written notice to LinkedIn (Campaign Manager support) of the fees you dispute and why",
            "https://www.linkedin.com/help/lms/ask",
            90,
            ("The fees you dispute", "The basis for the dispute (the invalid activity)"),
            "Only an Ad Services credit, at LinkedIn's sole discretion; no cash refund.",
            "https://www.linkedin.com/legal/sas-terms",
        ),
        Platform(
            "x",
            "X Ads",
            True,
            "Support ticket; disputes about charges must be in writing",
            "https://ads.x.com/en/help",
            60,
            ("The charges you dispute, in writing",),
            "A refund is only processed if the investigation finds a billing or technical error.",
            "https://help.x.com/en/business-and-advertising/billing-basics",
        ),
        Platform(
            "meta",
            "Meta Ads (Facebook, Instagram)",
            False,
            "Ads payment support form (general refunds: Meta documents no process for invalid clicks)",
            "https://www.facebook.com/help/contact/649167531904667",
            None,
            (),
            "Decided case by case, at Meta's sole discretion, and final. Refunds usually take at least one month. "
            "No refunds for poor ad performance.",
            "https://www.facebook.com/business/help/211313200321572",
        ),
        Platform(
            "pinterest",
            "Pinterest Ads",
            False,
            "Contact Pinterest support (no documented process for invalid clicks)",
            "https://help.pinterest.com/en/business/article/refunds-and-chargebacks",
            None,
            (),
            "Pinterest says standard charges are usually not eligible for a refund or credit.",
            "https://help.pinterest.com/en/business/article/refunds-and-chargebacks",
        ),
    ]
}


def generic(key: str) -> Platform:
    return Platform(
        key,
        key,
        False,
        "No documented process found: contact the platform's support with this file",
        "",
        None,
        (),
        "Unknown.",
        "",
    )


def info(key: str) -> Platform:
    return PLATFORMS.get(key) or generic(key)


def _within(click: report.AdClick, platform: Platform, today: datetime) -> str:
    if platform.window_days is None or click.first.ts is None:
        return ""
    return "yes" if click.first.ts >= today - timedelta(days=platform.window_days) else "no"


PACK_HEADER = [*report.CSV_HEADER[:-1], "within_deadline", "url"]


def _n(count: int, word: str = "click") -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _explanation(rows: list[report.AdClick], total: int, first: str, last: str) -> str:
    nets = Counter(c.detail.rsplit(" ", 1)[0] for c in rows if c.reason in ("network", "datacenter"))
    agents = Counter(c.detail for c in rows if c.reason == "agent")
    bots = sum(nets.values()) + sum(agents.values())
    parts = [
        f"Between {first} and {last} (UTC) our web server logs recorded {total} paid ad clicks. "
        f"{bots} of them were made by automated clients, not by people."
    ]
    if nets:
        listed = ", ".join(f"{n} from {name}" for name, n in nets.most_common(5))
        parts.append(
            f"{_n(sum(nets.values()))} came from data-center networks ({listed}); customers do not browse from "
            "cloud servers."
        )
    if agents:
        listed = ", ".join(f"{n} as {name}" for name, n in agents.most_common(5))
        parts.append(f"{_n(sum(agents.values()))} identified as robots or scraping libraries ({listed}).")
    hints = len(rows) - bots
    if hints:
        parts.append(
            f"{_n(hints)} more looked suspicious: the same IP address clicking several ads, or a visit that requested "
            "the page and nothing else."
        )
    parts.append("The attached file lists each click with its date and time, IP address, browser and click ID.")
    return " ".join(parts)


def write_packs(rep: report.Report, outdir: str | Path, *, today: datetime | None = None) -> list[dict[str, Any]]:
    """One claim file per platform with flagged clicks: <platform>-clicks.csv, -log-sample.log and -claim.txt."""
    today = today or datetime.now(timezone.utc)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for key in rep.platforms():
        platform = info(key)
        every = [c for c in rep.clicks if c.platform == key]
        rows = [c for c in every if c.reason]
        if not rows:
            continue
        inside = [c for c in rows if _within(c, platform, today) != "no"]

        with open(out / f"{key}-clicks.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(PACK_HEADER)
            for c in rows:
                d = report.click_dict(c)
                w.writerow(
                    [
                        d["date_utc"] or "",
                        d["time_utc"] or "",
                        d["platform"],
                        d["click_id"],
                        d["ip"],
                        d["verdict"],
                        d["reason"] or "",
                        d["detail"] or "",
                        "yes" if d["cut_off"] else "no",
                        d["status"],
                        d["user_agent"],
                        d["campaign"] or "",
                        d["ad_group"] or "",
                        d["ad_id"] or "",
                        d["keyword"] or "",
                        _within(c, platform, today),
                        d["url"],
                    ]
                )
        (out / f"{key}-log-sample.log").write_text("".join(c.raw + "\n" for c in rows[:500] if c.raw), encoding="utf-8")

        stamps = [c.first.ts for c in rows if c.first.ts]
        first = f"{min(stamps):%Y-%m-%d}" if stamps else "unknown"
        last = f"{max(stamps):%Y-%m-%d}" if stamps else "unknown"
        fields = Counter()
        for c in rows:
            for name, value in report.ad_fields(c.first.uri).items():
                fields[name] += bool(value)
        ips = Counter(c.first.ip for c in rows)
        why = {c.first.ip: (c.detail if c.reason in report.BOT_REASONS else report.REASONS[c.reason]) for c in rows}
        bots = sum(c.reason in report.BOT_REASONS for c in rows)

        t = [f"N-antibot claim file: {platform.name}", ""]
        if platform.source:
            t += [f"Rules read on the platform's own pages on {platform.checked}: {platform.source}", ""]
        t += ["WHERE TO CLAIM", f"  {platform.where}"]
        if platform.url:
            t.append(f"  {platform.url}")
        t += ["", "DEADLINE"]
        if platform.window_days:
            t.append(f"  {platform.window_days} days from the activity.")
            t.append(
                f"  In this file: {len(inside)} clicks inside the deadline, {len(rows) - len(inside)} already too old."
            )
        else:
            t.append("  The platform documents none.")
        t += ["", "RESULT YOU CAN EXPECT", f"  {platform.outcome}", "", "WHAT THE PLATFORM ASKS FOR"]
        t += [f"  - {a}" for a in platform.asks] or ["  It does not say. Send the three sections below."]
        t += [
            "",
            "WHAT THIS FILE GIVES YOU",
            f"  - Date range: {first} to {last} (UTC)",
            f"  - Click IDs, IP addresses, browser, date and time: {key}-clicks.csv ({len(rows)} clicks)",
            f"  - Web server log lines of those clicks: {key}-log-sample.log",
            f"  - Campaign in the URL: {fields['campaign']} of {len(rows)} clicks; ad group: {fields['ad_group']}; "
            f"ad: {fields['ad_id']}; keyword: {fields['keyword']}",
            "",
            "WHAT YOU MUST ADD FROM YOUR AD ACCOUNT",
            "  - Your customer or account ID",
            "  - Campaign, ad group and keyword names, for the clicks whose URL does not carry them",
            "    (tip: add campaign, ad group and keyword to your tracking template and the next report has them)",
            "",
            "SUMMARY",
            f"  Paid clicks from {platform.name} in the logs: {len(every)}",
            f"  Bots: {bots}    Suspicious (hints, not proof): {len(rows) - bots}    Clean: {len(every) - len(rows)}",
            "",
            "EXPLANATION YOU CAN PASTE",
            f"  {_explanation(rows, len(every), first, last)}",
            "",
            "IP ADDRESSES (clicks, address, why)",
        ]
        t += [f"  {n:>5}  {ip:<39}  {why[ip]}" for ip, n in ips.most_common(50)]
        (out / f"{key}-claim.txt").write_text("\n".join(t) + "\n", encoding="utf-8")
        written.append(
            {
                "platform": key,
                "name": platform.name,
                "clicks": len(rows),
                "bots": bots,
                "within_deadline": len(inside),
                "has_process": platform.has_process,
                "files": [f"{key}-claim.txt", f"{key}-clicks.csv", f"{key}-log-sample.log"],
            }
        )
    return written


def as_dict() -> list[dict[str, Any]]:
    """The platform table as plain data (for the API and the docs)."""
    return [
        {
            "platform": p.key,
            "name": p.name,
            "has_process": p.has_process,
            "where": p.where,
            "url": p.url,
            "deadline_days": p.window_days,
            "asks": list(p.asks),
            "outcome": p.outcome,
            "source": p.source,
            "checked": p.checked,
        }
        for p in PLATFORMS.values()
    ]

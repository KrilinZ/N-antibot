"""AI crawlers and search engines must always be able to read the site.

Their operators publish the addresses they crawl from. N-antibot downloads those lists and never cuts those
addresses, even when they sit inside a cloud network you chose to block. Being verified by address, this cannot be
abused by a scraper that merely claims to be GPTBot.
"""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from . import ranges
from .config import Config

USER_AGENT = ranges.USER_AGENT


@dataclass(frozen=True)
class Crawler:
    key: str
    operator: str
    agent: str  # the fragment that identifies it in the User-Agent
    purpose: str
    url: str | None  # the operator's own machine-readable list of addresses; None when N-antibot has none for it


# Lists read on 2026-11-13. Each URL is the operator's own file, in the format Google introduced:
# {"prefixes": [{"ipv4Prefix": "..."} | {"ipv6Prefix": "..."}]}.
GOOGLE = "https://developers.google.com/static/search/apis/ipranges"
CRAWLERS: tuple[Crawler, ...] = (
    Crawler("gptbot", "OpenAI", "GPTBot", "training", "https://openai.com/gptbot.json"),
    Crawler("oai-searchbot", "OpenAI", "OAI-SearchBot", "ChatGPT search", "https://openai.com/searchbot.json"),
    Crawler(
        "chatgpt-user", "OpenAI", "ChatGPT-User", "ChatGPT browsing for a user", "https://openai.com/chatgpt-user.json"
    ),
    Crawler("perplexitybot", "Perplexity", "PerplexityBot", "search", "https://www.perplexity.com/perplexitybot.json"),
    Crawler(
        "perplexity-user",
        "Perplexity",
        "Perplexity-User",
        "browsing for a user",
        "https://www.perplexity.com/perplexity-user.json",
    ),
    Crawler("googlebot", "Google", "Googlebot", "search and AI Overviews", f"{GOOGLE}/googlebot.json"),
    Crawler(
        "google-special",
        "Google",
        "Google-InspectionTool",
        "special crawlers (AdsBot, Storebot...)",
        f"{GOOGLE}/special-crawlers.json",
    ),
    Crawler(
        "google-user",
        "Google",
        "Google-Read-Aloud",
        "fetches triggered by users",
        f"{GOOGLE}/user-triggered-fetchers.json",
    ),
    Crawler(
        "google-user-google",
        "Google",
        "Google-NotebookLM",
        "fetches triggered by users (Gemini, NotebookLM)",
        f"{GOOGLE}/user-triggered-fetchers-google.json",
    ),
    Crawler("bingbot", "Microsoft", "bingbot", "search and Copilot", "https://www.bing.com/toolbox/bingbot.json"),
    Crawler(
        "applebot",
        "Apple",
        "Applebot",
        "search, Siri and Apple Intelligence",
        "https://search.developer.apple.com/applebot.json",
    ),
    Crawler(
        "mistral-user", "Mistral", "MistralAI-User", "browsing for a user", "https://mistral.ai/mistralai-user-ips.json"
    ),
    Crawler(
        "ccbot", "Common Crawl", "CCBot", "open crawl used to train models", "https://index.commoncrawl.org/ccbot.json"
    ),
    Crawler("duckassistbot", "DuckDuckGo", "DuckAssistBot", "AI answers", "https://duckduckgo.com/duckassistbot.json"),
    Crawler("duckduckbot", "DuckDuckGo", "DuckDuckBot", "search", "https://duckduckgo.com/duckduckbot.json"),
    # Recognised by name. N-antibot has no machine-readable address list for these.
    Crawler("claudebot", "Anthropic", "ClaudeBot", "training", None),
    Crawler("claude-user", "Anthropic", "Claude-User", "browsing for a user", None),
    Crawler("claude-searchbot", "Anthropic", "Claude-SearchBot", "search", None),
    Crawler("meta-externalagent", "Meta", "meta-externalagent", "training", None),
    Crawler("meta-externalfetcher", "Meta", "meta-externalfetcher", "fetches triggered by users", None),
    Crawler("amazonbot", "Amazon", "Amazonbot", "Alexa and search", None),
)


def parse(payload: Any) -> list[str]:
    """Validate an operator's list and return its ranges."""
    try:
        out = [str(p.get("ipv4Prefix") or p["ipv6Prefix"]) for p in payload["prefixes"]]
    except (KeyError, TypeError, AttributeError) as e:
        raise ranges.FetchError(f"unexpected format (missing {e})") from None
    if not out:
        raise ranges.FetchError("the list is empty")
    for p in out:
        try:
            ipaddress.ip_network(p, strict=False)
        except ValueError:
            raise ranges.FetchError(f"invalid range {p!r}") from None
    return out


def _download(url: str, timeout: float = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch(crawler: Crawler, *, ttl: float = 24 * 3600, download: Callable[[str], Any] | None = None) -> list[str]:
    """Published ranges of one crawler, cached like the network ranges. Raises FetchError."""
    if crawler.url is None:
        return []
    download = download or _download
    folder = ranges.cache_dir()
    path = folder / f"ai-{crawler.key}.json" if folder else None
    if path is not None:
        try:
            if time.time() - path.stat().st_mtime < ttl:
                return parse({"prefixes": json.loads(path.read_text(encoding="utf-8"))})
        except (OSError, ValueError, ranges.FetchError):
            pass
    try:
        payload = download(crawler.url)
        fresh = parse(payload)
    except Exception as e:
        if path is not None:
            try:
                return parse({"prefixes": json.loads(path.read_text(encoding="utf-8"))})
            except (OSError, ValueError, ranges.FetchError):
                pass
        raise ranges.FetchError(f"{crawler.operator} {crawler.agent}: {e}") from e
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps([{"ipv6Prefix" if ":" in p else "ipv4Prefix": p} for p in fresh]), encoding="utf-8"
            )
            tmp.replace(path)
        except OSError:
            pass
    return fresh


def protected_ranges(download: Callable[[str], Any] | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """({crawler key: ranges}, [what could not be downloaded]). A failure never stops the rest."""
    found: dict[str, list[str]] = {}
    failed: list[str] = []
    for crawler in CRAWLERS:
        if crawler.url is None:
            continue
        try:
            found[crawler.key] = fetch(crawler, download=download)
        except ranges.FetchError as e:
            failed.append(str(e))
    return found, failed


def blocked_agents(cfg: Config) -> list[tuple[Crawler, str]]:
    """AI crawlers and search engines that this configuration would cut by name: [(crawler, fragment)]."""
    out = []
    for crawler in CRAWLERS:
        hit = cfg.blocks_agent(f"{crawler.agent}/1.0")
        if hit:
            out.append((crawler, hit))
    return out


def check(
    cfg: Config, blocked_prefixes: list[str], published: dict[str, list[str]], failed: list[str]
) -> list[dict[str, Any]]:
    """For each crawler: does this configuration let it in? `blocked_prefixes` are the networks cut for everyone."""
    v4, v6 = ranges.collapse(blocked_prefixes)
    blocked = {4: v4, 6: v6}
    names = {c.key: hit for c, hit in blocked_agents(cfg)}
    rows = []
    for crawler in CRAWLERS:
        mine = [ipaddress.ip_network(p, strict=False) for p in published.get(crawler.key, [])]
        inside = [str(n) for n in mine if any(n.overlaps(b) for b in blocked[n.version])]
        by_name = names.get(crawler.key)
        if by_name:
            status, note = "cut", f"your robot list blocks it by name ({by_name})"
        elif inside and not cfg.ai_protect:
            status, note = "cut", f"{len(inside)} of its {len(mine)} ranges are in networks you block"
        elif inside:
            status, note = "ok", f"{len(inside)} of its {len(mine)} ranges are in networks you block: kept open for it"
        elif crawler.url is None:
            status, note = "ok", "passes by name; there is no address list for it, so it is not kept open by address"
        elif crawler.key not in published:
            status, note = "unknown", "its address list could not be downloaded"
        else:
            status, note = "ok", f"none of its {len(mine)} ranges is in a network you block"
        rows.append(
            {
                "crawler": crawler.agent,
                "operator": crawler.operator,
                "purpose": crawler.purpose,
                "status": status,
                "note": note,
                "published_ranges": len(mine),
                "ranges_in_blocked_networks": len(inside),
                "source": crawler.url,
            }
        )
    return rows

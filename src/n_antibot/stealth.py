"""Bots that pose as a real browser: header fingerprints, protocol mismatch, impossible Chrome versions, referer spam.

Network lists cannot stop a bot that rents residential proxies (one home address per request). What gives it away is
how it talks: a Chrome that speaks HTTP/1.1 to an HTTPS site, that never sends the Fetch Metadata headers every real
Chrome sends, that always sends the same Accept-Language, or that claims a version Google has not released.

A fingerprint rule cuts a request only when ALL its conditions hold. Every rule also has fixed guards that cannot be
turned off: a User-Agent that declares a robot or a known tool (bot, crawl, Google, Bing, GPTBot, ChatGPT...) is
never cut, a request signed with Web Bot Auth (Signature-Agent) is never cut, and with `[ai] protect` the published
addresses of AI crawlers and search engines are never cut either.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from . import ranges
from .presets import AI_AGENTS

# ---- guards ---------------------------------------------------------------------------------------------------------
# Fragments that mark a User-Agent as a declared robot, a preview fetcher or a measuring tool. Case-insensitive.
# Googlebot, Bingbot, Storebot, AdsBot, GoogleOther, Google-Read-Aloud, Chrome-Lighthouse, MicrosoftPreview, GPTBot,
# ChatGPT-User, OAI-SearchBot, ClaudeBot, PerplexityBot, Applebot... all carry at least one of them.
DECLARED: tuple[str, ...] = (
    "bot",
    "spider",
    "crawl",
    "slurp",
    "compatible;",
    "google",
    "bing",
    "msnbot",
    "preview",
    "lighthouse",
    "pagespeed",
    "facebook",
    "meta-external",
    "openai",
    "chatgpt",
    "gpt",
    "claude",
    "anthropic",
    "perplexity",
    "applebot",
    "mistral",
    "duckduck",
    "duckassist",
    "amazon",
    "yandex",
    "baidu",
    "petal",
    "cohere",
    "yahoo",
    "ia_archiver",
    "archive.org",
)
# Web Bot Auth (RFC 9421 HTTP message signatures): signed agents such as ChatGPT agent send this header.
SIGNED_HEADER = "Signature-Agent"

PROTOCOLS = {"http/1.0": "HTTP/1.0", "http/1.1": "HTTP/1.1", "http/2": "HTTP/2", "http/3": "HTTP/3"}
HEADER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
# Header values that are safe to place, quoted, in Caddy, nginx, Apache and Cloudflare: printable ASCII without
# quotes, backslashes, braces (Caddy placeholders), "*" (Caddy wildcards) or "|" (field separator in nginx).
HEADER_VALUE_RE = re.compile(r"^[A-Za-z0-9 !#$%&'()+,\-./:;<=>?@\[\]^_`~]{1,200}$")
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
# Referers that real visitors bring. A referer-spam domain may never match them.
REAL_REFERERS: tuple[str, ...] = (
    "https://www.google.com/",
    "https://www.google.es/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://search.yahoo.com/",
    "https://chatgpt.com/",
    "https://www.perplexity.ai/",
    "https://gemini.google.com/",
    "https://copilot.microsoft.com/",
    "https://l.facebook.com/",
    "https://www.instagram.com/",
    "https://t.co/",
    "https://www.linkedin.com/",
    "https://www.youtube.com/",
    "android-app://com.google.android.gm/",
)


@dataclass(frozen=True)
class Fingerprint:
    """A configured rule. Every condition that is set must hold for the request to be cut."""

    name: str
    description: str = ""
    browser: str = "chrome"  # "chrome": the User-Agent claims Chrome or a Chromium browser; "any": any Mozilla/5.0
    protocols: tuple[str, ...] = ()  # canonical names, e.g. ("HTTP/1.1",); empty = any protocol
    https: bool = False  # only over TLS (Fetch Metadata and client hints are only sent to secure origins)
    headers: tuple[tuple[str, str], ...] = ()  # (name, exact value)
    missing: tuple[str, ...] = ()  # headers that must be absent
    chrome_min: int = 0  # the claimed Chrome major is at least this (0: any)
    chrome_behind: int = 0  # the claimed Chrome major is more than N versions behind today's stable (0: off)

    def conditions(self) -> int:
        n = int(bool(self.protocols)) + len(self.headers) + len(self.missing) + int(self.https)
        return n + int(bool(self.chrome_behind))


# Ready-made rules. All opt-in: list them under [stealth] presets.
FINGERPRINT_PRESETS: dict[str, Fingerprint] = {
    f.name: f
    for f in [
        Fingerprint(
            "chrome-without-fetch-metadata",
            "Claims Chrome 90+ over HTTPS but sends neither Sec-Fetch-Mode nor Sec-Ch-Ua. Every real Chrome, Edge, "
            "Opera or Brave sends both to an HTTPS site.",
            https=True,
            missing=("Sec-Fetch-Mode", "Sec-Ch-Ua"),
            chrome_min=90,
        ),
        Fingerprint(
            "chrome-http1-without-fetch-metadata",
            "Claims Chrome over HTTP/1.x to an HTTPS site and sends no Sec-Fetch-Mode. A real Chrome speaks HTTP/2 or "
            "HTTP/3 whenever the server offers it, and always sends Sec-Fetch-Mode.",
            protocols=("HTTP/1.0", "HTTP/1.1"),
            https=True,
            missing=("Sec-Fetch-Mode",),
        ),
        Fingerprint(
            "residential-proxy-zh",
            "Chrome over HTTP/1.x to an HTTPS site, without Sec-Fetch-Mode and with the fixed Accept-Language "
            "'zh-CN,zh;q=0.9,en;q=0.8': a scraper seen in November 2026 rotating thousands of residential proxies, "
            "one page per address. Narrower than chrome-http1-without-fetch-metadata.",
            protocols=("HTTP/1.0", "HTTP/1.1"),
            https=True,
            headers=(("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),),
            missing=("Sec-Fetch-Mode",),
        ),
    ]
}

# ---- real requests that no rule may ever cut (checked when the configuration is loaded) ---------------------------
CURRENT = 0  # placeholder for "today's Chrome version": version conditions never hold for it


@dataclass(frozen=True)
class Request:
    label: str
    user_agent: str
    protocol: str = "HTTP/2"
    https: bool = True
    headers: tuple[tuple[str, str], ...] = ()
    ip: str = ""

    def header(self, name: str) -> str | None:
        low = name.lower()
        return next((v for k, v in self.headers if k.lower() == low), None)


_CHROME_HEADERS = (
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"),
    ("Accept-Encoding", "gzip, deflate, br, zstd"),
    ("Accept-Language", "es-ES,es;q=0.9"),
    ("Sec-Ch-Ua", '"Chromium";v="CURRENT", "Google Chrome";v="CURRENT"'),
    ("Sec-Ch-Ua-Mobile", "?0"),
    ("Sec-Ch-Ua-Platform", '"Windows"'),
    ("Sec-Fetch-Site", "none"),
    ("Sec-Fetch-Mode", "navigate"),
    ("Sec-Fetch-User", "?1"),
    ("Sec-Fetch-Dest", "document"),
    ("Upgrade-Insecure-Requests", "1"),
)
_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/CURRENT.0.0.0"
REAL_BROWSERS: tuple[Request, ...] = (
    Request("Chrome on Windows (HTTP/2)", f"{_WIN} Safari/537.36", headers=_CHROME_HEADERS),
    Request("Chrome on Windows (HTTP/3)", f"{_WIN} Safari/537.36", "HTTP/3", headers=_CHROME_HEADERS),
    Request("Chrome behind a corporate proxy (HTTP/1.1)", f"{_WIN} Safari/537.36", "HTTP/1.1", headers=_CHROME_HEADERS),
    Request(
        "Chrome in Chinese, behind a corporate proxy (HTTP/1.1)",
        f"{_WIN} Safari/537.36",
        "HTTP/1.1",
        headers=tuple((k, "zh-CN,zh;q=0.9,en;q=0.8" if k == "Accept-Language" else v) for k, v in _CHROME_HEADERS),
    ),
    # On plain HTTP a real Chrome sends no Fetch Metadata and no client hints: no rule may cut that.
    Request(
        "Chrome on plain HTTP",
        f"{_WIN} Safari/537.36",
        "HTTP/1.1",
        False,
        (("Accept-Language", "es-ES,es;q=0.9"), ("Accept-Encoding", "gzip, deflate")),
    ),
    Request(
        "Chrome in Chinese on plain HTTP",
        f"{_WIN} Safari/537.36",
        "HTTP/1.1",
        False,
        (("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"), ("Accept-Encoding", "gzip, deflate")),
    ),
    Request("Edge on Windows", f"{_WIN} Safari/537.36 Edg/CURRENT.0.0.0", headers=_CHROME_HEADERS),
    Request(
        "Chrome on Android",
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/CURRENT.0.0.0 Mobile "
        "Safari/537.36",
        headers=_CHROME_HEADERS,
    ),
    Request(
        "Chrome on a Mac",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/CURRENT.0.0.0 "
        "Safari/537.36",
        headers=_CHROME_HEADERS,
    ),
    Request(
        "Safari on an iPhone",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.1 Mobile/15E148 Safari/604.1",
        headers=(("Accept-Language", "es-ES,es;q=0.9"), ("Sec-Fetch-Mode", "navigate")),
    ),
    Request(
        "Firefox on Linux",
        "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
        headers=(("Accept-Language", "en-US,en;q=0.5"), ("Sec-Fetch-Mode", "navigate")),
    ),
)

# Search engines, AI crawlers and AI assistants, with the User-Agent they document. Sent over HTTP/1.1, without any
# browser header and with today's Chrome version: the worst case. None may be cut by any rule, ever.
_GV = "CURRENT.0.0.0"
GOOD_ROBOTS: tuple[tuple[str, str], ...] = (
    ("Googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"),
    (
        "Googlebot (desktop)",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        f" Chrome/{_GV} Safari/537.36",
    ),
    (
        "Googlebot (smartphone)",
        "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_GV} Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    ),
    (
        "Storebot-Google",
        "Mozilla/5.0 (X11; Linux x86_64; Storebot-Google/1.0) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_GV} Safari/537.36",
    ),
    (
        "Google-InspectionTool",
        "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_GV} Mobile Safari/537.36 (compatible; Google-InspectionTool/1.0;)",
    ),
    (
        "AdsBot-Google-Mobile",
        "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_GV} Mobile Safari/537.36 (compatible; AdsBot-Google-Mobile; +http://www.google.com/mobile/adsbot.html)",
    ),
    (
        "GoogleOther",
        f"Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GoogleOther) Chrome/{_GV} Safari/537.36",
    ),
    (
        "Google-Read-Aloud",
        f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_GV} Safari/537.36 "
        "(compatible; Google-Read-Aloud; +https://support.google.com/webmasters/answer/1061943)",
    ),
    (
        "Google-NotebookLM",
        f"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_GV} Safari/537.36 "
        "Google-NotebookLM",
    ),
    (
        "Chrome-Lighthouse (PageSpeed)",
        "Mozilla/5.0 (Linux; Android 11; moto g power (2022)) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{_GV} Mobile Safari/537.36 Chrome-Lighthouse",
    ),
    (
        "bingbot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)"
        f" Chrome/{_GV} Safari/537.36",
    ),
    (
        "MicrosoftPreview",
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{_GV} Safari/537.36"
        f" Edg/{_GV} MicrosoftPreview/2.0 +https://aka.ms/MicrosoftPreview",
    ),
    (
        "GPTBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
    ),
    (
        "OAI-SearchBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    ),
    (
        "ChatGPT-User",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
    ),
    (
        "ClaudeBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    ),
    (
        "Claude-User",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)",
    ),
    (
        "Claude-SearchBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; "
        "+searchbot@anthropic.com)",
    ),
    (
        "PerplexityBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    ),
    (
        "Perplexity-User",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)",
    ),
    (
        "Applebot",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 "
        "Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
    ),
    (
        "MistralAI-User",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; MistralAI-User/1.0; +https://docs.mistral.ai/robots)",
    ),
    (
        "DuckAssistBot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; DuckAssistBot/1.2; +http://duckduckgo.com/duckassistbot.html)",
    ),
    ("meta-externalagent", "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)"),
    ("facebookexternalhit", "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"),
    (
        "Amazonbot",
        "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amazonbot/0.1; "
        f"+https://developer.amazon.com/support/amazonbot) Chrome/{_GV} Safari/537.36",
    ),
    ("CCBot", "CCBot/2.0 (https://commoncrawl.org/faq/)"),
    ("YandexBot", "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)"),
    ("DuckDuckBot", "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)"),
)


def good_robot_requests() -> list[Request]:
    """Every good robot, sent with every condition a rule can ask for (the worst case)."""
    return [
        Request(f"{label}", ua, protocol, https, headers)
        for label, ua in GOOD_ROBOTS
        for protocol, https, headers in (
            ("HTTP/1.1", True, (("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),)),
            ("HTTP/1.1", False, ()),
            ("HTTP/2", True, ()),
        )
    ]


# ---- regular expressions --------------------------------------------------------------------------------------------
def _digits_range(lo: str, hi: str) -> list[str]:
    """Patterns matching every number string between lo and hi, both with the same number of digits."""
    if lo == hi:
        return [lo]
    if len(lo) == 1:
        return [f"[{lo}-{hi}]" if lo != hi else lo]
    if lo[0] == hi[0]:
        return [lo[0] + p for p in _digits_range(lo[1:], hi[1:])]
    out: list[str] = []
    rest = len(lo) - 1
    if lo[1:] == "0" * rest:
        first = lo[0]
    else:
        out += [lo[0] + p for p in _digits_range(lo[1:], "9" * rest)]
        first = str(int(lo[0]) + 1)
    last = hi[0] if hi[1:] == "9" * rest else str(int(hi[0]) - 1)
    if int(first) <= int(last):
        digit = first if first == last else f"[{first}-{last}]"
        out.append(digit + "[0-9]" * rest if rest else digit)
    if hi[1:] != "9" * rest:
        out += [hi[0] + p for p in _digits_range("0" * rest, hi[1:])]
    return out


def number_regex(lo: int, hi: int | None = None) -> str:
    """Alternation matching the decimal numbers lo..hi (hi None: up to 9999). Without leading zeros or anchors."""
    hi = 9999 if hi is None else hi
    if lo > hi:
        raise ValueError("empty range")
    parts: list[str] = []
    for width in range(len(str(lo)), len(str(hi)) + 1):
        a = max(lo, 10 ** (width - 1) if width > 1 else 0)
        b = min(hi, 10**width - 1)
        if a <= b:
            parts += _digits_range(str(a), str(b))
    return "(" + "|".join(parts) + ")"


def declared_regex(extra: tuple[str, ...] = ()) -> str:
    words = list(dict.fromkeys(w.lower() for w in (*DECLARED, *AI_AGENTS, *extra)))
    words = [w for w in words if not any(o != w and o in w for o in words)]  # "gptbot" is covered by "bot"
    return "(" + "|".join(re.escape(w).replace("\\-", "-") for w in words) + ")"


def referer_regex(domains: tuple[str, ...]) -> str:
    """Referer containing one of the domains as a host: also inside a redirect such as /url?q=http://domain/."""
    alt = "|".join(re.escape(d).replace("\\-", "-") for d in domains)
    return f"(^|[/.@=]|%2[Ff])({alt})($|[/:?#&%])"


# ---- Chrome versions, from Google's own version history ------------------------------------------------------------
VERSION_HISTORY = "https://versionhistory.googleapis.com/v1/chrome/platforms/win/channels/{channel}/versions?pageSize=1"


def _major(payload: Any) -> int:
    try:
        version = payload["versions"][0]["version"]
        return int(str(version).split(".")[0])
    except (KeyError, IndexError, TypeError, ValueError):
        raise ranges.FetchError("Chrome version history: unexpected answer") from None


def chrome_versions(*, ttl: float = 24 * 3600, download: Callable[[str], Any] | None = None) -> dict[str, int]:
    """{'stable': N, 'canary': M} for Chrome on Windows, read from versionhistory.googleapis.com (cached a day)."""
    folder = ranges.cache_dir()
    path = folder / "chrome-versions.json" if folder else None
    if path and download is None:
        try:
            if time.time() - path.stat().st_mtime < ttl:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(cached.get("stable"), int) and isinstance(cached.get("canary"), int):
                    return cached
        except (OSError, ValueError, AttributeError):
            pass
    get = download or _download
    try:
        found = {channel: _major(get(VERSION_HISTORY.format(channel=channel))) for channel in ("stable", "canary")}
    except ranges.FetchError:
        if path and path.exists():  # an older copy is better than nothing
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        raise
    if path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(found), encoding="utf-8")
        except OSError:
            pass
    return found


def _download(url: str, timeout: float = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": ranges.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise ranges.FetchError(f"Chrome version history: {e}") from None


# ---- resolved rules: what the renderers and the Python matcher use -------------------------------------------------
@dataclass(frozen=True)
class Rule:
    name: str
    ua_regex: str = ""  # case-sensitive; empty = any User-Agent
    protocols: tuple[str, ...] = ()
    https: bool = False
    headers: tuple[tuple[str, str], ...] = ()
    missing: tuple[str, ...] = ()
    referer_regex: str = ""  # case-insensitive; empty = any referer
    referer_domains: tuple[str, ...] = ()


MOZILLA = r"^Mozilla/5\.0 \("


def chrome_ua(lo: int = 0, hi: int | None = None) -> str:
    if lo <= 0 and hi is None:
        return MOZILLA + r".*Chrome/[0-9]"
    return MOZILLA + r".*Chrome/" + number_regex(max(lo, 0), hi) + r"\."


def resolve(fp: Fingerprint, versions: Mapping[str, int] | None) -> Rule:
    if fp.browser == "any":
        ua = MOZILLA
    else:
        hi = None
        if fp.chrome_behind:
            if not versions:
                raise ranges.FetchError("Chrome version history was not read")
            hi = versions["stable"] - fp.chrome_behind - 1
        ua = chrome_ua(fp.chrome_min, hi)
    return Rule(fp.name, ua, fp.protocols, fp.https, fp.headers, fp.missing)


def future_rule(versions: Mapping[str, int], margin: int) -> Rule:
    return Rule("future-chrome", chrome_ua(versions["canary"] + margin + 1))


def referer_rule(domains: tuple[str, ...]) -> Rule:
    return Rule("referer-spam", referer_regex=referer_regex(domains), referer_domains=domains)


def matches(
    rule: Rule,
    *,
    user_agent: str,
    protocol: str | None,
    https: bool | None,
    headers: Mapping[str, str],
    declared: str,
) -> bool:
    """Does this request meet every condition of the rule (guards included)? Header names are case-insensitive.

    `protocol` or `https` None means "not known" (an access log without them): a rule that needs them does not match.
    """
    h = {k.lower(): v for k, v in headers.items()}
    if re.search(declared, user_agent, re.I) or h.get(SIGNED_HEADER.lower()):
        return False
    if rule.ua_regex and not re.search(rule.ua_regex, user_agent):
        return False
    if rule.protocols and (protocol is None or _canon(protocol) not in rule.protocols):
        return False
    if rule.https and not https:
        return False
    for name, value in rule.headers:
        if h.get(name.lower()) != value:
            return False
    for name in rule.missing:
        if h.get(name.lower()):
            return False
    return not (rule.referer_regex and not re.search(rule.referer_regex, h.get("referer", ""), re.I))


def _canon(protocol: str) -> str:
    p = protocol.upper()
    return {"HTTP/2.0": "HTTP/2", "HTTP/3.0": "HTTP/3"}.get(p, p)


def sample(req: Request, version: int) -> tuple[str, dict[str, str]]:
    """User-Agent and headers of a sample request with CURRENT replaced by a Chrome version."""
    ua = req.user_agent.replace("CURRENT", str(version))
    return ua, {k: v.replace("CURRENT", str(version)) for k, v in req.headers}


def worst_case(rule: Rule, user_agent: str, versions: Mapping[str, int]) -> Request:
    """The request of this robot that meets every condition of the rule except its name: the hardest case."""
    candidates = [versions["stable"], versions["canary"] + 50, 100, 60]
    ua = user_agent.replace("CURRENT", str(versions["stable"]))
    for v in candidates:
        attempt = user_agent.replace("CURRENT", str(v))
        if not rule.ua_regex or re.search(rule.ua_regex, attempt):
            ua = attempt
            break
    headers = list(rule.headers)
    if rule.referer_domains:
        headers.append(("Referer", f"http://{rule.referer_domains[0]}/"))
    return Request("", ua, rule.protocols[0] if rule.protocols else "HTTP/1.1", True, tuple(headers))


def check_robots(rules: tuple[Rule, ...], declared: str, versions: Mapping[str, int]) -> list[dict[str, Any]]:
    """For each search engine, AI crawler and assistant: could any fingerprint rule cut it? Worst case per rule."""
    rows = []
    for label, ua in GOOD_ROBOTS:
        hits = []
        for rule in rules:
            req = worst_case(rule, ua, versions)
            if matches(
                rule,
                user_agent=req.user_agent,
                protocol=req.protocol,
                https=req.https,
                headers=dict(req.headers),
                declared=declared,
            ):
                hits.append(rule.name)
        rows.append(
            {
                "robot": label,
                "status": "cut" if hits else "ok",
                "note": f"cut by {', '.join(hits)}"
                if hits
                else f"passes by name, even sending everything the {len(rules)} rules look for",
            }
        )
    return rows

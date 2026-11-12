"""Built-in lists: cloud networks and robot user agents.

Every preset has a name, a short description and its members. Presets marked ``default=True`` are used when the
configuration does not say otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    members: tuple[str, ...]
    default: bool = False


# Autonomous systems (ASN) whose announced prefixes are blocked. Holder names checked on RIPEstat (as-overview).
NETWORK_PRESETS: dict[str, Preset] = {
    p.name: p
    for p in [
        Preset(
            "tencent-cloud",
            "Tencent Cloud, international (AS132203) and China (AS45090). Source of most Chrome-impersonating bots.",
            ("AS132203", "AS45090"),
            default=True,
        ),
        Preset("alibaba-cloud", "Alibaba Cloud (AS45102).", ("AS45102",)),
        Preset("huawei-cloud", "Huawei Cloud (AS136907).", ("AS136907",)),
    ]
}

# User-agent fragments. Matched case-insensitively anywhere in the User-Agent header.
ROBOT_PRESETS: dict[str, Preset] = {
    p.name: p
    for p in [
        Preset(
            "aggressive-crawlers",
            "Crawlers that bring no visitors and hammer the site.",
            ("Bytespider", "MJ12bot", "DotBot", "BLEXBot", "PetalBot", "MegaIndex", "SeekportBot"),
            default=True,
        ),
        Preset(
            "scraping-libraries",
            "HTTP libraries used by scrapers. curl and wget are NOT included: you need them to test your own site.",
            ("python-requests", "python-urllib", "Go-http-client", "Scrapy", "aiohttp", "libwww-perl"),
            default=True,
        ),
        Preset(
            "vulnerability-scanners",
            "Port and vulnerability scanners.",
            ("zgrab", "masscan", "Nuclei", "sqlmap", "Nikto"),
            default=True,
        ),
        Preset(
            "seo-tools",
            "Commercial SEO tool crawlers. Opt-in: blocking them only hides your site from those tools.",
            ("AhrefsBot", "SemrushBot", "DataForSeoBot", "serpstatbot", "Barkrowler"),
        ),
        Preset(
            "ai-training",
            "AI crawlers. Opt-in: blocking them removes your site from AI answers (GEO).",
            ("GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "meta-externalagent", "Amazonbot", "cohere-ai"),
        ),
    ]
}

# Real user agents that must never be blocked. Used as a safety net when validating a configuration.
PROTECTED_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; Google-InspectionTool/1.0)",
    "Storebot-Google/1.0",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)",
    "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "Mozilla/5.0 (compatible; Applebot/0.1; +http://www.apple.com/go/applebot)",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "Twitterbot/1.0",
    "curl/8.7.1",
    "Wget/1.24.5",
    "Stripe/1.0 (+https://stripe.com/docs/webhooks)",
)


def default_names(presets: dict[str, Preset]) -> tuple[str, ...]:
    return tuple(p.name for p in presets.values() if p.default)

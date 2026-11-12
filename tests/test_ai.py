from __future__ import annotations

import ipaddress
import json

import pytest

from n_antibot import ai, generate, ranges
from n_antibot.cli import main
from n_antibot.config import Config, ConfigError, from_dict

PUBLISHED = {
    "https://openai.com/gptbot.json": {"prefixes": [{"ipv4Prefix": "3.5.5.0/28"}, {"ipv4Prefix": "20.171.206.0/24"}]},
    "https://www.perplexity.com/perplexitybot.json": {"prefixes": [{"ipv4Prefix": "3.90.62.45/32"}]},
    "https://developers.google.com/static/search/apis/ipranges/googlebot.json": {
        "prefixes": [{"ipv4Prefix": "66.249.64.0/27"}, {"ipv6Prefix": "2001:4860:4801:10::/64"}]
    },
}


def download(url):
    if url not in PUBLISHED:
        raise OSError("not in this test")
    return PUBLISHED[url]


@pytest.fixture
def published(monkeypatch):
    """Real protection code, with three operators answering and the rest failing."""
    monkeypatch.setattr("n_antibot.ai.protected_ranges", lambda download_=None: _real(download))
    return PUBLISHED


def _real(dl):
    found, failed = {}, []
    for crawler in ai.CRAWLERS:
        if crawler.url is None:
            continue
        try:
            found[crawler.key] = ai.fetch(crawler, download=dl)
        except ranges.FetchError as e:
            failed.append(str(e))
    return found, failed


def aws_fetch(asns, **_):
    return ["3.0.0.0/9"] if "AS16509" in asns else []


def test_every_crawler_entry_is_well_formed():
    keys = [c.key for c in ai.CRAWLERS]
    assert len(keys) == len(set(keys)) and len(keys) >= 20
    for c in ai.CRAWLERS:
        assert c.operator and c.agent and c.purpose
        assert c.url is None or c.url.startswith("https://")
    assert sum(c.url is not None for c in ai.CRAWLERS) == 15


def test_default_configuration_cuts_no_ai_crawler_or_search_engine():
    cfg = Config().validate()
    assert cfg.ai_protect is True and ai.blocked_agents(cfg) == []
    for c in ai.CRAWLERS:
        for ua in (f"Mozilla/5.0 (compatible; {c.agent}/1.2; +https://example.org/bot)", f"{c.agent}/2.0"):
            assert cfg.blocks_agent(ua) is None, ua


def test_parse_accepts_the_published_format_and_rejects_anything_else():
    assert ai.parse(PUBLISHED["https://openai.com/gptbot.json"]) == ["3.5.5.0/28", "20.171.206.0/24"]
    assert ai.parse({"prefixes": [{"ipv6Prefix": "2001:db8::/32"}]}) == ["2001:db8::/32"]
    for bad in [{}, {"prefixes": []}, {"prefixes": [{"x": 1}]}, {"prefixes": [{"ipv4Prefix": "nope"}]}, [], None]:
        with pytest.raises(ranges.FetchError):
            ai.parse(bad)


def test_published_addresses_are_carved_out_of_a_blocked_cloud(published):
    cfg = from_dict({"networks": {"presets": ["aws"]}, "output": {"format": "json"}})
    warnings = []
    from n_antibot.core import blocklist

    bl = blocklist(cfg, fetch=aws_fetch, warn=warnings.append)
    nets = [ipaddress.ip_network(n) for n in bl.v4]
    inside = lambda ip: any(ipaddress.ip_address(ip) in n for n in nets)  # noqa: E731
    assert inside("3.9.9.9")  # the rest of the cloud is still cut
    assert not inside("3.5.5.1") and not inside("3.90.62.45")  # GPTBot and PerplexityBot live in it and stay open
    assert len(warnings) == 12 and "could not download" in warnings[0]  # the 12 operators that failed are reported
    off = blocklist(from_dict({"networks": {"presets": ["aws"]}, "ai": {"protect": False}}), fetch=aws_fetch)
    assert off.v4 == ["3.0.0.0/9"]


def test_ad_click_rule_keeps_ai_addresses_open_too(published):
    cfg = from_dict({"ads": {"networks": ["aws"], "cut": True}, "output": {"format": "json"}})
    data = json.loads(generate(cfg, fetch=lambda asns, **_: ["3.0.0.0/9"] if "AS16509" in asns else ["43.172.0.0/16"]))
    ads = [ipaddress.ip_network(n) for n in data["ad_clicks"]["ipv4"]]
    assert not any(ipaddress.ip_address("3.5.5.1") in n for n in ads)
    assert any(ipaddress.ip_address("3.9.9.9") in n for n in ads)


def test_check_reports_each_crawler(published):
    found, failed = ai.protected_ranges()
    rows = {
        r["crawler"]: r for r in ai.check(from_dict({"networks": {"presets": ["aws"]}}), ["3.0.0.0/9"], found, failed)
    }
    assert rows["GPTBot"]["status"] == "ok" and "kept open for it" in rows["GPTBot"]["note"]
    assert rows["GPTBot"]["ranges_in_blocked_networks"] == 1 and rows["GPTBot"]["published_ranges"] == 2
    assert rows["Googlebot"]["status"] == "ok" and "none of its 2 ranges" in rows["Googlebot"]["note"]
    assert rows["ClaudeBot"]["status"] == "ok" and "passes by name" in rows["ClaudeBot"]["note"]
    assert rows["bingbot"]["status"] == "unknown"
    unprotected = from_dict(
        {"networks": {"presets": ["aws"]}, "robots": {"presets": ["ai-training"]}, "ai": {"protect": False}}
    )
    rows = {r["crawler"]: r for r in ai.check(unprotected, ["3.0.0.0/9"], found, failed)}
    assert rows["GPTBot"]["status"] == "cut" and "by name" in rows["GPTBot"]["note"]
    assert rows["PerplexityBot"]["status"] == "cut" and "1 of its 1 ranges" in rows["PerplexityBot"]["note"]


def test_cloudflare_keeps_verified_bots(published):
    expr = generate(from_dict({"output": {"format": "cloudflare"}}), fetch=aws_fetch).rstrip("\n").splitlines()[-1]
    assert ") and not cf.client.bot" in expr
    off = generate(from_dict({"output": {"format": "cloudflare"}, "ai": {"protect": False}}), fetch=aws_fetch)
    assert "cf.client.bot" not in off


def test_cache_of_published_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("N_ANTIBOT_CACHE", str(tmp_path))
    gpt = ai.CRAWLERS[0]
    calls = []

    def once(url):
        calls.append(url)
        if len(calls) > 1:
            raise OSError("down")
        return PUBLISHED[url]

    assert ai.fetch(gpt, download=once) == ["3.5.5.0/28", "20.171.206.0/24"]
    assert ai.fetch(gpt, download=once) == ["3.5.5.0/28", "20.171.206.0/24"] and len(calls) == 1
    assert ai.fetch(gpt, ttl=0, download=once) == ["3.5.5.0/28", "20.171.206.0/24"] and len(calls) == 2  # stale copy
    with pytest.raises(ranges.FetchError, match="OpenAI OAI-SearchBot"):
        ai.fetch(ai.CRAWLERS[1], ttl=0, download=once)


def test_cli_ai_check(published, monkeypatch, capsys):
    monkeypatch.setattr("n_antibot.ranges.fetch_asn", lambda asn, **_: ["3.0.0.0/9"] if asn == "AS16509" else [])
    assert main(["ai-check"]) == 0
    out = capsys.readouterr().out
    assert "GPTBot" in out and "ok" in out and "cut" not in out.replace("cut off", "")
    assert main(["ai-check", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert {r["status"] for r in rows} <= {"ok", "unknown"}


def test_cli_ai_check_fails_when_something_is_cut(published, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("n_antibot.ranges.fetch_asn", lambda asn, **_: ["3.0.0.0/9"] if asn == "AS16509" else [])
    cfg = tmp_path / "c.toml"
    cfg.write_text('[networks]\npresets = ["aws"]\n[ai]\nprotect = false\n')
    assert main(["ai-check", "-c", str(cfg)]) == 1
    assert "CUT" in capsys.readouterr().out
    with pytest.raises(ConfigError):
        from_dict({"robots": {"block": ["GPTBot"]}})

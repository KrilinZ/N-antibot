import ipaddress
import json
import re

import pytest

from n_antibot import Config, ConfigError, FetchError, generate
from n_antibot.cli import main
from n_antibot.config import from_dict
from n_antibot.presets import NETWORK_PRESETS, PROTECTED_AGENTS, ROBOT_PRESETS
from n_antibot.ranges import build, collapse, fetch_asn, parse_ripestat, subtract
from n_antibot.render import strip_header

FAKE = {"AS132203": ["43.172.0.0/24", "43.172.1.0/24", "2402:4e00::/32"], "AS45090": ["43.173.0.0/16"]}


def fake_fetch(asns, **_):
    return [p for a in asns for p in FAKE.get(a, ["198.51.100.0/24"])]


def gen(cfg=None, **over):
    cfg = cfg or Config()
    return generate(from_dict(over) if over else cfg.validate(), fetch=fake_fetch, today="2026-11-12")


# ---------------------------------------------------------------- ranges
def test_collapse_merges_and_splits_families():
    v4, v6 = collapse(["43.172.0.0/24", "43.172.1.0/24", "43.172.0.0/25", "2402:4e00::/32"])
    assert [str(n) for n in v4] == ["43.172.0.0/23"]
    assert [str(n) for n in v6] == ["2402:4e00::/32"]


def test_subtract_punches_a_hole():
    out = subtract([ipaddress.ip_network("10.0.0.0/24")], [ipaddress.ip_network("10.0.0.7/32")])
    assert ipaddress.ip_address("10.0.0.7") not in ipaddress.ip_network("10.0.0.0/30")  # sanity
    assert not any(ipaddress.ip_address("10.0.0.7") in n for n in out)
    assert any(ipaddress.ip_address("10.0.0.8") in n for n in out)
    assert sum(n.num_addresses for n in out) == 255


def test_subtract_whole_range_and_other_family():
    assert subtract([ipaddress.ip_network("10.0.0.0/24")], [ipaddress.ip_network("10.0.0.0/16")]) == []
    six = [ipaddress.ip_network("2402:4e00::/32")]
    assert subtract(six, [ipaddress.ip_network("10.0.0.0/8")]) == six


def test_build_adds_manual_blocks_and_allows():
    v4, v6 = build(["43.172.0.0/16"], ["203.0.113.0/24"], ["43.172.10.1/32"])
    assert "203.0.113.0/24" in v4
    assert not any(ipaddress.ip_address("43.172.10.1") in ipaddress.ip_network(n) for n in v4)
    assert v6 == []


def test_parse_ripestat_validates_shape():
    assert parse_ripestat("AS1", {"data": {"prefixes": [{"prefix": "1.2.3.0/24"}]}}) == ["1.2.3.0/24"]
    for bad in [{}, {"data": {}}, {"data": {"prefixes": []}}, {"data": {"prefixes": [{"prefix": "nope"}]}}, None]:
        with pytest.raises(FetchError):
            parse_ripestat("AS1", bad)


def test_fetch_retries_then_fails_without_partial_result():
    calls, sleeps = [], []

    def flaky(url, timeout):
        calls.append(url)
        raise TimeoutError("slow")

    with pytest.raises(FetchError, match="AS9"):
        fetch_asn("AS9", get_json=flaky, sleep=sleeps.append, attempts=3)
    assert len(calls) == 3 and len(sleeps) == 2 and sleeps[1] > sleeps[0] >= 1
    assert "sourceapp=n-antibot" in calls[0]


def test_fetch_recovers_after_one_failure():
    answers = [OSError("reset"), {"data": {"prefixes": [{"prefix": "1.2.3.0/24"}]}}]

    def once(url, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert fetch_asn("AS1", get_json=once, sleep=lambda s: None) == ["1.2.3.0/24"]


# ---------------------------------------------------------------- config
def test_defaults_are_valid_and_cover_the_original_brake():
    cfg = Config().validate()
    assert cfg.all_asns() == ("AS132203", "AS45090")
    assert len(cfg.agents()) == 18
    assert "/.well-known/*" in cfg.exclude_paths


@pytest.mark.parametrize(
    "data, msg",
    [
        ({"netwroks": {}}, "unknown section"),
        ({"robots": {"blok": []}}, "unknown key robots.blok"),
        ({"robots": {"presets": ["nope"]}}, "unknown preset"),
        ({"robots": {"block": ["bad|regex"]}}, "letters, digits"),
        ({"robots": {"block": ["ab"]}}, "3-64"),
        ({"robots": {"block": "Bytespider"}}, "list of strings"),
        ({"robots": {"block": ["Mozilla"]}}, "real browser"),
        ({"robots": {"block": ["Googlebot"]}}, "real browser"),
        ({"robots": {"block": ["curl"]}}, "real browser"),
        ({"networks": {"asns": ["132203"]}}, "ASN"),
        ({"networks": {"block": ["300.1.1.1/8"]}}, "not an IP range"),
        ({"paths": {"exclude": ["api/*"]}}, "paths.exclude"),
        ({"paths": {"exclude": ["/a/*/b"]}}, "paths.exclude"),
        ({"output": {"format": "apache"}}, "output.format"),
        ({"caddy": {"prefix": "bad-name"}}, "caddy.prefix"),
        ({"caddy": {"ip_matcher": "x"}}, "ip_matcher"),
        ({"networks": {"presets": []}, "robots": {"presets": []}}, "nothing to block"),
    ],
)
def test_invalid_configs_are_rejected(data, msg):
    with pytest.raises(ConfigError, match=msg):
        from_dict(data)


def test_allow_removes_agents_case_insensitively():
    cfg = from_dict({"robots": {"allow": ["AIOHTTP"]}})
    assert "aiohttp" not in cfg.agents()
    assert cfg.blocks_agent("Python/3.12 aiohttp/3.9") is None


def test_presets_never_hit_protected_agents():
    for preset in ROBOT_PRESETS.values():
        for frag in preset.members:
            for ua in PROTECTED_AGENTS:
                assert frag.lower() not in ua.lower(), (frag, ua)


def test_every_preset_is_individually_valid():
    for name in NETWORK_PRESETS:
        from_dict({"networks": {"presets": [name]}})
    for name in ROBOT_PRESETS:
        from_dict({"robots": {"presets": [name]}})


def test_ai_crawlers_are_opt_in_for_geo():
    cfg = Config().validate()
    for ua in ["Mozilla/5.0 (compatible; GPTBot/1.2)", "ClaudeBot/1.0", "PerplexityBot/1.0", "AhrefsBot/7.0"]:
        assert cfg.blocks_agent(ua) is None, ua
    assert from_dict({"robots": {"presets": ["ai-training"]}}).blocks_agent("ClaudeBot/1.0") == "ClaudeBot"


# ---------------------------------------------------------------- renderers
def test_caddy_snippet_shape():
    text = gen()
    assert text.count("{") == text.count("}")
    assert text.count("not path /.well-known/*") == 2
    assert "rewrite @nAntibotNet /__n_antibot_blocked" in text
    assert "rewrite @nAntibotAgent /__n_antibot_blocked" in text
    assert re.search(r"handle /__n_antibot_blocked \{\n\tabort\n\}", text)
    assert '"(?i)(Bytespider|' in text
    assert "remote_ip 43.172.0.0/23 43.173.0.0/16 2402:4e00::/32" in text


def test_caddy_custom_names_and_client_ip_and_no_excludes():
    text = gen(
        caddy={"prefix": "shopBots", "block_path": "/__shop_blocked", "ip_matcher": "client_ip"},
        paths={"exclude": []},
    )
    assert "@shopBotsNet {" in text and "handle /__shop_blocked {" in text
    assert "\tclient_ip " in text and "not path" not in text


def test_caddy_agents_only():
    text = gen(networks={"presets": []})
    assert "@nAntibotNet" not in text and "rewrite @nAntibotAgent" in text


def test_nginx_include_shape():
    text = gen(output={"format": "nginx"}, paths={"exclude": ["/api/*", "/health", "*.xml"]})
    assert "geo $n_antibot_net {" in text and "\t43.172.0.0/23 1;" in text
    assert '"~*(Bytespider|' in text
    assert '"~^/api/" 1;' in text and '"/health" 1;' in text and '"~\\.xml$" 1;' in text
    assert '"100" 1;' in text and '"110" 1;' in text and '"101"' not in text
    assert text.count("{") == text.count("}")


def test_json_output():
    data = json.loads(gen(output={"format": "json"}))
    assert data["ipv4"] == ["43.172.0.0/23", "43.173.0.0/16"]
    assert data["ipv6"] == ["2402:4e00::/32"]
    assert "Bytespider" in data["user_agents"]
    assert re.search(data["user_agent_regex"].replace("(?i)", ""), "bytespider", re.I)


def test_strip_header_ignores_only_the_date():
    a = gen()
    b = a.replace("2026-11-12", "2030-01-01")
    assert strip_header(a) == strip_header(b)
    assert strip_header(a) != strip_header(a.replace("43.173.0.0/16", "43.174.0.0/16"))


# ---------------------------------------------------------------- CLI
def test_cli_init_and_config_roundtrip(tmp_path, capsys):
    cfgfile = tmp_path / "n-antibot.toml"
    assert main(["init", "-o", str(cfgfile)]) == 0
    assert main(["init", "-o", str(cfgfile)]) == 1  # never overwrites
    assert main(["test-agent", "-c", str(cfgfile), "python-requests/2.32"]) == 0
    assert main(["test-agent", "-c", str(cfgfile), "Mozilla/5.0 (compatible; Googlebot/2.1)"]) == 2
    out = capsys.readouterr().out
    assert "BLOCKED by 'python-requests'" in out and "allowed" in out


def test_cli_reports_config_errors(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('[robots]\nblock = ["Mozilla"]\n')
    assert main(["test-agent", "-c", str(bad), "x"]) == 3
    assert "real browser" in capsys.readouterr().err
    bad.write_text("not = = toml")
    assert main(["test-agent", "-c", str(bad), "x"]) == 3


def test_cli_generate_and_check(tmp_path, monkeypatch, capsys):
    import n_antibot.cli as cli

    monkeypatch.setattr(cli, "blocklist", _bl)
    out = tmp_path / "n-antibot.caddy"
    assert main(["generate", "-o", str(out)]) == 0
    assert "43.173.0.0/16" in out.read_text()
    assert main(["check", "-o", str(out)]) == 0
    out.write_text(out.read_text().replace("43.173.0.0/16", "1.1.1.0/24"))
    assert main(["check", "-o", str(out)]) == 1
    assert main(["test-ip", "43.173.5.5"]) == 0
    assert main(["test-ip", "8.8.8.8"]) == 2


def test_cli_fetch_failure_writes_nothing(tmp_path, monkeypatch, capsys):
    import n_antibot.cli as cli

    def boom(cfg):
        raise FetchError("RIPEstat AS132203: timeout")

    monkeypatch.setattr(cli, "blocklist", boom)
    out = tmp_path / "keep.caddy"
    out.write_text("previous")
    assert main(["generate", "-o", str(out)]) == 4
    assert out.read_text() == "previous"
    assert "Nothing was written" in capsys.readouterr().err


def _bl(cfg):
    from n_antibot.core import blocklist

    return blocklist(cfg, fetch=fake_fetch, today="2026-11-12")

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
        ({"output": {"format": "iis"}}, "output.format"),
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


# ---------------------------------------------------------------- apache, nftables, cloudflare
def test_apache_rules_shape():
    text = gen(output={"format": "apache"}, paths={"exclude": ["/api/*", "/health", "*.xml"]})
    lines = text.splitlines()
    assert lines[3] == "RewriteEngine On"
    assert 'RewriteCond %{REQUEST_URI} "!^/api/"' in text
    assert 'RewriteCond %{REQUEST_URI} "!^/health$"' in text
    assert 'RewriteCond %{REQUEST_URI} "!\\.xml$"' in text
    assert '"(Bytespider|' in text and "[NC,OR]" in text
    assert "-R '43.172.0.0/23' || -R '43.173.0.0/16' || -R '2402:4e00::/32'\"" in text
    conds = [x for x in lines if x.startswith("RewriteCond") and "REQUEST_URI" not in x]
    assert all(c.endswith("OR]") for c in conds[:-1]) and not conds[-1].endswith("]")
    assert lines[-1] == "RewriteRule ^ - [F,L]"


def test_apache_agents_only_and_networks_only():
    agents = gen(output={"format": "apache"}, networks={"presets": []})
    assert agents.splitlines()[-2].endswith('" [NC]') and "expr" not in agents
    nets = gen(output={"format": "apache"}, robots={"presets": []})
    assert "HTTP_USER_AGENT" not in nets and "OR]" not in nets


def test_nftables_ruleset_shape():
    text = gen(output={"format": "nftables"}, nftables={"ports": [80, 443, 8443]})
    assert "add table inet n_antibot\ndelete table inet n_antibot\ntable inet n_antibot {" in text
    assert "type ipv4_addr" in text and "type ipv6_addr" in text and "flags interval" in text
    assert "43.172.0.0/23, 43.173.0.0/16," in text
    assert "tcp dport { 80, 443, 8443 } ip saddr @v4 drop" in text
    assert "udp dport { 80, 443, 8443 } ip6 saddr @v6 drop" in text
    assert "hook prerouting" in text and "robots" in text.splitlines()[2] and " 0 robots" in text
    assert text.count("{") == text.count("}")


def test_nftables_without_ipv6_and_without_networks():
    text = gen(output={"format": "nftables"}, networks={"presets": [], "block": ["203.0.113.0/24"]})
    assert "set v6" not in text and "@v6" not in text and "203.0.113.0/24," in text
    with pytest.raises(ConfigError, match="only blocks networks"):
        from_dict({"output": {"format": "nftables"}, "networks": {"presets": []}})
    with pytest.raises(ConfigError, match=r"nftables\.ports"):
        from_dict({"nftables": {"ports": [0]}})
    with pytest.raises(ConfigError, match="list of integers"):
        from_dict({"nftables": {"ports": ["80"]}})


def test_cloudflare_expression():
    calls = []

    def spy(asns, **_):
        calls.append(asns)
        return []

    cfg = from_dict(
        {
            "output": {"format": "cloudflare"},
            "networks": {"block": ["203.0.113.0/24"], "allow": ["43.173.5.5/32"]},
            "paths": {"exclude": ["/api/*", "/health", "*.xml"]},
        }
    )
    expr = generate(cfg, fetch=spy, today="2026-11-12").rstrip("\n").splitlines()[-1]
    assert calls == []  # matched by ASN: nothing is downloaded
    assert expr.startswith("(ip.src.asnum in {132203 45090} or ip.src in {203.0.113.0/24} or ")
    assert 'lower(http.user_agent) contains "bytespider"' in expr
    assert ") and not ip.src in {43.173.5.5/32}" in expr
    assert 'and not starts_with(http.request.uri.path, "/api/")' in expr
    assert 'and not http.request.uri.path eq "/health"' in expr
    assert 'and not ends_with(http.request.uri.path, ".xml")' in expr
    assert expr.count("(") == expr.count(")")


def test_cloudflare_default_fits_the_expression_limit():
    expr = gen(output={"format": "cloudflare"}).rstrip("\n").splitlines()[-1]
    assert len(expr) < 4096


def test_every_example_case_is_a_valid_configuration():
    from pathlib import Path

    from n_antibot import load

    cases = sorted((Path(__file__).parent.parent / "examples" / "cases").glob("*.toml"))
    assert len(cases) >= 9
    for case in cases:
        cfg = load(case)
        assert generate(cfg, fetch=fake_fetch, today="2026-11-12"), case.name
    assert load(cases[0].parent / "wordpress.toml").format == "apache"
    assert load(cases[0].parent / "no-ai.toml").blocks_agent("PerplexityBot/1.0") == "PerplexityBot"
    assert load(cases[0].parent / "public-api.toml").blocks_agent("python-requests/2.32") is None


def test_every_output_is_plain_ascii():
    """No encoding surprises on any console or config parser (Windows consoles are not UTF-8 by default)."""
    for fmt in ("caddy", "nginx", "apache", "nftables", "cloudflare", "json"):
        assert gen(output={"format": fmt}).isascii(), fmt


def test_cli_messages_are_plain_ascii(tmp_path, monkeypatch, capsys):
    import n_antibot.cli as cli

    monkeypatch.setattr(cli, "blocklist", _bl)
    assert main(["generate", "-o", str(tmp_path / "x.caddy")]) == 0
    assert main(["presets"]) == 0
    assert main(["check", "-o", str(tmp_path / "x.caddy")]) == 0
    out = capsys.readouterr()
    assert (out.out + out.err).isascii()


# ---------------------------------------------------------------- [ads] cut = true
def ads_gen(fmt, **ads):
    cfg = from_dict({"output": {"format": fmt}, "ads": {"networks": ["aws", "hetzner"], "cut": True, **ads}})
    calls = []

    def fetch(asns, **_):
        calls.append(tuple(asns))
        return {
            "AS132203": ["43.172.0.0/16"],
            "AS16509": ["3.0.0.0/9", "2600:1f00::/24"],
            "AS24940": ["5.9.0.0/16"],
        }.get(asns[0], ["198.51.100.0/24"]) + (["5.9.0.0/16"] if "AS24940" in asns and asns[0] != "AS24940" else [])

    return generate(cfg, fetch=fetch, today="2026-11-12"), calls


def test_ads_cut_is_off_by_default_and_leaves_every_output_unchanged():
    assert Config().ads_cut is False
    for fmt in ("caddy", "nginx", "apache", "cloudflare"):
        text = gen(output={"format": fmt})
        assert "gclid" not in text and "AdClick" not in text and "adnet" not in text, fmt
    assert json.loads(gen(output={"format": "json"}))["ad_clicks"]["cut"] is False


def test_ads_cut_rules_in_each_output():
    caddy, calls = ads_gen("caddy")
    assert calls[1] == ("AS16509", "AS14618", "AS24940")  # the ads networks, fetched apart from the blocked ones
    assert "@nAntibotAdClick {" in caddy and "rewrite @nAntibotAdClick /__n_antibot_blocked" in caddy
    assert (
        "expression {http.request.uri.query}.matches('(^|&)(gclid|gbraid|wbraid|msclkid|ttclid|twclid|li_fat_id)=')"
        in caddy
    )
    block = caddy[caddy.index("@nAntibotAdClick") : caddy.index("rewrite @nAntibotNet")]
    assert "3.0.0.0/9" in block and "5.9.0.0/16" in block and "43.172.0.0/16" not in block
    assert caddy.count("{") == caddy.count("}")
    nginx, _ = ads_gen("nginx")
    assert "geo $n_antibot_adnet {" in nginx and "map $args $n_antibot_adclick {" in nginx
    assert (
        'map "$n_antibot_net$n_antibot_agent$n_antibot_excluded$n_antibot_adnet$n_antibot_adclick" $n_antibot_block {'
        in nginx
    )
    assert '"~^..011$" 1;' in nginx and '"100" 1;' not in nginx
    apache, _ = ads_gen("apache")
    assert apache.count("RewriteRule ^ - [F,L]") == 2
    assert 'RewriteCond %{QUERY_STRING} "(^|&)(gclid|gbraid|wbraid|msclkid|ttclid|twclid|li_fat_id)="' in apache
    cf, calls = ads_gen("cloudflare")
    assert calls == []  # by ASN: nothing is downloaded
    expr = cf.rstrip("\n").splitlines()[-1]
    assert '(ip.src.asnum in {16509 14618 24940} and (http.request.uri.query contains "gclid=" or ' in expr
    assert expr.count("(") == expr.count(")") and len(expr) < 4096
    data = json.loads(ads_gen("json")[0])["ad_clicks"]
    assert data["cut"] is True and "3.0.0.0/9" in data["ipv4"] and data["ipv6"] == ["2600:1f00::/24"]
    assert data["params"][0] == "gclid" and data["asns"] == ["AS16509", "AS14618", "AS24940"]


def test_ads_configuration_is_validated():
    assert (
        len(Config().ads_asn_list()) == 13 and "AS132203" not in Config().ads_asn_list()
    )  # blocked ones are not repeated
    assert from_dict({"networks": {"presets": ["aws"]}, "ads": {"networks": ["aws", "ovh"]}}).ads_asn_list() == (
        "AS16276",
    )
    for data, msg in [
        ({"ads": {"networks": ["nope"]}}, "ads.networks: unknown preset"),
        ({"ads": {"asns": ["16509"]}}, "ads.asns"),
        ({"ads": {"cut": "yes"}}, "must be true or false"),
        ({"ads": {"cut": True}, "output": {"format": "nftables"}}, "cannot see it"),
    ]:
        with pytest.raises(ConfigError, match=msg):
            from_dict(data)
    only_ads = from_dict({"networks": {"presets": []}, "robots": {"presets": []}, "ads": {"cut": True}})
    assert only_ads.ads_cut  # cutting only ad clicks is a valid configuration

from __future__ import annotations

import csv
import gzip
import io
import json
from datetime import datetime, timezone

from n_antibot import report
from n_antibot.cli import main
from n_antibot.config import from_dict

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
FAKE = {"AS132203": ["43.172.0.0/17", "43.173.0.0/16", "43.173.5.0/24", "2402:4e00::/32"], "AS45090": ["1.12.0.0/14"]}


def classifier(**over):
    return report.Classifier.from_config(from_dict(over), fetch_asn=lambda asn: FAKE.get(asn, []))


def combined(ip, when, uri, status=200, ua=CHROME):
    return f'{ip} - - [{when} +0100] "GET {uri} HTTP/2.0" {status} 512 "-" "{ua}"'


def caddy(ip, ts, uri, status=200, ua=CHROME, key="client_ip"):
    return json.dumps(
        {"ts": ts, "status": status, "request": {key: ip, "method": "GET", "uri": uri, "headers": {"User-Agent": [ua]}}}
    )


LOG = [
    combined("43.173.132.9", "12/Nov/2026:10:00:01", "/p/a/?gclid=NET-1", 444),
    combined("43.173.132.9", "12/Nov/2026:10:00:02", "/p/a/?gclid=NET-1", 444),  # same click, reloaded
    combined("8.8.8.8", "12/Nov/2026:10:01:00", "/?gclid=UA-1&utm_medium=cpc", 200, "python-requests/2.32"),
    combined("81.40.1.1", "12/Nov/2026:10:02:00", "/p/c/?gclid=OK-1"),
    combined("81.40.1.1", "12/Nov/2026:10:02:01", "/assets/app.css"),
    combined("81.40.1.2", "12/Nov/2026:10:03:00", "/?gclid=ONE-1"),
    combined("81.40.9.9", "12/Nov/2026:10:04:00", "/?gclid=REP-1"),
    combined("81.40.9.9", "12/Nov/2026:10:04:10", "/?gclid=REP-2"),
    combined("81.40.9.9", "12/Nov/2026:10:04:20", "/?gclid=REP-3"),
    combined("81.40.9.9", "12/Nov/2026:10:04:21", "/assets/app.js"),
    combined("81.40.1.3", "13/Nov/2026:09:00:00", "/?msclkid=MS-1"),
    combined("81.40.1.3", "13/Nov/2026:09:00:01", "/logo.png"),
    combined("81.40.1.4", "13/Nov/2026:09:10:00", "/offer/?utm_source=newsletter&utm_medium=email"),
    combined("81.40.1.5", "13/Nov/2026:09:20:00", "/offer/?utm_source=facebook&utm_medium=paid-social"),
    combined("81.40.1.5", "13/Nov/2026:09:20:01", "/logo.png"),
    "this is not a log line",
    "",
]


def test_parse_combined_and_caddy_lines():
    hit = report.parse_line(LOG[0])
    assert (hit.ip, hit.uri, hit.status) == ("43.173.132.9", "/p/a/?gclid=NET-1", 444)
    assert hit.ts == datetime(2026, 11, 12, 9, 0, 1, tzinfo=timezone.utc)  # converted to UTC
    hit = report.parse_line(caddy("2402:4e00::1", 1794477601.5, "/?gclid=X", 0, "Bytespider"))
    assert (hit.ip, hit.status, hit.ua) == ("2402:4e00::1", 0, "Bytespider") and hit.ts.year == 2026
    old = report.parse_line(
        json.dumps(
            {"ts": "2026-11-12T09:00:01Z", "status": 200, "request": {"remote_addr": "1.2.3.4:5555", "uri": "/"}}
        )
    )
    assert old.ip == "1.2.3.4" and old.ts.hour == 9
    short = report.parse_line('1.2.3.4 - - [12/Nov/2026:10:00:01 +0000] "GET / HTTP/1.1" 200 12')  # "common" format
    assert short.ua == "" and short.status == 200
    for bad in ["", "garbage", "{not json", '{"level":"info","msg":"server running"}', "[1,2]"]:
        assert report.parse_line(bad) is None


def test_ad_click_detection():
    assert report.ad_click("/?gclid=abc") == ("google", "abc")
    assert report.ad_click("/p/?x=1&gbraid=g1") == ("google", "g1")
    assert report.ad_click("/?wbraid=w1") == ("google", "w1")
    assert report.ad_click("/?msclkid=m1") == ("microsoft", "m1")
    assert report.ad_click("/?utm_source=Facebook&utm_medium=CPC") == ("meta", "")
    assert report.ad_click("/?utm_source=ig&utm_medium=paid-social") == ("meta", "")
    assert report.ad_click("/?utm_source=bing&utm_medium=cpc") == ("microsoft", "")
    assert report.ad_click("/?utm_source=newsletter&utm_medium=cpc") == ("newsletter", "")
    for organic in ["/", "/p/?page=2", "/?utm_medium=email", "/?utm_medium=organic", "/?gclid=", "/?fbclid=abc"]:
        assert report.ad_click(organic) is None, organic


def test_classifier_networks_agents_and_allow():
    c = classifier()
    assert c.verdict("43.173.132.9", CHROME) == ("network", "AS132203 (tencent-cloud) 43.173.0.0/16")
    assert c.verdict("43.173.5.77", CHROME)[1].endswith("43.173.0.0/16")  # nested /24 folded into its /16
    assert c.verdict("1.15.0.1", CHROME) == ("network", "AS45090 (tencent-cloud) 1.12.0.0/14")
    assert c.verdict("::ffff:43.173.1.1", CHROME)[0] == "network"
    assert c.verdict("2402:4e00:1::1", CHROME)[0] == "network"
    assert c.verdict("43.172.200.1", CHROME) is None and c.verdict("66.249.66.1", CHROME) is None
    assert c.verdict("8.8.8.8", "python-requests/2.32") == ("agent", "python-requests")
    assert c.verdict("not-an-ip", CHROME) is None
    allowed = classifier(networks={"allow": ["43.173.132.9/32"], "block": ["203.0.113.0/24"], "asns": ["AS64500"]})
    assert allowed.verdict("43.173.132.9", CHROME) is None
    assert allowed.verdict("203.0.113.5", CHROME) == ("network", "manual 203.0.113.0/24")


def test_analyze_counts_bots_and_ad_clicks():
    rep = report.analyze(LOG, classifier())
    assert (rep.lines, rep.parsed, rep.requests, rep.ips) == (17, 15, 15, 8)
    assert (rep.bot_requests, rep.bot_cut, rep.bot_served, rep.bot_ips) == (3, 2, 1, 2)
    assert rep.by_detail == {"AS132203 (tencent-cloud)": 2, "python-requests": 1}
    google = rep.clicks_by("google")
    assert google == {"total": 7, "network": 1, "agent": 1, "clean": 1, "no-resources": 1, "repeated": 3}
    assert rep.clicks_by("microsoft") == {"total": 1, "clean": 1}
    assert rep.clicks_by("meta") == {"total": 1, "clean": 1}
    assert rep.platforms() == ["google", "meta", "microsoft"]
    net = next(c for c in rep.clicks if c.click_id == "NET-1")
    assert net.cut and net.first.status == 444 and "43.173.0.0/16" in net.detail
    ua = next(c for c in rep.clicks if c.click_id == "UA-1")
    assert not ua.cut and ua.detail == "python-requests"  # billed AND served: n-antibot was not installed there
    assert rep.top_unblocked[0][0] == "81.40.9.9"
    assert "43.173.132.9" not in [ip for ip, *_ in rep.top_unblocked]


def test_since_until_and_min_repeat():
    day = datetime(2026, 11, 13, tzinfo=timezone.utc)
    second = report.analyze(LOG, classifier(), since=day)
    assert second.requests == 5 and second.platforms() == ["meta", "microsoft"]
    first = report.analyze(LOG, classifier(), until=day)
    assert first.requests == 10 and first.platforms() == ["google"]
    strict = report.analyze(LOG, classifier(), min_repeat=4)
    assert "repeated" not in strict.clicks_by("google")


def test_no_resource_hint_needs_a_log_with_resources():
    only_pages = [combined("81.40.1.2", "12/Nov/2026:10:03:00", "/?gclid=ONE-1")]
    assert report.analyze(only_pages, classifier()).clicks_by("google") == {"total": 1, "clean": 1}


def test_csv_and_json_outputs():
    rep = report.analyze(LOG, classifier())
    buf = io.StringIO()
    assert report.write_csv(rep, buf) == 6
    rows = list(csv.DictReader(io.StringIO(buf.getvalue())))
    assert [r["verdict"] for r in rows] == ["bot", "bot", "suspicious", "suspicious", "suspicious", "suspicious"]
    assert rows[0] == {
        "date_utc": "2026-11-12",
        "time_utc": "09:00:01",
        "platform": "google",
        "click_id": "NET-1",
        "ip": "43.173.132.9",
        "verdict": "bot",
        "reason": "from a blocked network",
        "detail": "AS132203 (tencent-cloud) 43.173.0.0/16",
        "cut_off": "yes",
        "status": "444",
        "user_agent": CHROME,
        "campaign": "",
        "ad_group": "",
        "ad_id": "",
        "keyword": "",
        "url": "/p/a/?gclid=NET-1",
    }
    everything = io.StringIO()
    assert report.write_csv(rep, everything, include_clean=True) == 9
    data = report.as_dict(rep)
    assert data["bots"]["requests"] == 3 and data["ad_clicks"]["google"]["total"] == 7
    assert json.dumps(data)
    text = report.render_text(rep)
    assert "google: 7 clicks" in text and "bots:        2 (28.6%)" in text and text.isascii()


def test_cli_report_with_gzip_and_csv(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("n_antibot.ranges.fetch_asn", lambda asn, **_: FAKE.get(asn, []))
    plain = tmp_path / "access.log"
    plain.write_text("\n".join(LOG[:6]) + "\n")
    packed = tmp_path / "access.log.1.gz"
    with gzip.open(packed, "wt") as f:
        f.write("\n".join(LOG[6:]) + "\n")
    out = tmp_path / "claim" / "clicks.csv"
    assert main(["report", str(plain), str(packed), "--csv", str(out)]) == 0
    printed = capsys.readouterr()
    assert "google: 7 clicks" in printed.out and "6 ad clicks written" in printed.err
    assert out.read_text().count("\n") == 7
    assert main(["report", str(plain), "--json", "--since", "2026-11-12", "--until", "2026-11-12"]) == 0
    assert json.loads(capsys.readouterr().out)["requests"] == 6
    assert main(["report", str(plain), "--since", "yesterday"]) == 3
    assert main(["report", str(tmp_path / "missing.log")]) == 3


# ---------------------------------------------------------------- data-center networks and ad clicks
CLOUDS = {**FAKE, "AS16509": ["3.0.0.0/9", "2600:1f00::/24"], "AS24940": ["5.9.0.0/16"]}


def cloud_classifier(**over):
    return report.Classifier.from_config(from_dict(over), fetch_asn=lambda asn: CLOUDS.get(asn, []))


def test_ad_clicks_from_data_centers_are_bots_even_if_that_cloud_is_not_blocked():
    log = [
        combined("3.5.5.5", "12/Nov/2026:10:00:00", "/?gclid=AWS-1"),  # served: AWS is not blocked
        combined("3.5.5.5", "12/Nov/2026:10:00:01", "/app.css"),
        combined("5.9.1.1", "12/Nov/2026:10:01:00", "/?msclkid=HZ-1"),
        combined("3.5.5.6", "12/Nov/2026:10:02:00", "/pricing"),  # not an ad click: nothing to flag
        combined("81.40.1.1", "12/Nov/2026:10:03:00", "/?gclid=OK-1"),
        combined("81.40.1.1", "12/Nov/2026:10:03:01", "/app.css"),
    ]
    c = cloud_classifier()
    assert c.verdict("3.5.5.5", CHROME) is None  # not blocked for normal traffic
    assert c.datacenter("3.5.5.5") == "AS16509 (aws) 3.0.0.0/9" and c.datacenter("2600:1f00::1").startswith("AS16509")
    assert c.datacenter("43.173.1.1") is None  # already a blocked network, not counted twice
    rep = report.analyze(log, c)
    assert rep.bot_requests == 0  # the Bots section only counts what is blocked
    assert rep.clicks_by("google") == {"total": 2, "datacenter": 1, "clean": 1}
    assert rep.clicks_by("microsoft") == {"total": 1, "datacenter": 1}
    aws = next(x for x in rep.clicks if x.click_id == "AWS-1")
    assert report.click_verdict(aws) == "bot" and aws.detail == "AS16509 (aws) 3.0.0.0/9" and not aws.cut
    text = report.render_text(rep)
    assert "bots:        1 (50.0%)  [blocked network 0, robot 0, data center 1]" in text
    assert report.click_dict(aws)["reason"] == "from a data-center network"


def test_ads_networks_can_be_narrowed_or_extended():
    only = cloud_classifier(ads={"networks": ["hetzner"]})
    assert only.datacenter("3.5.5.5") is None and only.datacenter("5.9.1.1").startswith("AS24940 (hetzner)")
    extra = report.Classifier.from_config(
        from_dict({"ads": {"networks": [], "asns": ["AS64500"]}}),
        fetch_asn=lambda asn: {"AS64500": ["198.51.100.0/24"]}.get(asn, []),
    )
    assert extra.datacenter("198.51.100.7") == "AS64500 198.51.100.0/24"
    allowed = cloud_classifier(networks={"allow": ["3.5.5.5/32"]})
    assert allowed.datacenter("3.5.5.5") is None  # your own server in AWS is never held against a click


def test_range_cache_survives_a_failed_download(tmp_path, monkeypatch):
    from n_antibot import ranges

    monkeypatch.setenv("N_ANTIBOT_CACHE", str(tmp_path))
    calls = []

    def fetch(asn, **_):
        calls.append(asn)
        if len(calls) > 1:
            raise ranges.FetchError("ripestat down")
        return ["192.0.2.0/24"]

    monkeypatch.setattr(ranges, "fetch_asn", fetch)
    assert ranges.fetch_asn_cached("AS64500") == ["192.0.2.0/24"] and (tmp_path / "AS64500.json").exists()
    assert ranges.fetch_asn_cached("AS64500") == ["192.0.2.0/24"] and calls == ["AS64500"]  # fresh: no download
    assert ranges.fetch_asn_cached("AS64500", ttl=0) == ["192.0.2.0/24"] and len(calls) == 2  # stale copy used
    import pytest

    with pytest.raises(ranges.FetchError):
        ranges.fetch_asn_cached("AS64501", ttl=0)  # nothing cached and the download fails
    monkeypatch.setenv("N_ANTIBOT_CACHE", "off")
    assert ranges.cache_dir() is None

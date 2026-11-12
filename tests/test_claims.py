from __future__ import annotations

import csv
from datetime import datetime, timezone

from test_report import CHROME, FAKE, classifier, combined

from n_antibot import claims, report
from n_antibot.cli import main

TODAY = datetime(2026, 11, 20, tzinfo=timezone.utc)
LOG = [
    combined("43.173.1.1", "12/Nov/2026:10:00:01", "/a/?gclid=G-1&gad_campaignid=998877&utm_term=running+shoes", 444),
    combined("43.173.1.1", "01/Sep/2026:10:00:01", "/a/?gclid=G-OLD", 444),  # older than Google's 60 days
    combined("8.8.8.8", "12/Nov/2026:10:01:00", "/?gclid=G-2", 200, "python-requests/2.32"),
    combined("81.40.1.1", "12/Nov/2026:10:02:00", "/?gclid=G-OK"),
    combined("81.40.1.1", "12/Nov/2026:10:02:01", "/app.css"),
    combined(
        "43.173.1.2",
        "12/Nov/2026:10:03:00",
        "/?msclkid=M-1&utm_campaign=brand&adgroupid=55&adid=77&keyword=shoes",
        444,
    ),
    combined(
        "43.173.1.3",
        "12/Nov/2026:10:04:00",
        "/?utm_source=facebook&utm_medium=paid-social&utm_campaign=winter&adset_id=5",
        444,
    ),
    combined("43.173.1.4", "12/Nov/2026:10:05:00", "/?utm_source=newsletter&utm_medium=cpc", 444),
    combined("81.40.1.9", "12/Nov/2026:10:06:00", "/?li_fat_id=L-OK"),
    combined("81.40.1.9", "12/Nov/2026:10:06:01", "/app.css"),
]


def packs(tmp_path):
    rep = report.analyze(LOG, classifier())
    return rep, claims.write_packs(rep, tmp_path, today=TODAY)


def test_platform_table_is_complete_and_sourced():
    for p in claims.PLATFORMS.values():
        assert p.where and p.outcome and p.source.startswith("https://") and p.url.startswith("https://"), p.key
        assert p.checked == "2026-11-12"
        if p.has_process:
            assert p.window_days in (60, 90) and p.asks, p.key
        else:
            assert p.window_days is None and p.asks == (), p.key
    assert [p for p, v in claims.PLATFORMS.items() if v.has_process] == ["google", "microsoft", "linkedin", "x"]
    assert claims.PLATFORMS["google"].window_days == 60 and claims.PLATFORMS["linkedin"].window_days == 90
    assert len(claims.as_dict()) == len(claims.PLATFORMS)


def test_ad_fields_from_utm_and_platform_parameters():
    f = report.ad_fields("/a/?gclid=G-1&gad_campaignid=998877&utm_term=running+shoes")
    assert f == {"campaign": "998877", "ad_group": "", "ad_id": "", "keyword": "running shoes"}
    f = report.ad_fields("/?msclkid=M-1&utm_campaign=brand&adgroupid=55&adid=77&keyword=shoes")
    assert f == {"campaign": "brand", "ad_group": "55", "ad_id": "77", "keyword": "shoes"}
    assert report.ad_fields("/")["campaign"] == ""


def test_one_pack_per_platform_with_flagged_clicks(tmp_path):
    _, written = packs(tmp_path)
    assert [p["platform"] for p in written] == [
        "google",
        "meta",
        "microsoft",
        "newsletter",
    ]  # linkedin had no flagged click
    google = written[0]
    assert google["clicks"] == 3 and google["bots"] == 3 and google["within_deadline"] == 2 and google["has_process"]
    assert not written[1]["has_process"]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f for p in written for f in p["files"])


def test_google_pack_has_what_google_asks_for(tmp_path):
    packs(tmp_path)
    rows = list(csv.DictReader((tmp_path / "google-clicks.csv").open()))
    assert [r["click_id"] for r in rows] == ["G-OLD", "G-1", "G-2"]
    assert [r["within_deadline"] for r in rows] == ["no", "yes", "yes"]
    one = rows[1]
    assert one["ip"] == "43.173.1.1" and one["user_agent"] == CHROME and one["date_utc"] == "2026-11-12"
    assert one["campaign"] == "998877" and one["keyword"] == "running shoes" and one["verdict"] == "bot"
    text = (tmp_path / "google-claim.txt").read_text()
    assert "https://support.google.com/google-ads/contact/click_quality" in text
    assert "60 days from the activity." in text and "2 clicks inside the deadline, 1 already too old" in text
    for ask in claims.PLATFORMS["google"].asks:
        assert ask in text
    assert "Paid clicks from Google Ads in the logs: 4" in text and "Bots: 3" in text and "Clean: 1" in text
    assert "2 clicks came from data-center networks (2 from AS132203 (tencent-cloud))" in text
    assert "1 click identified as robots or scraping libraries (1 as python-requests)" in text
    assert "Campaign in the URL: 1 of 3 clicks" in text and text.isascii()
    sample = (tmp_path / "google-log-sample.log").read_text().splitlines()
    assert sample == [LOG[1], LOG[0], LOG[2]]  # the very lines of the server log, oldest first


def test_microsoft_and_meta_packs(tmp_path):
    packs(tmp_path)
    ms = next(csv.DictReader((tmp_path / "microsoft-clicks.csv").open()))
    assert (ms["campaign"], ms["ad_group"], ms["ad_id"], ms["keyword"]) == ("brand", "55", "77", "shoes")
    text = (tmp_path / "microsoft-claim.txt").read_text()
    assert "Affected ad group and ad group number" in text and "go.microsoft.com/fwlink?LinkId=398371" in text
    meta = (tmp_path / "meta-claim.txt").read_text()
    assert "Meta documents no process for invalid clicks" in meta and "The platform documents none." in meta
    assert "facebook.com/help/contact/649167531904667" in meta
    other = (tmp_path / "newsletter-claim.txt").read_text()
    assert "No documented process found" in other and "Rules read" not in other


def test_no_flagged_clicks_no_files(tmp_path):
    rep = report.analyze([LOG[3], LOG[4]], classifier())
    assert claims.write_packs(rep, tmp_path / "empty", today=TODAY) == []
    assert list((tmp_path / "empty").iterdir()) == []


def test_cli_claim_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("n_antibot.ranges.fetch_asn", lambda asn, **_: FAKE.get(asn, []))
    log = tmp_path / "access.log"
    log.write_text("\n".join(LOG) + "\n")
    out = tmp_path / "claim"
    assert main(["report", str(log), "--claim-dir", str(out)]) == 0
    err = capsys.readouterr().err
    assert "Google Ads: 3 clicks" in err and "google-claim.txt" in err
    assert "Meta Ads (Facebook, Instagram): 1 clicks" in err and "documents no process" in err
    assert (out / "google-clicks.csv").exists() and (out / "meta-log-sample.log").exists()

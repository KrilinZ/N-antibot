from __future__ import annotations

import csv
import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_report import CHROME, FAKE, LOG

from n_antibot import __version__, api
from n_antibot.config import from_dict

TOKEN = "s3cret-token-for-tests-0123456789"


class Clock:
    now = 1794500000.0  # 12-nov-2026

    def __call__(self):
        return self.now


@pytest.fixture
def server(tmp_path):
    log = tmp_path / "access.log"
    log.write_text("\n".join(LOG[:15]) + "\n")
    state = {"fail": False, "calls": 0}

    def fetch(asn):
        state["calls"] += 1
        if state["fail"]:
            raise OSError("ripestat down")
        return FAKE.get(asn, [])

    clock = Clock()
    cfg = from_dict({"paths": {"exclude": ["/.well-known/*", "/api/*"]}})
    service = api.Service(cfg, [str(tmp_path / "access.log*")], fetch_asn=fetch, ranges_ttl=3600, clock=clock)
    srv = api.make_server(service, "127.0.0.1", 0, TOKEN)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {
        "url": f"http://127.0.0.1:{srv.server_address[1]}",
        "log": log,
        "state": state,
        "clock": clock,
        "tmp": tmp_path,
    }
    srv.shutdown()
    srv.server_close()


def call(base, path, token=TOKEN, method="GET"):
    req = urllib.request.Request(base["url"] + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if "json" in r.headers["Content-Type"] else body), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()), e.headers


def test_health_and_openapi_need_no_token(server):
    assert call(server, "/health", token=None)[:2] == (200, {"status": "ok", "version": __version__})
    status, spec, _ = call(server, "/v1/openapi.json", token=None)
    assert status == 200 and spec["openapi"] == "3.1.0" and "/v1/ad-clicks" in spec["paths"]


def test_token_is_required_and_never_accepted_in_the_url(server):
    status, body, headers = call(server, "/v1/summary", token=None)
    assert status == 401 and body["error"]["code"] == "unauthorized" and headers["WWW-Authenticate"] == "Bearer"
    assert call(server, "/v1/summary", token="wrong-token-wrong-token")[0] == 401
    status, body, _ = call(server, f"/v1/summary?token={TOKEN}", token=None)
    assert status == 400 and body["error"]["code"] == "token_in_url"


def test_summary_bots_and_period_filters(server):
    status, data, headers = call(server, "/v1/summary")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert data["requests"] == 15 and data["bots"]["requests"] == 3 and data["bots"]["cut_off"] == 2
    assert data["ad_clicks"]["google"]["total"] == 7 and data["ad_clicks"]["google"]["network"] == 1
    day = call(server, "/v1/summary?since=2026-11-13&until=2026-11-13")[1]
    assert day["requests"] == 5 and list(day["ad_clicks"]) == ["meta", "microsoft"]
    bots = call(server, "/v1/bots")[1]
    assert (
        bots["by"] == {"AS132203 (tencent-cloud)": 2, "python-requests": 1}
        and bots["top_unblocked"][0]["ip"] == "81.40.9.9"
    )
    assert bots["total_requests"] == 15 and bots["requests"] == 3
    status, body, _ = call(server, "/v1/summary?since=ayer")
    assert status == 400 and "since must be a date" in body["error"]["message"]


def test_ad_clicks_filters_paging_and_csv(server):
    data = call(server, "/v1/ad-clicks")[1]
    assert data["total"] == 9 and data["limit"] == 100 and len(data["clicks"]) == 9
    bots = call(server, "/v1/ad-clicks?verdict=bot&platform=google")[1]
    assert [c["click_id"] for c in bots["clicks"]] == ["NET-1", "UA-1"]
    first = bots["clicks"][0]
    assert first["ip"] == "43.173.132.9" and first["cut_off"] is True and first["verdict"] == "bot"
    assert (
        first["timestamp"] == "2026-11-12T09:00:01+00:00"
        and first["user_agent"] == CHROME
        and first["campaign"] is None
    )
    page = call(server, "/v1/ad-clicks?limit=2&offset=1")[1]
    assert page["total"] == 9 and [c["click_id"] for c in page["clicks"]] == ["UA-1", "OK-1"]
    status, text, headers = call(server, "/v1/ad-clicks?verdict=suspicious&format=csv")
    assert status == 200 and headers["Content-Type"].startswith("text/csv")
    assert [r["click_id"] for r in csv.DictReader(io.StringIO(text))] == ["ONE-1", "REP-1", "REP-2", "REP-3"]
    for bad in ["verdict=maybe", "limit=0", "limit=5000", "limit=x", "offset=-1", "format=xml"]:
        status, body, _ = call(server, f"/v1/ad-clicks?{bad}")
        assert status == 400 and body["error"]["code"] == "invalid_parameter", bad


def test_check_and_blocklist(server):
    hit = call(server, "/v1/check?ip=43.173.132.9&user_agent=Mozilla")[1]
    assert hit["is_bot"] and hit["reason"] == "network" and hit["would_block"] and "43.173.0.0/16" in hit["match"]
    agent = call(server, "/v1/check?user_agent=python-requests/2.32&path=/api/hook")[1]
    assert (
        agent["is_bot"] and agent["match"] == "python-requests" and agent["path_excluded"] and not agent["would_block"]
    )
    assert call(server, "/v1/check?ip=66.249.66.1&user_agent=Googlebot")[1]["is_bot"] is False
    assert call(server, "/v1/check")[0] == 400 and call(server, "/v1/check?ip=nope")[0] == 400
    bl = call(server, "/v1/blocklist")[1]
    assert (
        "43.173.0.0/16" in bl["ipv4"]
        and "Bytespider" in bl["user_agents"]
        and bl["exclude_paths"] == ["/.well-known/*", "/api/*"]
    )


def test_claims_endpoint(server):
    data = call(server, "/v1/claims")[1]
    rows = {p["platform"]: p for p in data["platforms"]}
    assert rows["google"]["url"].endswith("/click_quality") and rows["google"]["deadline_days"] == 60
    assert (
        rows["google"]["clicks"] == 7 and rows["google"]["bot_clicks"] == 2 and rows["google"]["suspicious_clicks"] == 4
    )
    assert rows["google"]["flagged_within_deadline"] == 6
    assert rows["meta"]["has_process"] is False and rows["linkedin"]["clicks"] == 0


def test_errors_unknown_path_wrong_method_and_missing_logs(server):
    status, body, _ = call(server, "/v1/nope")
    assert status == 404 and body["error"]["code"] == "not_found"
    status, body, headers = call(server, "/v1/summary", method="POST")
    assert status == 405 and headers["Allow"] == "GET, HEAD, OPTIONS"
    server["log"].unlink()
    status, body, _ = call(server, "/v1/summary")
    assert status == 503 and body["error"]["code"] == "no_logs"


def test_new_log_lines_show_up_and_rotated_files_are_read(server):
    assert call(server, "/v1/summary")[1]["requests"] == 15
    (server["tmp"] / "access.log.1").write_text(LOG[0].replace("NET-1", "NET-9") + "\n")
    data = call(server, "/v1/summary")[1]
    assert data["requests"] == 16 and data["ad_clicks"]["google"]["network"] == 2


def test_a_failed_range_refresh_keeps_the_previous_lists(server):
    assert call(server, "/v1/check?ip=43.173.1.1")[1]["is_bot"]
    calls = server["state"]["calls"]
    assert call(server, "/v1/check?ip=43.173.1.1")[0] == 200 and server["state"]["calls"] == calls  # cached
    server["clock"].now += 2 * 3600
    server["state"]["fail"] = True
    assert call(server, "/v1/check?ip=43.173.1.1")[1]["is_bot"]  # refresh failed: old lists still answer


def test_without_any_ranges_the_api_says_so(tmp_path):
    def down(asn):
        raise OSError("ripestat down")

    service = api.Service(from_dict({}), [str(tmp_path / "x.log")], fetch_asn=down)
    with pytest.raises(api.ApiError) as e:
        service.classifier()
    assert e.value.status == 503 and e.value.code == "ranges_unavailable"


def test_refuses_to_listen_beyond_loopback_without_a_token(tmp_path):
    service = api.Service(from_dict({}), [str(tmp_path / "x.log")])
    with pytest.raises(ValueError, match="without a token"):
        api.make_server(service, "0.0.0.0", 0, None)
    with pytest.raises(ValueError, match="at least 16"):
        api.make_server(service, "127.0.0.1", 0, "short")
    assert api.is_loopback("127.0.0.1") and api.is_loopback("::1") and api.is_loopback("localhost")
    assert not api.is_loopback("0.0.0.0") and not api.is_loopback("example.com")


def test_openapi_file_in_docs_matches_the_code():
    spec = Path(__file__).parent.parent / "docs" / "openapi.json"
    assert json.loads(spec.read_text()) == api.openapi(), "run: python -m n_antibot.api > docs/openapi.json"

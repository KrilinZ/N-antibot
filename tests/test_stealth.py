"""Bots posing as a browser ([stealth]): rules, safety nets, the report, and real Caddy, nginx and Apache over HTTPS.

The server tests send the same requests with curl over HTTP/1.1 and HTTP/2 and check that the impostor is cut and
that real browsers, search engines, AI crawlers and signed agents get in.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from test_servers import _apache_binary, _apache_modules, free_port, wait

from n_antibot import generate, stealth
from n_antibot.config import ConfigError, from_dict
from n_antibot.report import Classifier, analyze, parse_line

VERSIONS = {"stable": 159, "canary": 160}
CHROME_VERSIONS = lambda: dict(VERSIONS)  # noqa: E731

# The impostor seen in November 2026, header by header (from a real access log).
IMPOSTOR_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
)
IMPOSTOR_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "close",
}
REAL_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36"
)
REAL_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Sec-Ch-Ua": '"Chromium";v="159", "Google Chrome";v="159", "Not_A Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}
ALL = ["chrome-http1-without-fetch-metadata", "chrome-without-fetch-metadata", "residential-proxy-zh"]


def stealth_cfg(fmt: str = "caddy", **extra):
    body = {"presets": ALL, "future_chrome": True, "referers": ["m.baidu.com", "aocr.org"]}
    body.update(extra)
    return from_dict(
        {
            "networks": {"presets": []},
            "robots": {"presets": []},
            "paths": {"exclude": ["/api/*", "/.well-known/*"]},
            "output": {"format": fmt},
            "stealth": body,
        }
    )


def would_cut(cfg, ua, headers, protocol="HTTP/1.1", https=True) -> str | None:
    declared = cfg.declared_regex()
    for rule in cfg.stealth_rules(VERSIONS):
        if stealth.matches(rule, user_agent=ua, protocol=protocol, https=https, headers=headers, declared=declared):
            return rule.name
    return None


# ---- rules -----------------------------------------------------------------------------------------------------------
def test_number_regex_is_exact():
    for lo, hi in [(0, 9999), (90, None), (163, None), (5, 152), (100, 100), (99, 101), (10, 99), (123, 4567)]:
        rx = re.compile("^" + stealth.number_regex(lo, hi) + "$")
        top = 9999 if hi is None else hi
        assert [n for n in range(10000) if bool(rx.match(str(n))) != (lo <= n <= top)] == []


def test_the_impostor_is_cut_and_real_browsers_are_not():
    cfg = stealth_cfg()
    assert would_cut(cfg, IMPOSTOR_UA, IMPOSTOR_HEADERS) == "chrome-http1-without-fetch-metadata"
    # On plain HTTP a real Chrome sends no Fetch Metadata either: nothing tells them apart, nothing is cut there.
    assert would_cut(cfg, IMPOSTOR_UA, IMPOSTOR_HEADERS, https=False) is None
    # Same bot over HTTP/2 or HTTP/3: no Sec-Fetch-Mode and no Sec-Ch-Ua.
    for proto in ("HTTP/2", "HTTP/3"):
        assert would_cut(cfg, IMPOSTOR_UA, IMPOSTOR_HEADERS, proto) == "chrome-without-fetch-metadata"
    for proto in ("HTTP/1.1", "HTTP/2", "HTTP/3"):
        assert would_cut(cfg, REAL_UA, REAL_HEADERS, proto) is None
        assert would_cut(cfg, REAL_UA, {**REAL_HEADERS, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}, proto) is None


def test_future_chrome_and_referer_spam():
    cfg = stealth_cfg()
    assert would_cut(cfg, REAL_UA.replace("159", "163"), REAL_HEADERS, "HTTP/2") == "future-chrome"
    assert would_cut(cfg, REAL_UA.replace("159", "162"), REAL_HEADERS, "HTTP/2") is None  # Canary + 2 still passes
    spam = "https://www.google.com/url?q=http://m.baidu.com/s?wd=x"
    assert would_cut(cfg, REAL_UA, {**REAL_HEADERS, "Referer": spam}, "HTTP/2") == "referer-spam"
    assert would_cut(cfg, REAL_UA, {**REAL_HEADERS, "Referer": "https://aocr.org/"}, "HTTP/2") == "referer-spam"
    encoded = "https://www.google.com/url?q=http%3A%2F%2Fm.baidu.com%2F"
    assert would_cut(cfg, REAL_UA, {**REAL_HEADERS, "Referer": encoded}, "HTTP/2") == "referer-spam"
    for fine in ("https://www.google.com/", "https://notaocr.org/", "https://m.baidu.com.example/x"):
        assert would_cut(cfg, REAL_UA, {**REAL_HEADERS, "Referer": fine}, "HTTP/2") is None, fine


@pytest.mark.parametrize("label,ua", stealth.GOOD_ROBOTS, ids=[x[0] for x in stealth.GOOD_ROBOTS])
def test_search_engines_and_ai_are_never_cut(label, ua):
    cfg = stealth_cfg()
    rules = cfg.stealth_rules(VERSIONS)
    rows = stealth.check_robots(rules, cfg.declared_regex(), VERSIONS)
    assert {r["robot"]: r["status"] for r in rows}[label] == "ok"
    for rule in rules:
        req = stealth.worst_case(rule, ua, VERSIONS)
        assert not stealth.matches(
            rule,
            user_agent=req.user_agent,
            protocol=req.protocol,
            https=req.https,
            headers=dict(req.headers),
            declared=cfg.declared_regex(),
        )


def test_signed_agents_pass():
    cfg = stealth_cfg()
    signed = {**IMPOSTOR_HEADERS, "Signature-Agent": '"https://chatgpt.com"'}
    assert would_cut(cfg, IMPOSTOR_UA, signed) is None


@pytest.mark.parametrize(
    "body,message",
    [
        ({"fingerprint": [{"name": "xx", "protocols": ["http/1.1"]}]}, "real visitor"),
        ({"fingerprint": [{"name": "xx", "protocols": ["http/2"]}]}, "real visitor"),
        ({"fingerprint": [{"name": "xx", "headers": {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}}]}, "real visitor"),
        ({"fingerprint": [{"name": "xx", "missing": ["Sec-Fetch-Mode"]}]}, "plain HTTP"),
        ({"fingerprint": [{"name": "xx"}]}, "no condition"),
        ({"fingerprint": [{"name": "xx", "missing": ["Accept"], "headers": {"Accept": "a"}}]}, "both"),
        ({"fingerprint": [{"name": "xx", "headers": {"Accept-Language": 'a"b'}}]}, "printable"),
        ({"fingerprint": [{"name": "xx", "headers": {"Accept-Language": "{x}"}}]}, "printable"),
        ({"fingerprint": [{"name": "xx", "protocols": ["spdy"]}]}, "protocol"),
        ({"fingerprint": [{"name": "xx", "colour": "red"}]}, "unknown key"),
        ({"fingerprint": [{"name": "Bad Name", "missing": ["Sec-Fetch-Mode"]}]}, "name"),
        ({"referers": ["google.com"]}, "google"),
        ({"referers": ["bing.com"]}, "bing"),
        ({"referers": ["not a domain"]}, "domain"),
        ({"presets": ["nope"]}, "unknown preset"),
    ],
)
def test_dangerous_or_broken_rules_are_refused(body, message):
    with pytest.raises(ConfigError, match=message):
        from_dict({"stealth": body})


def test_nftables_cannot_see_headers():
    with pytest.raises(ConfigError, match="nftables"):
        from_dict({"output": {"format": "nftables"}, "stealth": {"presets": ["residential-proxy-zh"]}})


def test_default_output_does_not_change():
    plain = from_dict({})
    assert not plain.has_stealth()
    assert "Stealth" not in generate(plain, fetch=lambda asns, **_: ["192.0.2.0/24"], today="2026-01-01")


def test_old_chrome_rule_uses_todays_stable():
    cfg = from_dict(
        {
            "stealth": {
                "fingerprint": [
                    {
                        "name": "old-chrome-http1",
                        "chrome_behind": 4,
                        "protocols": ["http/1.1"],
                        "missing": ["Sec-Fetch-Mode"],
                    }
                ]
            }
        }
    )
    (rule,) = cfg.stealth_rules(VERSIONS)
    assert re.search(rule.ua_regex, IMPOSTOR_UA.replace("144", "154"))
    assert not re.search(rule.ua_regex, IMPOSTOR_UA.replace("144", "155"))


def test_chrome_versions_come_from_google(monkeypatch):
    seen = []

    def download(url):
        seen.append(url)
        return {"versions": [{"version": "161.0.8200.1" if "canary" in url else "159.0.8154.34"}]}

    assert stealth.chrome_versions(download=download) == {"stable": 159, "canary": 161}
    assert all(u.startswith("https://versionhistory.googleapis.com/") for u in seen)
    with pytest.raises(Exception, match="unexpected"):
        stealth.chrome_versions(download=lambda url: {"versions": []})


def test_generate_stops_when_versions_cannot_be_read():
    from n_antibot.ranges import FetchError

    def broken():
        raise FetchError("Chrome version history: offline")

    with pytest.raises(FetchError):
        generate(stealth_cfg(), fetch=lambda a, **_: [], chrome=broken)


# ---- report ----------------------------------------------------------------------------------------------------
def _caddy_line(ua, headers, proto, tls=True, uri="/brand/x", ip="203.0.113.7", status=0):
    req = {
        "remote_ip": ip,
        "proto": proto,
        "method": "GET",
        "host": "shop.example.test",
        "uri": uri,
        "headers": {"User-Agent": [ua], **{k: [v] for k, v in headers.items()}},
    }
    if tls:
        req["tls"] = {"version": 772, "proto": ""}
    return json.dumps({"ts": 1795700000.0, "request": req, "status": status})


def test_report_counts_impostors_from_caddy_logs():
    cfg = stealth_cfg()
    classifier = Classifier(cfg, [], rules=cfg.stealth_rules(VERSIONS))
    lines = [
        _caddy_line(IMPOSTOR_UA, IMPOSTOR_HEADERS, "HTTP/1.1"),
        _caddy_line(IMPOSTOR_UA.replace("144", "130"), IMPOSTOR_HEADERS, "HTTP/1.1", ip="198.51.100.9"),
        _caddy_line(REAL_UA, REAL_HEADERS, "HTTP/2.0", status=200, ip="192.0.2.10"),
        _caddy_line(stealth.GOOD_ROBOTS[0][1], IMPOSTOR_HEADERS, "HTTP/1.1", status=200, ip="66.249.66.1"),
    ]
    rep = analyze(lines, classifier)
    assert rep.bot_requests == 2 and rep.bot_cut == 2
    assert rep.by_reason["fingerprint"] == 2
    assert rep.by_detail["fingerprint chrome-http1-without-fetch-metadata"] == 2


def test_combined_logs_have_no_headers_so_only_referer_and_version_rules_apply():
    hit = parse_line(
        '203.0.113.7 - - [26/Nov/2026:11:40:00 +0000] "GET /x HTTP/1.1" 200 12 '
        f'"https://www.google.com/url?q=http://m.baidu.com/" "{REAL_UA}"'
    )
    assert hit.proto == "HTTP/1.1" and hit.https is None
    cfg = stealth_cfg()
    classifier = Classifier(cfg, [], rules=cfg.stealth_rules(VERSIONS))
    assert classifier.fingerprint(hit) == "referer-spam"
    plain = parse_line(f'203.0.113.7 - - [26/Nov/2026:11:40:00 +0000] "GET /x HTTP/1.1" 200 12 "-" "{IMPOSTOR_UA}"')
    assert classifier.fingerprint(plain) is None  # https and headers unknown: no guess


# ---- JSON for the Node middleware ---------------------------------------------------------------------------------
FIXTURE = Path(__file__).parent / "node" / "stealth.json"


def node_fixture() -> str:
    cfg = stealth_cfg("json")
    import n_antibot.ai as ai

    original = ai.protected_ranges
    ai.protected_ranges = lambda download=None: ({"googlebot": ["66.249.64.0/27"]}, [])
    try:
        text = generate(cfg, fetch=lambda a, **_: [], today="2026-11-26", chrome=CHROME_VERSIONS)
    finally:
        ai.protected_ranges = original
    return text


def test_node_fixture_is_current():
    """tests/node/stealth.json is what `generate -f json` makes today (regenerate it if this fails)."""
    data = json.loads(node_fixture())
    data.pop("generator")
    stored = json.loads(FIXTURE.read_text())
    stored.pop("generator")
    assert stored == data


# ---- real servers over HTTPS --------------------------------------------------------------------------------------
def curl(port: int, ua: str, headers: dict, *, http2: bool, path: str = "/", https: bool = True) -> int | str:
    url = f"{'https' if https else 'http'}://localhost:{port}{path}"
    cmd = ["curl", "-sk", "-o", "/dev/null", "-w", "%{http_code} %{http_version}", "--max-time", "5", "-A", ua]
    cmd.append("--http2" if http2 else "--http1.1")
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    out = subprocess.run([*cmd, url], capture_output=True, text=True).stdout.split()
    if not out or out[0] == "000":
        return "closed"
    if https and http2:
        assert out[1] == "2", f"the server did not speak HTTP/2: {out}"
    return int(out[0])


def _cert(d: Path) -> tuple[Path, Path]:
    key, crt = d / "key.pem", d / "cert.pem"
    subprocess.run(
        [
            *("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=localhost"),
            *("-keyout", str(key), "-out", str(crt)),
        ],
        check=True,
        capture_output=True,
    )
    return key, crt


def _wait_https(port: int) -> None:
    wait(port)
    for _ in range(50):
        r = subprocess.run(
            [
                "curl",
                "-sk",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                "2",
                f"https://localhost:{port}/x.txt",
            ],
            capture_output=True,
            text=True,
        )
        if r.stdout not in ("", "000"):
            return
        time.sleep(0.2)


@pytest.fixture
def https_server(tmp_path, request, monkeypatch):
    kind = request.param
    if not shutil.which("curl") or not shutil.which("openssl"):
        pytest.skip("curl and openssl are needed")
    # Loopback is "Googlebot" for the keep-open test only when asked; otherwise no published address list.
    procs = []

    def start(cfg_factory=stealth_cfg, keep_open: list[str] | None = None) -> tuple[int, int, bool]:
        monkeypatch.setattr("n_antibot.ai.protected_ranges", lambda download=None: ({"googlebot": keep_open or []}, []))
        port, plain = free_port(), free_port()
        d = tmp_path / f"{kind}{port}"
        (d / "www/api").mkdir(parents=True)
        (d / "www/index.html").write_text("ok")
        (d / "www/x.txt").write_text("ok")
        (d / "www/api/hook").write_text("ok")
        cfg = cfg_factory(kind)
        snippet = generate(cfg, fetch=lambda a, **_: [], chrome=CHROME_VERSIONS)
        h2 = True
        if kind == "caddy":
            if not shutil.which("caddy"):
                pytest.skip("caddy not installed")
            (d / "n-antibot.caddy").write_text(snippet)
            (d / "Caddyfile").write_text(
                "{\n\tadmin off\n\tauto_https disable_redirects\n\tlocal_certs\n\tskip_install_trust\n}\n"
                f"https://localhost:{port} {{\n\ttls internal\n\timport {d}/n-antibot.caddy\n"
                f"\troot * {d}/www\n\tfile_server\n}}\n"
                f"http://localhost:{plain} {{\n\timport {d}/n-antibot.caddy\n\troot * {d}/www\n\tfile_server\n}}\n"
            )
            env = {"XDG_DATA_HOME": str(d / "data"), "XDG_CONFIG_HOME": str(d / "conf"), "HOME": str(d)}
            procs.append(
                subprocess.Popen(
                    ["caddy", "run", "--config", str(d / "Caddyfile"), "--adapter", "caddyfile"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**__import__("os").environ, **env},
                )
            )
        elif kind == "nginx":
            if not shutil.which("nginx"):
                pytest.skip("nginx not installed")
            key, crt = _cert(d)
            (d / "n-antibot.conf").write_text(snippet)
            version = subprocess.run(["nginx", "-v"], capture_output=True, text=True).stderr
            v = tuple(int(x) for x in re.search(r"(\d+)\.(\d+)\.(\d+)", version).groups())
            listen = f"listen 127.0.0.1:{port} ssl"
            listen += ";\n\t\thttp2 on;" if v >= (1, 25, 1) else " http2;"
            (d / "nginx.conf").write_text(
                f"daemon off;\npid {d}/nginx.pid;\nerror_log {d}/error.log;\nevents {{}}\nhttp {{\n"
                f"\taccess_log off;\n\tclient_body_temp_path {d};\n\tproxy_temp_path {d};\n\tfastcgi_temp_path {d};\n"
                f"\tuwsgi_temp_path {d};\n\tscgi_temp_path {d};\n\tinclude {d}/n-antibot.conf;\n"
                f"\tserver {{\n\t\t{listen}\n\t\tserver_name localhost;\n"
                f'\t\tssl_certificate {crt};\n\t\tssl_certificate_key {key};\n\t\tlocation / {{ return 200 "ok"; }}\n'
                "\t\tif ($n_antibot_block) { return 444; }\n\t}\n"
                f'\tserver {{\n\t\tlisten 127.0.0.1:{plain};\n\t\tlocation / {{ return 200 "ok"; }}\n'
                "\t\tif ($n_antibot_block) { return 444; }\n\t}\n}\n"
            )
            procs.append(subprocess.Popen(["nginx", "-c", str(d / "nginx.conf")], stderr=subprocess.DEVNULL))
        else:
            binary, modules = _apache_binary(), _apache_modules()
            if not binary or not modules or not (modules / "mod_ssl.so").exists():
                pytest.skip("apache with mod_ssl not installed")
            key, crt = _cert(d)
            (d / "n-antibot.conf").write_text(snippet)
            h2 = (modules / "mod_http2.so").exists() and (modules / "mod_mpm_event.so").exists()
            mods = ["mpm_event" if h2 else "mpm_prefork", "unixd", "authz_core", "dir", "rewrite", "log_config"]
            mods += ["socache_shmcb", "ssl"] + (["http2"] if h2 else [])
            load = "".join(
                f"LoadModule {m}_module {modules}/mod_{m}.so\n" for m in mods if (modules / f"mod_{m}.so").exists()
            )
            vhost = f'\tInclude {d}/n-antibot.conf\n\tDocumentRoot "{d}/www"\n'
            (d / "httpd.conf").write_text(
                f'ServerRoot "{d}"\nDefaultRuntimeDir "{d}"\nMutex file:{d} default\nPidFile "{d}/httpd.pid"\n'
                f"Listen 127.0.0.1:{port}\nListen 127.0.0.1:{plain}\nServerName localhost\n{load}"
                f'ErrorLog "{d}/error.log"\nDirectoryIndex index.html\n'
                + ("Protocols h2 http/1.1\n" if h2 else "")
                + f'<Directory "{d}/www">\n\tRequire all granted\n</Directory>\n'
                f"<VirtualHost 127.0.0.1:{port}>\n\tSSLEngine on\n\tSSLCertificateFile {crt}\n"
                f"\tSSLCertificateKeyFile {key}\n{vhost}</VirtualHost>\n"
                f"<VirtualHost 127.0.0.1:{plain}>\n{vhost}</VirtualHost>\n"
            )
            subprocess.run([binary, "-t", "-f", str(d / "httpd.conf")], check=True, capture_output=True)
            procs.append(
                subprocess.Popen(
                    [binary, "-f", str(d / "httpd.conf"), "-DFOREGROUND"],
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            )
        _wait_https(port)
        wait(plain)
        return port, plain, h2

    yield start
    for p in procs:
        p.terminate()
        p.wait(10)


SERVERS = ["caddy", "nginx", "apache"]


def _cut(kind):
    return 403 if kind == "apache" else "closed"


@pytest.mark.parametrize("https_server", SERVERS, indirect=True)
def test_server_cuts_the_impostor_and_lets_everyone_else_in(https_server, request):
    kind = request.node.callspec.params["https_server"]
    port, plain, h2 = https_server()
    cut = _cut(kind)
    protos = [False, True] if h2 else [False]
    # The impostor, over HTTP/1.1 as seen, and over HTTP/2 if it upgrades.
    for http2 in protos:
        assert curl(port, IMPOSTOR_UA, IMPOSTOR_HEADERS, http2=http2) == cut, f"impostor http2={http2}"
    # On plain HTTP a real Chrome sends no Fetch Metadata either: nothing is cut there (redirect to HTTPS instead).
    assert curl(plain, REAL_UA, {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}, http2=False, https=False) == 200
    # Real browsers: HTTP/2 and HTTP/1.1 (corporate proxy), in Spanish and in Chinese.
    for http2 in protos:
        assert curl(port, REAL_UA, REAL_HEADERS, http2=http2) == 200
        zh = {**REAL_HEADERS, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
        assert curl(port, REAL_UA, zh, http2=http2) == 200
    # Every search engine, AI crawler and assistant, sending the impostor's exact headers.
    for label, ua in stealth.GOOD_ROBOTS:
        ua = ua.replace("CURRENT", "144")
        assert curl(port, ua, IMPOSTOR_HEADERS, http2=False) == 200, label
    # A signed agent (Web Bot Auth) with a Chrome User-Agent.
    signed = {**IMPOSTOR_HEADERS, "Signature-Agent": '"https://chatgpt.com"'}
    assert curl(port, IMPOSTOR_UA, signed, http2=False) == 200
    # curl itself, and excluded paths.
    assert curl(port, "curl/8.5.0", {}, http2=False) == 200
    assert curl(port, IMPOSTOR_UA, IMPOSTOR_HEADERS, http2=False, path="/api/hook") == 200
    # Future Chrome version and referer spam, from an otherwise perfect browser.
    future = REAL_UA.replace("Chrome/159", "Chrome/163")
    assert curl(port, future, REAL_HEADERS, http2=h2) == cut
    spam = {**REAL_HEADERS, "Referer": "https://www.google.com/url?q=http://m.baidu.com/"}
    assert curl(port, REAL_UA, spam, http2=h2) == cut
    assert curl(port, REAL_UA, {**REAL_HEADERS, "Referer": "https://www.google.com/"}, http2=h2) == 200


@pytest.mark.parametrize("https_server", SERVERS, indirect=True)
def test_server_keeps_published_ai_addresses_open(https_server):
    """Loopback stands for a published crawler address here: even the impostor's request is let in from it."""
    port, _, _ = https_server(keep_open=["127.0.0.0/8", "::1/128"])
    assert curl(port, IMPOSTOR_UA, IMPOSTOR_HEADERS, http2=False) == 200

"""End-to-end: start real Caddy and nginx with the generated snippet and send requests.

Skipped when the binaries are not installed. Loopback (127.0.0.1) is added to the blocked ranges so the network
block can be tested locally.
"""

from __future__ import annotations

import http.client
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from n_antibot import generate
from n_antibot.config import from_dict

CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
GOOGLE = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BYTESPIDER = "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)"


def no_fetch(asns, **_):
    return []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(port: int, path: str, ua: str) -> int | str:
    """HTTP status, or 'closed' when the server drops the connection without answering."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        c.request("GET", path, headers={"User-Agent": ua})
        return c.getresponse().status
    except (http.client.RemoteDisconnected, ConnectionResetError, http.client.BadStatusLine):
        return "closed"
    finally:
        c.close()


def wait(port: int) -> None:
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("server did not start")


def cfg(fmt: str, block_loopback: bool):
    return from_dict(
        {
            "networks": {"presets": [], "block": ["127.0.0.0/8"] if block_loopback else ["192.0.2.0/24"]},
            "paths": {"exclude": ["/api/*", "/.well-known/*"]},
            "output": {"format": fmt},
        }
    )


@pytest.fixture
def caddy(tmp_path):
    if not shutil.which("caddy"):
        pytest.skip("caddy not installed")
    procs = []

    def start(block_loopback: bool) -> int:
        port = free_port()
        d = tmp_path / f"caddy{port}"
        d.mkdir()
        (d / "n-antibot.caddy").write_text(generate(cfg("caddy", block_loopback), fetch=no_fetch))
        (d / "Caddyfile").write_text(
            "{\n\tauto_https off\n\tadmin off\n}\n"
            f":{port} {{\n\timport {d}/n-antibot.caddy\n\tlog {{\n\t\toutput file {d}/access.log\n\t}}\n"
            '\thandle /api/* {\n\t\trespond "api" 200\n\t}\n'
            '\thandle /product/* {\n\t\trespond "product" 200\n\t}\n'
            '\thandle {\n\t\trespond "ok" 200\n\t}\n}\n'
        )
        procs.append(
            subprocess.Popen(
                ["caddy", "run", "--config", str(d / "Caddyfile"), "--adapter", "caddyfile"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        wait(port)
        return port

    yield start
    for p in procs:
        p.terminate()
        p.wait(10)


@pytest.fixture
def nginx(tmp_path):
    if not shutil.which("nginx"):
        pytest.skip("nginx not installed")
    procs = []

    def start(block_loopback: bool) -> int:
        port = free_port()
        d: Path = tmp_path / f"nginx{port}"
        d.mkdir()
        (d / "n-antibot.conf").write_text(generate(cfg("nginx", block_loopback), fetch=no_fetch))
        (d / "nginx.conf").write_text(
            f"daemon off;\nworker_processes 1;\nerror_log {d}/error.log;\npid {d}/nginx.pid;\nevents {{}}\n"
            f"http {{\n\taccess_log {d}/access.log combined;\n\tinclude {d}/n-antibot.conf;\n"
            f"\tserver {{\n\t\tlisten 127.0.0.1:{port};\n\t\tif ($n_antibot_block) {{ return 444; }}\n"
            '\t\tlocation / { return 200 "ok"; }\n\t}\n}\n'
        )
        subprocess.run(["nginx", "-t", "-p", str(d), "-c", str(d / "nginx.conf")], check=True, capture_output=True)
        procs.append(subprocess.Popen(["nginx", "-p", str(d), "-c", str(d / "nginx.conf")], stderr=subprocess.DEVNULL))
        wait(port)
        return port

    yield start
    for p in procs:
        p.terminate()
        p.wait(10)


@pytest.mark.parametrize("server", ["caddy", "nginx"])
def test_agents(server, request):
    port = request.getfixturevalue(server)(False)
    assert get(port, "/", CHROME) == 200
    assert get(port, "/", GOOGLE) == 200
    assert get(port, "/", "curl/8.7.1") == 200
    assert get(port, "/", BYTESPIDER) == "closed"
    assert get(port, "/product/x/", BYTESPIDER) == "closed"
    assert get(port, "/media/a.jpg", "python-requests/2.32.3") == "closed"
    assert get(port, "/api/hook", "python-requests/2.32.3") == 200  # excluded path
    assert get(port, "/.well-known/acme-challenge/x", BYTESPIDER) in (200, 404)


@pytest.mark.parametrize("server", ["caddy", "nginx"])
def test_networks(server, request):
    port = request.getfixturevalue(server)(True)
    assert get(port, "/", CHROME) == "closed"
    assert get(port, "/product/x/", GOOGLE) == "closed"
    assert get(port, "/api/hook", CHROME) == 200


# ---------------------------------------------------------------- Apache
def _apache_binary() -> str | None:
    for name in ("httpd", "apache2"):
        for folder in ("/usr/sbin", "/usr/local/bin", "/opt/homebrew/bin"):
            if Path(folder, name).exists():
                return str(Path(folder, name))
    return shutil.which("httpd") or shutil.which("apache2")


def _apache_modules() -> Path | None:
    for folder in ("/usr/libexec/apache2", "/usr/lib/apache2/modules", "/usr/lib64/httpd/modules"):
        if Path(folder, "mod_rewrite.so").exists():
            return Path(folder)
    return None


@pytest.fixture
def apache(tmp_path):
    binary, modules = _apache_binary(), _apache_modules()
    if not binary or not modules:
        pytest.skip("apache not installed")
    procs = []

    def start(block_loopback: bool, htaccess: bool = False) -> int:
        port = free_port()
        d = tmp_path / f"apache{port}"
        for sub in ("www/api", "www/product", "www/.well-known"):
            (d / sub).mkdir(parents=True)
        for page in ("www/index.html", "www/api/hook", "www/product/index.html", "www/.well-known/x.txt"):
            (d / page).write_text("ok")
        rules = generate(cfg("apache", block_loopback), fetch=no_fetch)
        (d / "n-antibot.conf").write_text(rules)
        if htaccess:
            (d / "www/.htaccess").write_text(rules)
        load = "".join(
            f"LoadModule {m}_module {modules}/mod_{m}.so\n"
            for m in ("mpm_prefork", "unixd", "authz_core", "dir", "rewrite", "log_config")
            if (modules / f"mod_{m}.so").exists()
        )
        (d / "httpd.conf").write_text(
            f'ServerRoot "{d}"\nDefaultRuntimeDir "{d}"\nMutex file:{d} default\nPidFile "{d}/httpd.pid"\n'
            f'Listen 127.0.0.1:{port}\nServerName localhost\n{load}ErrorLog "{d}/error.log"\n'
            f'DocumentRoot "{d}/www"\nDirectoryIndex index.html\n'
            f'CustomLog "{d}/access.log" "%h %l %u %t \\"%r\\" %>s %b \\"%{{Referer}}i\\" \\"%{{User-Agent}}i\\""\n'
            f'<Directory "{d}/www">\n\tRequire all granted\n\tAllowOverride All\n</Directory>\n'
            + ("" if htaccess else f"<VirtualHost 127.0.0.1:{port}>\n\tInclude {d}/n-antibot.conf\n</VirtualHost>\n")
        )
        subprocess.run([binary, "-t", "-f", str(d / "httpd.conf")], check=True, capture_output=True)
        procs.append(
            subprocess.Popen(
                [binary, "-f", str(d / "httpd.conf"), "-DFOREGROUND"],
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # on shutdown Apache signals its whole process group
            )
        )
        wait(port)
        return port

    yield start
    for p in procs:
        p.terminate()
        p.wait(10)


@pytest.mark.parametrize("htaccess", [False, True], ids=["virtualhost", "htaccess"])
def test_apache_agents(apache, htaccess):
    port = apache(False, htaccess)
    assert get(port, "/", CHROME) == 200
    assert get(port, "/product/", GOOGLE) == 200
    assert get(port, "/", "curl/8.7.1") == 200
    assert get(port, "/", BYTESPIDER) == 403
    assert get(port, "/product/", BYTESPIDER) == 403
    assert get(port, "/missing.jpg", "python-requests/2.32.3") == 403
    assert get(port, "/api/hook", "python-requests/2.32.3") == 200
    assert get(port, "/.well-known/x.txt", BYTESPIDER) == 200


@pytest.mark.parametrize("htaccess", [False, True], ids=["virtualhost", "htaccess"])
def test_apache_networks(apache, htaccess):
    port = apache(True, htaccess)
    assert get(port, "/", CHROME) == 403
    assert get(port, "/product/", GOOGLE) == 403
    assert get(port, "/api/hook", CHROME) == 200


# ---------------------------------------------------------------- nftables (Linux with passwordless sudo, e.g. CI)
def _can_nft() -> bool:
    if not sys.platform.startswith("linux") or not shutil.which("nft"):
        return False
    return subprocess.run(["sudo", "-n", "nft", "list", "tables"], capture_output=True).returncode == 0


def _reachable(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), 2).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _can_nft(), reason="needs Linux, nft and passwordless sudo")
def test_nftables_drops_the_blocked_network(tmp_path):
    port = free_port()
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=tmp_path,
    )
    table = "n_antibot_test"
    rules = tmp_path / "n-antibot.nft"
    rules.write_text(
        generate(
            from_dict(
                {
                    "networks": {"presets": [], "block": ["127.0.0.0/8", "2001:db8::/32"], "allow": ["127.0.0.9/32"]},
                    "output": {"format": "nftables"},
                    "nftables": {"table": table, "ports": [port]},
                }
            ),
            fetch=no_fetch,
        )
    )
    try:
        wait(port)
        assert _reachable(port)
        subprocess.run(["sudo", "-n", "nft", "-c", "-f", str(rules)], check=True)
        subprocess.run(["sudo", "-n", "nft", "-f", str(rules)], check=True)
        subprocess.run(["sudo", "-n", "nft", "-f", str(rules)], check=True)  # loading twice replaces the table
        listed = subprocess.run(["sudo", "-n", "nft", "list", "table", "inet", table], capture_output=True, text=True)
        assert "2001:db8::/32" in listed.stdout and listed.stdout.count("chain prerouting") == 1
        assert not _reachable(port)
        subprocess.run(["sudo", "-n", "nft", "delete", "table", "inet", table], check=True)
        assert _reachable(port)
    finally:
        subprocess.run(["sudo", "-n", "nft", "delete", "table", "inet", table], capture_output=True)
        server.terminate()
        server.wait(10)


# ---------------------------------------------------------------- report from the logs each server really writes
@pytest.mark.parametrize("server", ["caddy", "nginx", "apache"])
def test_report_reads_real_access_logs(server, request, tmp_path):
    from n_antibot import report

    port = request.getfixturevalue(server)(False)
    get(port, "/?gclid=BOT-1", BYTESPIDER)
    get(port, "/product/?gclid=BOT-2&utm_medium=cpc", "python-requests/2.32.3")
    get(port, "/?gclid=HUMAN-1", CHROME)
    get(port, "/?msclkid=MS-1", CHROME)
    get(port, "/", GOOGLE)
    log = tmp_path / f"{server}{port}" / "access.log"
    for _ in range(50):  # servers flush their log a moment after answering
        if log.exists() and log.read_text().count("\n") >= 5:
            break
        time.sleep(0.1)

    config = cfg(server, False)
    classifier = report.Classifier.from_config(config, fetch_asn=lambda asn: [])
    rep = report.analyze(log.read_text().splitlines(), classifier)
    assert rep.requests == 5 and rep.lines == rep.parsed
    assert rep.bot_requests == 2 and rep.bot_cut == 2 and rep.bot_served == 0
    google = rep.clicks_by("google")
    assert google["total"] == 3 and google["agent"] == 2
    assert rep.clicks_by("microsoft")["total"] == 1
    bots = {c.click_id: c for c in rep.clicks if c.reason == "agent"}
    assert set(bots) == {"BOT-1", "BOT-2"} and all(c.cut for c in bots.values())
    assert bots["BOT-1"].first.ip == "127.0.0.1" and bots["BOT-1"].first.ts is not None

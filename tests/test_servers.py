"""End-to-end: start real Caddy and nginx with the generated snippet and send requests.

Skipped when the binaries are not installed. Loopback (127.0.0.1) is added to the blocked ranges so the network
block can be tested locally.
"""

import http.client
import shutil
import socket
import subprocess
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
            f":{port} {{\n\timport {d}/n-antibot.caddy\n"
            '\thandle /api/* {\n\t\trespond "api" 200\n\t}\n'
            '\thandle /producto/* {\n\t\trespond "producto" 200\n\t}\n'
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
            f"http {{\n\taccess_log off;\n\tinclude {d}/n-antibot.conf;\n"
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
    assert get(port, "/producto/x/", BYTESPIDER) == "closed"
    assert get(port, "/media/a.jpg", "python-requests/2.32.3") == "closed"
    assert get(port, "/api/hook", "python-requests/2.32.3") == 200  # excluded path
    assert get(port, "/.well-known/acme-challenge/x", BYTESPIDER) in (200, 404)


@pytest.mark.parametrize("server", ["caddy", "nginx"])
def test_networks(server, request):
    port = request.getfixturevalue(server)(True)
    assert get(port, "/", CHROME) == "closed"
    assert get(port, "/producto/x/", GOOGLE) == "closed"
    assert get(port, "/api/hook", CHROME) == 200

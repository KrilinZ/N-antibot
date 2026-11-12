"""`n-antibot install` against real servers: install, see the robot cut off, break it on purpose, uninstall."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

import pytest
from test_servers import BYTESPIDER, CHROME, _apache_binary, _apache_modules, free_port, get, no_fetch, wait

from n_antibot import generate, installer
from n_antibot.config import from_dict

SITE = "shop.example.test"


def snippet(fmt):
    cfg = from_dict({"networks": {"presets": [], "block": ["192.0.2.0/24"]}, "output": {"format": fmt}})
    return generate(cfg, fetch=no_fetch)


class Server:
    def __init__(self, tmp_path):
        self.d = tmp_path
        self.procs = []
        self.lines = []

    def say(self, text):
        self.lines.append(text)

    def stop(self):
        for p in self.procs:
            p.terminate()
            p.wait(10)


@pytest.fixture
def srv(tmp_path):
    s = Server(tmp_path)
    yield s
    s.stop()


def start_caddy(s):
    if not shutil.which("caddy"):
        pytest.skip("caddy not installed")
    port, admin = free_port(), free_port()
    conf = s.d / "Caddyfile"
    conf.write_text(
        f"{{\n\tauto_https off\n\tadmin localhost:{admin}\n}}\n"
        f"http://{SITE}:{port}, http://127.0.0.1:{port} {{\n"
        '\thandle /product/* {\n\t\trespond "product" 200\n\t}\n'
        '\thandle {\n\t\trespond "ok" 200\n\t}\n}\n'
    )
    s.procs.append(
        subprocess.Popen(
            ["caddy", "run", "--config", str(conf), "--adapter", "caddyfile"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    )
    wait(port)
    plan = installer.plan("caddy", conf, base_cmd=["caddy", "--address", f"localhost:{admin}"])
    return port, plan, f"http://{SITE}:{port}"


def start_nginx(s):
    if not shutil.which("nginx"):
        pytest.skip("nginx not installed")
    port = free_port()
    (s.d / "conf.d").mkdir()
    (s.d / "sites").mkdir()
    conf = s.d / "nginx.conf"
    conf.write_text(
        f"worker_processes 1;\nerror_log {s.d}/error.log;\npid {s.d}/nginx.pid;\nevents {{}}\n"
        f"http {{\n\taccess_log off;\n\tinclude {s.d}/conf.d/*.conf;\n\tinclude {s.d}/sites/*;\n}}\n"
    )
    site = s.d / "sites" / "shop"
    site.write_text(
        f"server {{\n    listen 127.0.0.1:{port};\n    server_name www.{SITE} {SITE};\n"
        '    location / { return 200 "ok"; }\n}\n'
    )
    base = ["nginx", "-c", str(conf), "-p", str(s.d)]
    s.procs.append(subprocess.Popen([*base, "-g", "daemon off;"], stderr=subprocess.DEVNULL))
    wait(port)
    plan = installer.plan("nginx", site, dest=s.d / "conf.d" / "n-antibot.conf", base_cmd=base)
    return port, plan, SITE


def start_apache(s):
    binary, modules = _apache_binary(), _apache_modules()
    if not binary or not modules:
        pytest.skip("apache not installed")
    port = free_port()
    (s.d / "www/product").mkdir(parents=True)
    (s.d / "sites").mkdir()
    for page in ("www/index.html", "www/product/index.html"):
        (s.d / page).write_text("ok")
    load = "".join(
        f"LoadModule {m}_module {modules}/mod_{m}.so\n"
        for m in ("mpm_prefork", "unixd", "authz_core", "dir", "rewrite")
        if (modules / f"mod_{m}.so").exists()
    )
    conf = s.d / "httpd.conf"
    conf.write_text(
        f'ServerRoot "{s.d}"\nDefaultRuntimeDir "{s.d}"\nMutex file:{s.d} default\nPidFile "{s.d}/httpd.pid"\n'
        f'Listen 127.0.0.1:{port}\n{load}ErrorLog "{s.d}/error.log"\nDirectoryIndex index.html\n'
        f'<Directory "{s.d}/www">\n\tRequire all granted\n</Directory>\nIncludeOptional {s.d}/sites/*.conf\n'
    )
    site = s.d / "sites" / "shop.conf"
    site.write_text(
        f'<VirtualHost 127.0.0.1:{port}>\n    ServerName {SITE}\n    DocumentRoot "{s.d}/www"\n</VirtualHost>\n'
    )
    base = [binary, "-f", str(conf)]
    s.procs.append(subprocess.Popen([*base, "-DFOREGROUND"], stderr=subprocess.DEVNULL, start_new_session=True))
    wait(port)
    plan = installer.plan("apache", site, dest=s.d / "n-antibot.conf", base_cmd=base)
    return port, plan, SITE


STARTERS = {"caddy": start_caddy, "nginx": start_nginx, "apache": start_apache}


def eventually(port, path, agent, expected):
    """nginx and Apache reload gracefully: old workers may answer for a moment."""
    seen = None
    for _ in range(40):
        seen = get(port, path, agent)
        if seen == expected:
            return True
        time.sleep(0.1)
    return seen == expected


@pytest.mark.parametrize("server", ["caddy", "nginx", "apache"])
def test_install_check_break_and_uninstall(server, srv):
    port, plan, site = STARTERS[server](srv)
    url = f"http://127.0.0.1:{port}"
    blocked = 403 if server == "apache" else "closed"
    before = plan.config.read_text()
    assert get(port, "/", BYTESPIDER) == 200

    # dry run: says what it would do and touches nothing
    installer.apply(plan, site, snippet(server), backup_dir=srv.d / "bk", dry_run=True, say=srv.say)
    assert plan.config.read_text() == before and not plan.dest.exists() and "dry run: nothing was changed" in srv.lines

    # install with the live check
    installer.apply(
        plan, site, snippet(server), backup_dir=srv.d / "bk", check_url=url, blocked_agent="Bytespider", say=srv.say
    )
    assert srv.lines[-1] == f"installed: {site} is protected"
    assert get(port, "/", CHROME) == 200 and get(port, "/", BYTESPIDER) == blocked
    assert get(port, "/product/", BYTESPIDER) == blocked
    assert plan.config.read_text().count(plan.line) == 1 and (srv.d / "bk").is_dir()

    # installing again only refreshes the lists
    installer.apply(plan, site, snippet(server), backup_dir=srv.d / "bk", say=srv.say)
    assert plan.config.read_text().count(plan.line) == 1
    assert "the configuration already has the line: only the lists are updated" in srv.lines
    assert eventually(port, "/", BYTESPIDER, blocked)

    # a broken file is rejected by the server's own checker and everything is put back
    good = plan.dest.read_text()
    with pytest.raises(installer.InstallError, match="rejected the configuration"):
        installer.apply(plan, site, "this is { not valid", backup_dir=srv.d / "bk", say=srv.say)
    assert plan.dest.read_text() == good and get(port, "/", BYTESPIDER) == blocked and get(port, "/", CHROME) == 200

    # a failed live check rolls back too (the robot we expect to be cut is not in the lists)
    with pytest.raises(installer.InstallError, match="live check"):
        installer.apply(
            plan,
            site,
            snippet(server),
            backup_dir=srv.d / "bk",
            check_url=url,
            blocked_agent="NotInTheList",
            say=srv.say,
        )
    assert get(port, "/", BYTESPIDER) == blocked

    # uninstall: the configuration is exactly as it was
    installer.apply(plan, site, None, backup_dir=srv.d / "bk", uninstall=True, say=srv.say)
    assert plan.config.read_text() == before and not plan.dest.exists()
    assert eventually(port, "/", BYTESPIDER, 200)
    installer.apply(plan, site, None, backup_dir=srv.d / "bk", uninstall=True, say=srv.say)
    assert srv.lines[-1] == "nothing to remove: n-antibot is not installed here"


def test_finds_the_site_in_each_kind_of_configuration(tmp_path):
    caddy = tmp_path / "Caddyfile"
    caddy.write_text("other.test {\n}\nshop.example.test, www.shop.example.test {\n\trespond ok\n}\n")
    nginx = tmp_path / "nginx-site"
    nginx.write_text("server {\n  server_name www.shop.example.test shop.example.test;\n}\n")
    apache = tmp_path / "vhost.conf"
    apache.write_text("<VirtualHost *:443>\n  ServerName shop.example.test\n</VirtualHost>\n")
    for server, f in (("caddy", caddy), ("nginx", nginx), ("apache", apache)):
        assert installer.find_config(server, "shop.example.test", [str(tmp_path / "*")]) == f
        assert installer.find_config(server, "example.test", [str(tmp_path / "*")]) is None  # no partial matches
    assert installer.find_config("nginx", "www.shop.example.test", [str(nginx)]) == nginx
    assert installer.find_config("caddy", "www.shop.example.test", [str(caddy)]) is None  # not the first address


def test_refuses_what_it_cannot_do_safely(tmp_path):
    conf = tmp_path / "Caddyfile"
    conf.write_text("other.test {\n}\n")
    plan = installer.plan("caddy", conf)
    with pytest.raises(installer.InstallError, match=r"no declaration of shop\.example\.test"):
        installer.apply(plan, SITE, "x", backup_dir=tmp_path / "bk", say=lambda t: None)
    with pytest.raises(installer.InstallError, match="generated file is empty"):
        installer.apply(plan, SITE, "", backup_dir=tmp_path / "bk", say=lambda t: None)
    with pytest.raises(installer.InstallError, match="no configuration file"):
        installer.apply(installer.plan("caddy", tmp_path / "missing"), SITE, "x", backup_dir=tmp_path, say=print)
    assert conf.read_text() == "other.test {\n}\n" and not (tmp_path / "bk").exists()


def _can_nft():
    if not sys.platform.startswith("linux") or not shutil.which("nft"):
        return False
    return subprocess.run(["sudo", "-n", "nft", "list", "tables"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _can_nft(), reason="needs Linux, nft and passwordless sudo")
def test_nftables_install_and_uninstall(tmp_path):
    cfg = from_dict(
        {
            "networks": {"presets": [], "block": ["192.0.2.0/24"]},
            "output": {"format": "nftables"},
            "nftables": {"table": "n_antibot_install_test"},
        }
    )
    lines = []
    dest = tmp_path / "n-antibot.nft"
    nft = ["sudo", "-n", "nft"]
    try:
        installer.apply_nftables(
            generate(cfg, fetch=no_fetch), cfg.nftables_table, dest, nft=nft, dry_run=True, say=lines.append
        )
        assert not dest.exists() and "the rules are valid" in lines[-1]
        installer.apply_nftables(generate(cfg, fetch=no_fetch), cfg.nftables_table, dest, nft=nft, say=lines.append)
        listed = subprocess.run([*nft, "list", "table", "inet", cfg.nftables_table], capture_output=True, text=True)
        assert "192.0.2.0/24" in listed.stdout and dest.exists()
        with pytest.raises(installer.InstallError, match="nft rejected"):
            installer.apply_nftables("table inet broken {", cfg.nftables_table, dest, nft=nft, say=lines.append)
        installer.apply_nftables("", cfg.nftables_table, dest, nft=nft, uninstall=True, say=lines.append)
        assert subprocess.run([*nft, "list", "table", "inet", cfg.nftables_table], capture_output=True).returncode != 0
        assert not dest.exists()
    finally:
        subprocess.run([*nft, "delete", "table", "inet", cfg.nftables_table], capture_output=True)


def test_cli_install_dry_run_uninstall_and_errors(tmp_path, monkeypatch, capsys):
    import n_antibot.cli as cli
    from n_antibot.cli import main
    from n_antibot.core import blocklist

    monkeypatch.setattr(cli, "blocklist", lambda cfg: blocklist(cfg, fetch=lambda asns, **_: ["43.173.0.0/16"]))
    conf = tmp_path / "Caddyfile"
    conf.write_text("shop.example.test {\n\trespond ok\n}\n")
    args = ["install", "caddy", "--site", SITE, "--config-file", str(conf), "--backup-dir", str(tmp_path / "bk")]
    assert main([*args, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "add 1 line: import" in out and "dry run: nothing was changed" in out and out.isascii()
    assert conf.read_text() == "shop.example.test {\n\trespond ok\n}\n" and not (tmp_path / "bk").exists()
    assert main([*args, "--uninstall"]) == 0 and "nothing to remove" in capsys.readouterr().out
    assert main(["install", "caddy", "--site", "nope.test", "--config-file", str(conf)]) == 5
    assert "no declaration of nope.test" in capsys.readouterr().err
    assert main(["install", "caddy"]) == 3 and "--site is required" in capsys.readouterr().err
    assert main(["install", "--site", "nowhere.invalid"]) == 3
    assert "no Caddy, nginx or Apache configuration" in capsys.readouterr().err

"""`n-antibot install`: put the generated file in place for Caddy, nginx, Apache or nftables, safely.

Every installer follows the same steps and undoes everything if one fails:
  1. back up the files it is going to touch,
  2. write the generated file,
  3. add one line to the site's configuration (once),
  4. validate with the server's own checker,
  5. reload,
  6. optionally check the live site: a browser and Googlebot get an answer, a blocked robot does not.
"""

from __future__ import annotations

import glob
import http.client
import re
import shutil
import ssl
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

MARK = "# n-antibot:"
CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


class InstallError(Exception):
    """Nothing was left changed: the message says what failed."""


@dataclass
class Plan:
    """What an installer needs to know about one server."""

    server: str
    config: Path  # the file that gets the one-line change
    dest: Path  # where the generated file goes
    line: str  # the line added to the configuration
    validate: list[str]
    reload: list[str]
    blocked_status: tuple = ("closed",)  # what a blocked robot sees
    notes: list[str] = field(default_factory=list)


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        return 127, f"{cmd[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(cmd)}: timed out"
    return p.returncode, (p.stdout + p.stderr).strip()


def fetch_status(url: str, user_agent: str, timeout: float = 20) -> int | str:
    """HTTP status of a GET, or 'closed' when the server drops the connection without answering."""
    u = urlsplit(url)
    cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    kwargs = {"context": ssl.create_default_context()} if u.scheme == "https" else {}
    conn = cls(u.hostname, u.port, timeout=timeout, **kwargs)
    try:
        conn.request("GET", u.path or "/", headers={"User-Agent": user_agent, "Accept": "*/*"})
        return conn.getresponse().status
    except (http.client.HTTPException, ConnectionError, ssl.SSLError, TimeoutError, OSError):
        return "closed"
    finally:
        conn.close()


def live_check(url: str, blocked_agent: str | None, blocked_status: tuple, say: Callable[[str], None]) -> int:
    """Returns the number of failed checks."""
    fails = 0
    for label, agent in (("browser", CHROME), ("Googlebot", GOOGLEBOT), ("curl", "curl/8.7.1")):
        status = fetch_status(url, agent)
        ok = status != "closed" and status != 403
        say(f"{'ok  ' if ok else 'FAIL'} {label:<10} -> {status}")
        fails += not ok
    if blocked_agent:
        status = fetch_status(url, f"Mozilla/5.0 (compatible; {blocked_agent}/1.0)")
        ok = status in blocked_status
        expected = " or ".join(map(str, blocked_status))
        say(f"{'ok  ' if ok else 'FAIL'} {blocked_agent:<10} -> {status} (expected {expected})")
        fails += not ok
    return fails


# ------------------------------------------------------------------------------------------------- finding the site
def _site_line(server: str, site: str) -> re.Pattern[str]:
    s = re.escape(site)
    if server == "caddy":
        return re.compile(rf"^{s}([ ,][^{{]*)? *\{{\s*$")
    if server == "nginx":
        return re.compile(rf"^\s*server_name\s+([^;]*\s)?{s}(\s[^;]*)?;", re.I)
    return re.compile(rf"^\s*Server(Name|Alias)\s+(\S+\s+)*{s}(\s|$)", re.I)


SEARCH = {
    "caddy": ["/etc/caddy/Caddyfile"],
    "nginx": ["/etc/nginx/sites-enabled/*", "/etc/nginx/conf.d/*.conf", "/etc/nginx/nginx.conf"],
    "apache": [
        "/etc/apache2/sites-enabled/*.conf",
        "/etc/httpd/conf.d/*.conf",
        "/etc/httpd/conf/httpd.conf",
        "/etc/apache2/httpd.conf",
    ],
}


def find_config(server: str, site: str, patterns: list[str] | None = None) -> Path | None:
    """The configuration file that declares this site, or None."""
    rx = _site_line(server, site)
    for pattern in patterns or SEARCH[server]:
        for name in sorted(glob.glob(pattern)):
            try:
                text = Path(name).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if any(rx.match(line) for line in text.splitlines()):
                return Path(name)
    return None


def detect(site: str) -> list[tuple[str, Path]]:
    """Servers on this machine whose configuration declares the site: [(server, config file)]."""
    found = []
    for server in ("caddy", "nginx", "apache"):
        config = find_config(server, site)
        if config:
            found.append((server, config))
    return found


def _apache_cmd() -> list[str]:
    for name in ("apache2ctl", "apachectl", "httpd", "apache2"):
        if shutil.which(name):
            return [name]
    return ["apachectl"]


def plan(
    server: str, config: Path, *, prefix: str = "n_antibot", dest: Path | None = None, base_cmd: list[str] | None = None
) -> Plan:
    """The standard plan for a server. `base_cmd` replaces the server command (tests, containers, custom paths)."""
    if server == "caddy":
        dest = dest or config.parent / "n-antibot.caddy"
        cmd = base_cmd or ["caddy"]
        return Plan(
            "caddy",
            config,
            dest,
            f"import {dest}",
            [*cmd[:1], "validate", "--config", "{config}", "--adapter", "caddyfile"],
            [*cmd[:1], "reload", "--config", "{config}", "--adapter", "caddyfile", *cmd[1:]],
        )
    if server == "nginx":
        dest = dest or Path("/etc/nginx/conf.d/n-antibot.conf")
        cmd = base_cmd or ["nginx"]
        return Plan(
            "nginx",
            config,
            dest,
            f"if (${prefix}_block) {{ return 444; }}",
            [*cmd, "-t"],
            [*cmd, "-s", "reload"],
            notes=[f"{dest} must be included inside http {{ }} (conf.d is, on Debian, Ubuntu and RHEL)."],
        )
    if server == "apache":
        dest = dest or config.parent.parent / "n-antibot.conf"
        cmd = base_cmd or _apache_cmd()
        return Plan(
            "apache", config, dest, f"Include {dest}", [*cmd, "-t"], [*cmd, "-k", "graceful"], blocked_status=(403,)
        )
    raise InstallError(f"unknown server {server!r}")


# ------------------------------------------------------------------------------------------------- the common steps
def _with_line(text: str, p: Plan, site: str) -> tuple[str, int]:
    """Configuration with the plan's line added right after each declaration of the site. Returns (text, added)."""
    rx = _site_line(p.server, site)
    out, added = [], 0
    lines = text.split("\n")
    for i, line in enumerate(lines):
        out.append(line)
        if rx.match(line):
            nxt = "\n".join(lines[i + 1 : i + 3])
            if p.line in nxt:
                continue
            indent = "\t" if p.server == "caddy" else (re.match(r"\s*", line).group(0) or "\t")
            out.append(f"{indent}{MARK} blocks bot networks and scrapers. To remove it, delete this line and the next.")
            out.append(f"{indent}{p.line}")
            added += 1
    return "\n".join(out), added


def _without_line(text: str, p: Plan) -> str:
    return "\n".join(line for line in text.split("\n") if line.strip() != p.line and not line.strip().startswith(MARK))


def apply(
    p: Plan,
    site: str,
    snippet: str | None,
    *,
    backup_dir: Path,
    check_url: str | None = None,
    blocked_agent: str | None = None,
    uninstall: bool = False,
    dry_run: bool = False,
    say: Callable[[str], None] = print,
) -> None:
    """Install (or uninstall) following the plan. Raises InstallError after putting everything back."""
    if not p.config.is_file():
        raise InstallError(f"no configuration file at {p.config}")
    original = p.config.read_text(encoding="utf-8")
    if uninstall:
        changed, added = _without_line(original, p), 0
        if changed == original and not p.dest.exists():
            say("nothing to remove: n-antibot is not installed here")
            return
    else:
        if not snippet:
            raise InstallError("nothing to install: the generated file is empty")
        changed, added = _with_line(original, p, site)
        if added == 0 and p.line not in original:
            raise InstallError(f"no declaration of {site} found in {p.config}")

    say(f"server: {p.server}, configuration: {p.config}, file: {p.dest}")
    for note in p.notes:
        say(f"note: {note}")
    if uninstall:
        say(f"remove the line: {p.line}")
    elif added:
        say(f"add {added} line{'s' if added > 1 else ''}: {p.line}")
    else:
        say("the configuration already has the line: only the lists are updated")
    if dry_run:
        say("dry run: nothing was changed")
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p.config, backup / p.config.name)
    had_dest = p.dest.exists()
    if had_dest:
        shutil.copy2(p.dest, backup / (p.dest.name + ".before"))
    say(f"backup in {backup}")

    def restore() -> None:
        shutil.copy2(backup / p.config.name, p.config)
        if had_dest:
            shutil.copy2(backup / (p.dest.name + ".before"), p.dest)
        else:
            p.dest.unlink(missing_ok=True)
        _run([a.replace("{config}", str(p.config)) for a in p.reload])
        say("restored the previous configuration")

    try:
        if not uninstall:
            p.dest.parent.mkdir(parents=True, exist_ok=True)
            p.dest.write_text(snippet or "", encoding="utf-8")
            p.dest.chmod(0o644)
        p.config.write_text(changed, encoding="utf-8")
        code, output = _run([a.replace("{config}", str(p.config)) for a in p.validate])
        if code != 0:
            raise InstallError(f"{p.server} rejected the configuration:\n{output[-800:]}")
        code, output = _run([a.replace("{config}", str(p.config)) for a in p.reload])
        if code != 0:
            raise InstallError(f"{p.server} could not reload:\n{output[-800:]}")
        say(f"{p.server} reloaded")
        if uninstall:
            p.dest.unlink(missing_ok=True)
            say("uninstalled")
            return
        if check_url:
            time.sleep(1.5)
            fails = live_check(check_url.rstrip("/") + "/", blocked_agent, p.blocked_status, say)
            if fails:
                raise InstallError(f"{fails} live check{'s' if fails > 1 else ''} failed")
    except InstallError:
        restore()
        raise
    except OSError as e:
        restore()
        raise InstallError(f"{e.filename or ''}: {e.strerror or e} (are you root?)") from e
    say(f"installed: {site} is protected")


def apply_nftables(
    snippet: str,
    table: str,
    dest: Path,
    *,
    nft: list[str] | None = None,
    uninstall: bool = False,
    dry_run: bool = False,
    say: Callable[[str], None] = print,
) -> None:
    """Load (or remove) the nftables table. The file is checked with `nft -c` before anything is applied."""
    nft = nft or ["nft"]
    if uninstall:
        if dry_run:
            say(f"dry run: would delete table inet {table} and {dest}")
            return
        _run([*nft, "delete", "table", "inet", table])
        dest.unlink(missing_ok=True)
        say("uninstalled")
        return
    tmp = dest.with_suffix(dest.suffix + ".new")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(snippet, encoding="utf-8")
    except OSError as e:
        raise InstallError(f"{e.filename or ''}: {e.strerror or e} (are you root?)") from e
    code, output = _run([*nft, "-c", "-f", str(tmp)])
    if code != 0:
        tmp.unlink(missing_ok=True)
        raise InstallError(f"nft rejected the rules:\n{output[-800:]}")
    if dry_run:
        tmp.unlink(missing_ok=True)
        say(f"dry run: the rules are valid; nothing was loaded (would write {dest})")
        return
    code, output = _run([*nft, "-f", str(tmp)])
    if code != 0:
        tmp.unlink(missing_ok=True)
        raise InstallError(f"nft could not load the rules:\n{output[-800:]}")
    tmp.replace(dest)
    say(f"loaded table inet {table} from {dest}")
    say(f"to keep it after a reboot, include {dest} from /etc/nftables.conf")

"""Configuration: a small TOML file, strictly validated. Every key is optional."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10
    import tomli as tomllib

from .presets import NETWORK_PRESETS, PROTECTED_AGENTS, ROBOT_PRESETS, default_names

FORMATS = ("caddy", "nginx", "apache", "nftables", "cloudflare", "json")
ASN_RE = re.compile(r"^AS\d{1,10}$")
# Letters, digits, "_" and "-" only: safe inside an RE2 (Caddy) and a PCRE (nginx) regex without escaping.
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")
# Caddy path matchers: exact (/robots.txt), prefix (/api/*) or suffix (*.php). Same three forms are rendered for nginx.
PATH_RE = re.compile(r"^(/[A-Za-z0-9._~%!$&'()+,;=:@/-]*\*?|\*\.[A-Za-z0-9]+)$")
IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")


class ConfigError(ValueError):
    """The configuration is not valid. The message says which key and why."""


@dataclass(frozen=True)
class Config:
    network_presets: tuple[str, ...] = field(default_factory=lambda: default_names(NETWORK_PRESETS))
    asns: tuple[str, ...] = ()
    block_cidrs: tuple[str, ...] = ()
    allow_cidrs: tuple[str, ...] = ()
    robot_presets: tuple[str, ...] = field(default_factory=lambda: default_names(ROBOT_PRESETS))
    block_agents: tuple[str, ...] = ()
    allow_agents: tuple[str, ...] = ()
    exclude_paths: tuple[str, ...] = ("/.well-known/*",)
    format: str = "caddy"
    caddy_prefix: str = "nAntibot"
    caddy_block_path: str = "/__n_antibot_blocked"
    caddy_ip_matcher: str = "remote_ip"
    nginx_prefix: str = "n_antibot"
    nftables_table: str = "n_antibot"
    nftables_ports: tuple[int, ...] = (80, 443)
    # Data-center networks used to judge PAID AD CLICKS only (the report always uses them; `ads_cut` also cuts them).
    ads_presets: tuple[str, ...] = field(default_factory=lambda: tuple(NETWORK_PRESETS))
    ads_asns: tuple[str, ...] = ()
    ads_cut: bool = False

    # ---- derived lists -------------------------------------------------------------------------------------------
    def all_asns(self) -> tuple[str, ...]:
        out: list[str] = []
        for name in self.network_presets:
            out += NETWORK_PRESETS[name].members
        out += self.asns
        return tuple(dict.fromkeys(a.upper() for a in out))

    def ads_asn_list(self) -> tuple[str, ...]:
        """ASNs whose ad clicks count as bots: the ads lists, minus the networks that are blocked for everything."""
        out: list[str] = []
        for name in self.ads_presets:
            out += NETWORK_PRESETS[name].members
        out += self.ads_asns
        blocked = set(self.all_asns())
        return tuple(dict.fromkeys(a.upper() for a in out if a.upper() not in blocked))

    def agents(self) -> tuple[str, ...]:
        out: list[str] = []
        for name in self.robot_presets:
            out += ROBOT_PRESETS[name].members
        out += self.block_agents
        drop = {a.lower() for a in self.allow_agents}
        return tuple(dict.fromkeys(a for a in out if a.lower() not in drop))

    def blocks_agent(self, user_agent: str) -> str | None:
        """Return the fragment that would block this User-Agent, or None."""
        low = user_agent.lower()
        return next((a for a in self.agents() if a.lower() in low), None)

    # ---- validation ----------------------------------------------------------------------------------------------
    def validate(self) -> Config:
        for name in self.network_presets:
            if name not in NETWORK_PRESETS:
                raise ConfigError(f"networks.presets: unknown preset {name!r} (known: {', '.join(NETWORK_PRESETS)})")
        for name in self.robot_presets:
            if name not in ROBOT_PRESETS:
                raise ConfigError(f"robots.presets: unknown preset {name!r} (known: {', '.join(ROBOT_PRESETS)})")
        for a in self.asns:
            if not ASN_RE.match(a.upper()):
                raise ConfigError(f"networks.asns: {a!r} is not an ASN like 'AS132203'")
        for name in self.ads_presets:
            if name not in NETWORK_PRESETS:
                raise ConfigError(f"ads.networks: unknown preset {name!r} (known: {', '.join(NETWORK_PRESETS)})")
        for a in self.ads_asns:
            if not ASN_RE.match(a.upper()):
                raise ConfigError(f"ads.asns: {a!r} is not an ASN like 'AS16509'")
        if self.ads_cut and self.format == "nftables":
            raise ConfigError("ads.cut needs the URL of the request: a firewall (nftables) cannot see it")
        for key, cidrs in (("networks.block", self.block_cidrs), ("networks.allow", self.allow_cidrs)):
            for c in cidrs:
                try:
                    ipaddress.ip_network(c, strict=False)
                except ValueError as e:
                    raise ConfigError(f"{key}: {c!r} is not an IP range: {e}") from None
        for key, agents in (("robots.block", self.block_agents), ("robots.allow", self.allow_agents)):
            for a in agents:
                if not AGENT_RE.match(a):
                    raise ConfigError(
                        f"{key}: {a!r} must be 3-64 characters of letters, digits, '_' or '-' (no regex, no spaces)"
                    )
        for p in self.exclude_paths:
            if not PATH_RE.match(p) or "*" in p[1:-1]:
                raise ConfigError(f"paths.exclude: {p!r} must be '/exact', '/prefix/*' or '*.ext'")
        if self.format not in FORMATS:
            raise ConfigError(f"output.format: {self.format!r} must be one of {', '.join(FORMATS)}")
        if not IDENT_RE.match(self.caddy_prefix):
            raise ConfigError(f"caddy.prefix: {self.caddy_prefix!r} must be letters, digits or '_'")
        if not IDENT_RE.match(self.nginx_prefix):
            raise ConfigError(f"nginx.prefix: {self.nginx_prefix!r} must be letters, digits or '_'")
        if not IDENT_RE.match(self.nftables_table):
            raise ConfigError(f"nftables.table: {self.nftables_table!r} must be letters, digits or '_'")
        if not self.nftables_ports or not all(0 < p < 65536 for p in self.nftables_ports):
            raise ConfigError("nftables.ports must be a non-empty list of ports between 1 and 65535")
        if self.format == "nftables" and not self.all_asns() and not self.block_cidrs:
            raise ConfigError("output.format 'nftables' only blocks networks, and every network list is empty")
        if not re.match(r"^/[A-Za-z0-9_-]+$", self.caddy_block_path):
            raise ConfigError(f"caddy.block_path: {self.caddy_block_path!r} must look like '/__n_antibot_blocked'")
        if self.caddy_ip_matcher not in ("remote_ip", "client_ip"):
            raise ConfigError("caddy.ip_matcher must be 'remote_ip' or 'client_ip'")
        nothing = not self.all_asns() and not self.block_cidrs and not self.agents()
        if nothing and not (self.ads_cut and self.ads_asn_list()):
            raise ConfigError("nothing to block: every network and robot list is empty")
        for ua in PROTECTED_AGENTS:
            hit = self.blocks_agent(ua)
            if hit:
                raise ConfigError(f"robots: {hit!r} would block a real browser or search engine: {ua!r}")
        return self


_SCHEMA: dict[str, dict[str, str]] = {
    "networks": {"presets": "network_presets", "asns": "asns", "block": "block_cidrs", "allow": "allow_cidrs"},
    "robots": {"presets": "robot_presets", "block": "block_agents", "allow": "allow_agents"},
    "paths": {"exclude": "exclude_paths"},
    "output": {"format": "format"},
    "caddy": {"prefix": "caddy_prefix", "block_path": "caddy_block_path", "ip_matcher": "caddy_ip_matcher"},
    "nginx": {"prefix": "nginx_prefix"},
    "nftables": {"table": "nftables_table", "ports": "nftables_ports"},
    "ads": {"networks": "ads_presets", "asns": "ads_asns", "cut": "ads_cut"},
}
_STRINGS = {"format", "caddy_prefix", "caddy_block_path", "caddy_ip_matcher", "nginx_prefix", "nftables_table"}
_INTS = {"nftables_ports"}
_BOOLS = {"ads_cut"}


def from_dict(data: dict[str, Any]) -> Config:
    """Build and validate a Config from parsed TOML. Unknown sections or keys are errors (typos must not pass)."""
    values: dict[str, Any] = {}
    for section, body in data.items():
        if section not in _SCHEMA:
            raise ConfigError(f"unknown section [{section}] (known: {', '.join(_SCHEMA)})")
        if not isinstance(body, dict):
            raise ConfigError(f"[{section}] must be a table")
        for key, value in body.items():
            if key not in _SCHEMA[section]:
                raise ConfigError(f"unknown key {section}.{key} (known: {', '.join(_SCHEMA[section])})")
            attr = _SCHEMA[section][key]
            if attr in _STRINGS:
                if not isinstance(value, str):
                    raise ConfigError(f"{section}.{key} must be a string")
                values[attr] = value
            elif attr in _BOOLS:
                if not isinstance(value, bool):
                    raise ConfigError(f"{section}.{key} must be true or false")
                values[attr] = value
            elif attr in _INTS:
                if not isinstance(value, list) or not all(type(v) is int for v in value):
                    raise ConfigError(f"{section}.{key} must be a list of integers")
                values[attr] = tuple(value)
            else:
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ConfigError(f"{section}.{key} must be a list of strings")
                values[attr] = tuple(v.strip() for v in value)
    return replace(Config(), **values).validate()


def load(path: str | Path | None) -> Config:
    """Load a TOML file, or the defaults when path is None."""
    if path is None:
        return Config().validate()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror}") from None
    return from_dict(data)

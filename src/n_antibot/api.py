"""Read-only HTTP API over the same data as `n-antibot report`: `n-antibot serve`.

Standard library only. JSON in, JSON out. GET requests never change anything. It listens on 127.0.0.1 unless told
otherwise, and refuses to listen on any other address without a token.
"""

from __future__ import annotations

import glob
import hmac
import io
import ipaddress
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from . import __version__, claims, ranges, report
from .config import Config
from .render import Blocklist
from .render import as_json as render_json

MAX_LIMIT = 1000
VERDICTS = ("bot", "suspicious", "clean", "all")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _day(name: str, text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise ApiError(400, "invalid_parameter", f"{name} must be a date like 2026-11-12") from None


def _int(name: str, text: str | None, default: int, low: int, high: int) -> int:
    if text is None:
        return default
    try:
        value = int(text)
    except ValueError:
        raise ApiError(400, "invalid_parameter", f"{name} must be a whole number") from None
    if not low <= value <= high:
        raise ApiError(400, "invalid_parameter", f"{name} must be between {low} and {high}")
    return value


class Service:
    """The data behind the API, with small caches so that a dashboard polling it does not re-read everything."""

    def __init__(
        self,
        cfg: Config,
        logs: list[str],
        *,
        fetch_asn: Callable[[str], list[str]] | None = None,
        ranges_ttl: float = 24 * 3600,
        clock: Callable[[], float] = time.time,
    ):
        self.cfg, self.patterns = cfg, list(logs)
        self._fetch_asn, self._ttl, self._clock = fetch_asn, ranges_ttl, clock
        self._lock = threading.Lock()
        self._classifier: report.Classifier | None = None
        self._labelled: list[tuple[str, str]] = []
        self._fetched_at = 0.0
        self._reports: dict[tuple, report.Report] = {}

    # ---- blocked ranges: refreshed every `ranges_ttl`; a failed refresh keeps the previous lists -------------------
    def classifier(self) -> report.Classifier:
        with self._lock:
            stale = self._classifier is None or self._clock() - self._fetched_at > self._ttl
            if stale:
                try:
                    fetch = self._fetch_asn or ranges.fetch_asn_cached
                    labelled: list[tuple[str, str]] = []
                    for asn in (*self.cfg.all_asns(), *self.cfg.ads_asn_list()):
                        labelled += [(asn, p) for p in fetch(asn)]
                    self._labelled = labelled
                    self._classifier = report.Classifier.from_config(
                        self.cfg, fetch_asn=lambda a: [p for x, p in labelled if x == a]
                    )
                    self._fetched_at = self._clock()
                    self._reports.clear()
                except Exception as e:
                    if self._classifier is None:
                        raise ApiError(503, "ranges_unavailable", f"could not download the network ranges: {e}") from e
                    self._fetched_at = self._clock() - self._ttl + 600  # keep the old lists, retry in ten minutes
            return self._classifier  # type: ignore[return-value]

    def log_files(self) -> list[str]:
        files: list[str] = []
        for pattern in self.patterns:
            files += sorted(glob.glob(pattern)) or ([pattern] if os.path.exists(pattern) else [])
        return list(dict.fromkeys(files))

    def report(self, since: datetime | None, until: datetime | None) -> report.Report:
        classifier = self.classifier()
        files = self.log_files()
        if not files:
            raise ApiError(503, "no_logs", "no access log found: check the files given to `n-antibot serve`")
        try:
            signature = tuple((f, os.path.getmtime(f), os.path.getsize(f)) for f in files)
        except OSError as e:
            raise ApiError(503, "no_logs", f"cannot read {e.filename}: {e.strerror}") from e
        key = (signature, since, until)
        with self._lock:
            if key in self._reports:
                return self._reports[key]
        try:
            rep = report.analyze(
                report.read_logs(files), classifier, since=since, until=until + timedelta(days=1) if until else None
            )
        except OSError as e:
            raise ApiError(503, "no_logs", f"cannot read {e.filename}: {e.strerror}") from e
        with self._lock:
            if len(self._reports) > 32:
                self._reports.clear()
            self._reports[key] = rep
        return rep

    # ---- endpoints -------------------------------------------------------------------------------------------------
    def summary(self, q: dict[str, str]) -> dict[str, Any]:
        rep = self.report(_day("since", q.get("since")), _day("until", q.get("until")))
        return report.as_dict(rep)

    def bots(self, q: dict[str, str]) -> dict[str, Any]:
        data = self.summary(q)
        return {
            "period": data["period"],
            "total_requests": data["requests"],
            **data["bots"],
            "top_unblocked": data["top_unblocked"],
        }

    def _clicks(self, q: dict[str, str]) -> tuple[report.Report, list[report.AdClick]]:
        verdict = q.get("verdict", "all")
        if verdict not in VERDICTS:
            raise ApiError(400, "invalid_parameter", f"verdict must be one of {', '.join(VERDICTS)}")
        rep = self.report(_day("since", q.get("since")), _day("until", q.get("until")))
        rows = [
            c
            for c in rep.clicks
            if verdict in ("all", report.click_verdict(c)) and q.get("platform") in (None, c.platform)
        ]
        return rep, rows

    def ad_clicks(self, q: dict[str, str]) -> dict[str, Any]:
        limit = _int("limit", q.get("limit"), 100, 1, MAX_LIMIT)
        offset = _int("offset", q.get("offset"), 0, 0, 10**9)
        rep, rows = self._clicks(q)
        return {
            "period": report.as_dict(rep)["period"],
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "clicks": [report.click_dict(c) for c in rows[offset : offset + limit]],
        }

    def ad_clicks_csv(self, q: dict[str, str]) -> str:
        _, rows = self._clicks(q)
        only = report.Report(clicks=rows)
        out = io.StringIO()
        report.write_csv(only, out, include_clean=True)
        return out.getvalue()

    def claims(self, q: dict[str, str]) -> dict[str, Any]:
        """Where to dispute invalid clicks on each platform, with this period's flagged clicks per platform."""
        rep = self.report(_day("since", q.get("since")), _day("until", q.get("until")))
        now = datetime.fromtimestamp(self._clock(), tz=timezone.utc)
        out = []
        known = [p["platform"] for p in claims.as_dict()]
        for key in [*known, *[p for p in rep.platforms() if p not in known]]:
            p = claims.info(key)
            rows = [c for c in rep.clicks if c.platform == key]
            flagged = [c for c in rows if c.reason]
            inside = [c for c in flagged if claims._within(c, p, now) != "no"]
            out.append(
                {
                    "platform": key,
                    "name": p.name,
                    "has_process": p.has_process,
                    "where": p.where,
                    "url": p.url or None,
                    "deadline_days": p.window_days,
                    "asks": list(p.asks),
                    "outcome": p.outcome,
                    "source": p.source or None,
                    "checked": p.checked,
                    "clicks": len(rows),
                    "bot_clicks": sum(c.reason in report.BOT_REASONS for c in rows),
                    "suspicious_clicks": sum(c.reason in ("repeated", "no-resources") for c in rows),
                    "flagged_within_deadline": len(inside),
                }
            )
        return {"period": report.as_dict(rep)["period"], "platforms": out}

    def check(self, q: dict[str, str]) -> dict[str, Any]:
        ip, ua, path = q.get("ip", ""), q.get("user_agent", ""), q.get("path", "/")
        if not ip and not ua:
            raise ApiError(400, "invalid_parameter", "give ip, user_agent or both")
        if ip:
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                raise ApiError(400, "invalid_parameter", "ip is not an IP address") from None
        verdict = self.classifier().verdict(ip, ua)
        excluded = _excluded(self.cfg, path)
        return {
            "ip": ip or None,
            "user_agent": ua or None,
            "path": path,
            "is_bot": verdict is not None,
            "reason": verdict[0] if verdict else None,
            "match": verdict[1] if verdict else None,
            "path_excluded": excluded,
            "would_block": verdict is not None and not excluded,
        }

    def blocklist(self) -> dict[str, Any]:
        self.classifier()
        blocked = set(self.cfg.all_asns())
        v4, v6 = ranges.build(
            [p for asn, p in self._labelled if asn in blocked], self.cfg.block_cidrs, self.cfg.allow_cidrs
        )
        bl = Blocklist(
            v4, v6, self.cfg.agents(), self.cfg.all_asns(), time.strftime("%Y-%m-%d", time.gmtime(self._fetched_at))
        )
        return json.loads(render_json(bl, self.cfg))


def _excluded(cfg: Config, path: str) -> bool:
    path = path.split("?")[0]
    for p in cfg.exclude_paths:
        if p.startswith("*."):
            if path.endswith(p[1:]):
                return True
        elif p.endswith("*"):
            if path.startswith(p[:-1]):
                return True
        elif path == p:
            return True
    return False


# ---------------------------------------------------------------------------------------------------- OpenAPI
_PERIOD = [
    {
        "name": "since",
        "in": "query",
        "schema": {"type": "string", "format": "date"},
        "description": "First day to include (UTC).",
    },
    {
        "name": "until",
        "in": "query",
        "schema": {"type": "string", "format": "date"},
        "description": "Last day to include (UTC).",
    },
]


def openapi() -> dict[str, Any]:
    """The API described in OpenAPI 3.1. docs/openapi.json is this, written to a file."""

    def op(
        summary: str, params: list[dict[str, Any]] | None = None, public: bool = False, csv: bool = False
    ) -> dict[str, Any]:
        content: dict[str, Any] = {"application/json": {"schema": {"type": "object"}}}
        if csv:
            content["text/csv"] = {"schema": {"type": "string"}}
        responses: dict[str, Any] = {"200": {"description": "OK", "content": content}}
        if params:
            responses["400"] = {
                "description": "A parameter is not valid",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
        if not public:
            responses["401"] = {
                "description": "Missing or wrong token",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
            responses["503"] = {
                "description": "Logs or network ranges are not available",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            }
        out: dict[str, Any] = {"summary": summary, "responses": responses}
        if params:
            out["parameters"] = params
        if public:
            out["security"] = []
        return {"get": out}

    clicks = [
        *_PERIOD,
        {
            "name": "verdict",
            "in": "query",
            "schema": {"type": "string", "enum": list(VERDICTS), "default": "all"},
            "description": "Which clicks to return.",
        },
        {
            "name": "platform",
            "in": "query",
            "schema": {"type": "string"},
            "description": "Only this platform: google, microsoft...",
        },
        {
            "name": "limit",
            "in": "query",
            "schema": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 100},
            "description": "Clicks per page.",
        },
        {
            "name": "offset",
            "in": "query",
            "schema": {"type": "integer", "minimum": 0, "default": 0},
            "description": "Clicks to skip.",
        },
        {
            "name": "format",
            "in": "query",
            "schema": {"type": "string", "enum": ["json", "csv"], "default": "json"},
            "description": "csv returns every matching click, without paging.",
        },
    ]
    check = [
        {"name": "ip", "in": "query", "schema": {"type": "string"}, "description": "IPv4 or IPv6 address."},
        {"name": "user_agent", "in": "query", "schema": {"type": "string"}, "description": "User-Agent header."},
        {
            "name": "path",
            "in": "query",
            "schema": {"type": "string", "default": "/"},
            "description": "Requested path, to apply the excluded paths.",
        },
    ]
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "N-antibot API",
            "version": __version__,
            "description": "Read-only data about bots and paid ad clicks, computed from your own access logs.",
            "license": {"name": "MIT", "identifier": "MIT"},
        },
        "servers": [{"url": "http://127.0.0.1:8787"}],
        "security": [{"bearer": []}],
        "paths": {
            "/health": op("Is the service up? No token needed.", public=True),
            "/v1/summary": op("Requests, bots and ad clicks per platform.", _PERIOD),
            "/v1/bots": op(
                "Bot requests by network and robot, and the busiest visitors that are not blocked.", _PERIOD
            ),
            "/v1/ad-clicks": op("Paid ad clicks, one by one, with their verdict.", clicks, csv=True),
            "/v1/claims": op(
                "Where to dispute invalid clicks on each ad platform, and how many flagged clicks you have.", _PERIOD
            ),
            "/v1/check": op("Would this visitor be blocked?", check),
            "/v1/blocklist": op("The blocked ranges and robots in use."),
            "/v1/openapi.json": op("This document. No token needed.", public=True),
        },
        "components": {
            "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
            "schemas": {
                "Error": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {
                            "type": "object",
                            "required": ["code", "message"],
                            "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
                        }
                    },
                }
            },
        },
    }


# ---------------------------------------------------------------------------------------------------- HTTP
def make_handler(service: Service, token: str | None, cors_origin: str | None = None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"n-antibot/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # one quiet line per request, without the query string
            if os.environ.get("N_ANTIBOT_ACCESS_LOG"):
                print(
                    f"n-antibot api: {self.command} {urlsplit(self.path).path} -> {args[1] if len(args) > 1 else ''}",
                    flush=True,
                )

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization")
                self.send_header("Vary", "Origin")
            if status == 401:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, data: Any) -> None:
            self._send(status, (json.dumps(data, indent=2) + "\n").encode(), "application/json; charset=utf-8")

        def _error(self, status: int, code: str, message: str) -> None:
            self._json(status, {"error": {"code": code, "message": message}})

        def _authorized(self) -> bool:
            if token is None:
                return True
            given = self.headers.get("Authorization", "")
            return given.startswith("Bearer ") and hmac.compare_digest(given[7:].strip().encode(), token.encode())

        def do_OPTIONS(self) -> None:
            self._send(204, b"", "text/plain")

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            path = url.path.rstrip("/") or "/"
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if path == "/health":
                    return self._json(200, {"status": "ok", "version": __version__})
                if path == "/v1/openapi.json":
                    return self._json(200, openapi())
                if "token" in q or "access_token" in q:
                    raise ApiError(400, "token_in_url", "send the token in the Authorization header, never in the URL")
                if not self._authorized():
                    raise ApiError(401, "unauthorized", "send the header: Authorization: Bearer <token>")
                if path == "/v1/summary":
                    return self._json(200, service.summary(q))
                if path == "/v1/bots":
                    return self._json(200, service.bots(q))
                if path == "/v1/ad-clicks":
                    fmt = q.get("format", "json")
                    if fmt == "csv":
                        return self._send(200, service.ad_clicks_csv(q).encode(), "text/csv; charset=utf-8")
                    if fmt != "json":
                        raise ApiError(400, "invalid_parameter", "format must be json or csv")
                    return self._json(200, service.ad_clicks(q))
                if path == "/v1/claims":
                    return self._json(200, service.claims(q))
                if path == "/v1/check":
                    return self._json(200, service.check(q))
                if path == "/v1/blocklist":
                    return self._json(200, service.blocklist())
                raise ApiError(404, "not_found", f"no such endpoint: {path}. See /v1/openapi.json")
            except ApiError as e:
                self._error(e.status, e.code, e.message)
            except Exception as e:  # never leak a traceback to the client
                print(f"n-antibot api: error on {path}: {e!r}", flush=True)
                self._error(500, "internal_error", "unexpected error: see the service log")

        def _not_allowed(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD, OPTIONS")
            body = json.dumps(
                {"error": {"code": "method_not_allowed", "message": "this API is read-only: use GET"}}
            ).encode()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_PUT = do_PATCH = do_DELETE = _not_allowed

    return Handler


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def make_server(
    service: Service,
    host: str = "127.0.0.1",
    port: int = 8787,
    token: str | None = None,
    cors_origin: str | None = None,
) -> ThreadingHTTPServer:
    """Build the server (call .serve_forever()). Refuses to listen beyond loopback without a token."""
    if not is_loopback(host) and not token:
        raise ValueError(f"refusing to listen on {host} without a token: set N_ANTIBOT_TOKEN or --token-file")
    if token is not None and len(token) < 16:
        raise ValueError("the token must be at least 16 characters long")
    server = ThreadingHTTPServer((host, port), make_handler(service, token, cors_origin))
    server.daemon_threads = True
    return server


if __name__ == "__main__":  # python -m n_antibot.api > docs/openapi.json
    print(json.dumps(openapi(), indent=2))

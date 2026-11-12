# Data API

[← Documentation](README.md) · [🇪🇸 Español](../es/api.md) · [OpenAPI specification](../openapi.json)

> ✅ **Tested with the real server running:** permissions, filters, paging, CSV, errors, rotating logs and a failed
> range download. The example answers on this page are real output.

`n-antibot serve` starts a **read-only** API with the same data as `n-antibot report`: bots, ad clicks made by bots
and where to claim them. It answers in JSON (or CSV) so you can query it from your dashboard, a spreadsheet, a
script or an alert.

- [Starting it](#starting-it) · [Authentication](#authentication) · [Endpoints](#endpoints) · [Errors](#errors)
- [Examples](#examples) · [Keeping it running](#keeping-it-running) · [Security](#security) · [How it behaves](#how-it-behaves)

## Starting it

```bash
export N_ANTIBOT_TOKEN="$(openssl rand -hex 24)"
n-antibot serve -c n-antibot.toml '/var/log/nginx/access.log*'
# n-antibot: API on http://127.0.0.1:8787 (token required)
```

| Option | Default | Description |
|---|---|---|
| `LOG…` | (required) | Access logs. Wildcards are accepted **in quotes** (`'access.log*'`): they are resolved on every request, so rotated files are picked up by themselves. `.gz` too. |
| `-c CONFIG` | defaults | Your configuration: which networks and robots count as bots. |
| `--host` | `127.0.0.1` | Address to listen on. Outside `127.0.0.1` a token is mandatory. |
| `--port` | `8787` | Port. |
| `--token-file FILE` | | File holding the token. Alternative to the `N_ANTIBOT_TOKEN` variable. |
| `--cors-origin ORIGIN` | | Lets a web dashboard on that origin (`https://panel.example.com`) call the API from the browser. |
| `--refresh-hours H` | `24` | How often the network ranges are downloaded again. |

## Authentication

With a token, every request carries the `Authorization` header:

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" http://127.0.0.1:8787/v1/summary
```

| Rule | Detail |
|---|---|
| The token goes **only in the header** | If it arrives in the URL (`?token=`), the API answers `400 token_in_url`: URLs end up in logs and histories. |
| At least 16 characters | With a shorter one the service does not start. |
| No token, local only | Without a token the API only starts on `127.0.0.1`. On any other address it refuses to start. |
| Never without a token | `/health` and `/v1/openapi.json` are the only open endpoints. |

## Endpoints

| Endpoint | What it returns |
|---|---|
| [`GET /health`](#get-health) | Whether the service is up, and its version |
| [`GET /v1/summary`](#get-v1summary) | Summary: requests, bots and ad clicks per platform |
| [`GET /v1/bots`](#get-v1bots) | Bots by network and by robot, and the busiest visitors that are not blocked |
| [`GET /v1/ad-clicks`](#get-v1ad-clicks) | Ad clicks, one by one, with their verdict (JSON or CSV) |
| [`GET /v1/claims`](#get-v1claims) | Where to claim on each platform, what it asks for, and how many clicks you have within the deadline |
| [`GET /v1/check`](#get-v1check) | Would this IP or browser be blocked? |
| [`GET /v1/blocklist`](#get-v1blocklist) | The ranges and robots in use |
| `GET /v1/openapi.json` | This API described in OpenAPI 3.1 |

Common period parameters, on the endpoints that accept them:

| Parameter | Format | Description |
|---|---|---|
| `since` | `YYYY-MM-DD` | First day included (UTC). Without it, from the start of the logs. |
| `until` | `YYYY-MM-DD` | Last day included (UTC). Without it, to the end. |

### `GET /health`

No token. For your monitor.

```json
{ "status": "ok", "version": "0.5.0" }
```

### `GET /v1/summary`

Parameters: `since`, `until`.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "requests": 8,
  "ips": 5,
  "unreadable_lines": 1,
  "bots": {
    "requests": 5,
    "ips": 3,
    "cut_off": 4,
    "served": 1,
    "by": { "AS132203 (tencent-cloud)": 4, "python-requests": 1 }
  },
  "ad_clicks": {
    "google": { "network": 3, "agent": 1, "clean": 1, "total": 5 },
    "meta": { "network": 1, "total": 1 },
    "microsoft": { "no-resources": 1, "total": 1 }
  },
  "top_unblocked": [
    { "ip": "81.40.1.1", "requests": 2, "resources": 1, "user_agent": "Mozilla/5.0 (iPhone) Safari" }
  ]
}
```

| Field | Meaning |
|---|---|
| `period.from`, `period.to` | First and last request read (UTC). |
| `requests`, `ips` | Requests and distinct IP addresses. |
| `unreadable_lines` | Log lines that are not accesses. |
| `bots.requests`, `bots.ips` | Bot requests and how many IPs they came from. |
| `bots.cut_off` | Those that were cut off (status `0` in Caddy, `444` in nginx, `403` in Apache). |
| `bots.served` | Those that got an answer. If it is not `0`, the block is not installed or not up to date. |
| `bots.by` | Breakdown by network (with its ASN) and by robot. |
| `ad_clicks.<platform>` | Paid clicks: `total`, `network`, `agent` and `datacenter` (bots), `repeated` and `no-resources` (suspicious), `clean`. |
| `top_unblocked` | The busiest visitors that are not blocked, with how many resources (images, styles) they requested. |

### `GET /v1/bots`

Parameters: `since`, `until`. The bot part of the summary, without the ads.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "total_requests": 8,
  "requests": 5,
  "ips": 3,
  "cut_off": 4,
  "served": 1,
  "by": { "AS132203 (tencent-cloud)": 4, "python-requests": 1 },
  "top_unblocked": [ { "ip": "81.40.1.1", "requests": 2, "resources": 1, "user_agent": "Mozilla/5.0 (iPhone) Safari" } ]
}
```

`total_requests` is every request in the period; `requests` is the bot ones (`cut_off` + `served`).

### `GET /v1/ad-clicks`

| Parameter | Values | Default | Description |
|---|---|---|---|
| `since`, `until` | `YYYY-MM-DD` | | Period. |
| `verdict` | `bot`, `suspicious`, `clean`, `all` | `all` | Which clicks to return. |
| `platform` | `google`, `microsoft`, `meta`… | all | Only that platform. |
| `limit` | 1 to 1000 | `100` | Clicks per page. |
| `offset` | 0 or more | `0` | Clicks to skip. |
| `format` | `json`, `csv` | `json` | `csv` returns every matching click, without paging. |

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" "http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&limit=1"
```

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "total": 5,
  "limit": 1,
  "offset": 0,
  "clicks": [
    {
      "timestamp": "2026-11-12T09:00:01+00:00",
      "date_utc": "2026-11-12",
      "time_utc": "09:00:01",
      "platform": "google",
      "click_id": "AAA111",
      "ip": "43.173.132.9",
      "verdict": "bot",
      "reason": "from a blocked network",
      "detail": "AS132203 (tencent-cloud) 43.173.0.0/16",
      "cut_off": true,
      "status": 444,
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
      "campaign": null,
      "ad_group": null,
      "ad_id": null,
      "keyword": null,
      "url": "/product/a/?gclid=AAA111"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `total` | Clicks matching the filters (not only those on this page). |
| `click_id` | The click's `gclid`, `msclkid`… If the paid visit carries no identifier, `(no id) IP path`. |
| `verdict` | `bot`, `suspicious` or `clean`. |
| `reason`, `detail` | Why: the network with its ASN and range, the robot, or the hint. `null` for clean clicks. |
| `cut_off` | `true` if the visit was cut off. The click is charged anyway: it happens at the platform before reaching your site. |
| `status` | The code your server answered with. |
| `campaign`, `ad_group`, `ad_id`, `keyword` | Whatever the URL carries (`utm_campaign`, `gad_campaignid`, `adgroupid`, `utm_term`…). `null` if it carries none. |

To download the CSV ready to attach:

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" \
  "http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&platform=google&since=2026-10-01&format=csv" -o google-bots.csv
```

### `GET /v1/claims`

Parameters: `since`, `until`. One entry per platform, with what its official documentation says (read on the day in
`checked`) and your clicks in the period.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "platforms": [
    {
      "platform": "google",
      "name": "Google Ads",
      "has_process": true,
      "where": "Click Quality Form",
      "url": "https://support.google.com/google-ads/contact/click_quality",
      "deadline_days": 60,
      "asks": [
        "Date range of the suspicious activity (within the past 60 days)",
        "Campaign and ad group names",
        "Suspicious keywords",
        "Web server logs: IP addresses with repetitive clicks or clicks without conversions",
        "Web server logs: browser or device information",
        "Web server logs: GCLIDs of the suspicious clicks",
        "A brief explanation of why the traffic is suspicious"
      ],
      "outcome": "Specialists review the last 60 days and email the findings; if more invalid traffic is found, Google notifies you of the credit. It does not confirm click by click.",
      "source": "https://support.google.com/google-ads/answer/11182074",
      "checked": "2026-11-12",
      "clicks": 5,
      "bot_clicks": 4,
      "suspicious_clicks": 0,
      "flagged_within_deadline": 4
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `has_process` | `true` if the platform documents a way to dispute invalid clicks. |
| `where`, `url` | Where to claim. |
| `deadline_days` | Deadline in days from the activity. `null` if it states none. |
| `asks` | What the platform says it needs. Empty if it does not say. |
| `outcome` | What you can expect. |
| `source`, `checked` | The official page it comes from and the day it was read. |
| `clicks`, `bot_clicks`, `suspicious_clicks` | Your clicks from that platform in the period. |
| `flagged_within_deadline` | Bot and suspicious clicks that are still within the deadline. |

### `GET /v1/check`

| Parameter | Description |
|---|---|
| `ip` | IPv4 or IPv6 address. |
| `user_agent` | `User-Agent` header. |
| `path` | Requested path, to apply the excluded paths. Default `/`. |

`ip`, `user_agent` or both are required.

```json
{
  "ip": "43.173.132.9",
  "user_agent": "Mozilla/5.0",
  "path": "/",
  "is_bot": true,
  "reason": "network",
  "match": "AS132203 (tencent-cloud) 43.173.0.0/16",
  "path_excluded": false,
  "would_block": true
}
```

| Field | Meaning |
|---|---|
| `is_bot` | It is in a blocked network or is a blocked robot. |
| `reason` | `network` or `agent`; `null` if it is not a bot. |
| `match` | The range with its ASN, or the robot's name. |
| `path_excluded` | The path is in `[paths] exclude`. |
| `would_block` | `is_bot` and the path is not excluded: what your server would do. |

### `GET /v1/blocklist`

The same as `n-antibot generate -f json`: `asns`, `ipv4`, `ipv6`, `user_agents`, `user_agent_regex` and
`exclude_paths`. Useful to feed another system (a firewall, a dashboard) from one place.

## Errors

Always in the same shape:

```json
{ "error": { "code": "invalid_parameter", "message": "since must be a date like 2026-11-12" } }
```

| Status | `code` | When |
|:---:|---|---|
| 400 | `invalid_parameter` | A date, number or value that is not valid. The message says which. |
| 400 | `token_in_url` | The token arrived in the URL instead of the header. |
| 401 | `unauthorized` | The token is missing or wrong. |
| 404 | `not_found` | That endpoint does not exist. |
| 405 | `method_not_allowed` | The API is read-only: `GET` only. |
| 500 | `internal_error` | Unexpected error. The detail goes to the service log, not to the answer. |
| 503 | `no_logs` | It cannot find or read the access logs. |
| 503 | `ranges_unavailable` | It could not download the network ranges and has no earlier copy. |

## Examples

**Python** (standard library only):

```python
import json, os, urllib.request

def n_antibot(path):
    req = urllib.request.Request(
        "http://127.0.0.1:8787" + path,
        headers={"Authorization": "Bearer " + os.environ["N_ANTIBOT_TOKEN"]},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

summary = n_antibot("/v1/summary?since=2026-11-01")
google = summary["ad_clicks"].get("google", {})
bots = google.get("network", 0) + google.get("agent", 0)
print(f"Google Ads: {bots} of {google.get('total', 0)} clicks were made by a bot")
```

**JavaScript** (Node 18 or a web dashboard with `--cors-origin`):

```js
const res = await fetch('http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&limit=1000', {
  headers: { Authorization: `Bearer ${process.env.N_ANTIBOT_TOKEN}` },
});
if (!res.ok) throw new Error((await res.json()).error.message);
const { total, clicks } = await res.json();
console.log(total, clicks.map((c) => c.click_id));
```

**Daily alert** (warns if bots are still getting answers):

```bash
served=$(curl -s -H "Authorization: Bearer $N_ANTIBOT_TOKEN" \
  "http://127.0.0.1:8787/v1/bots?since=$(date -u +%F)" | python3 -c 'import json,sys; print(json.load(sys.stdin)["served"])')
[ "$served" -gt 0 ] && echo "N-antibot: $served bot requests got an answer today"
```

## Keeping it running

With systemd:

```ini
# /etc/systemd/system/n-antibot-api.service
[Unit]
Description=N-antibot API
After=network-online.target

[Service]
ExecStart=/usr/local/bin/n-antibot serve -c /etc/n-antibot.toml --token-file /etc/n-antibot.token '/var/log/nginx/access.log*'
User=n-antibot
Group=adm
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --no-create-home n-antibot
openssl rand -hex 24 | sudo tee /etc/n-antibot.token >/dev/null
sudo chown n-antibot /etc/n-antibot.token && sudo chmod 600 /etc/n-antibot.token
sudo systemctl enable --now n-antibot-api
```

This systemd unit is an example: it is not covered by the tests. The service user must be able to **read** the logs (on Debian and Ubuntu, the `adm` group).

To query it from outside, put it behind your web server with HTTPS instead of opening it directly:

```caddyfile
panel.example.com {
	handle_path /n-antibot/* {
		reverse_proxy 127.0.0.1:8787
	}
}
```

## Security

| Measure | Detail |
|---|---|
| Read-only | It only answers `GET`. No endpoint changes anything. |
| Local by default | It listens on `127.0.0.1`. Beyond that, a token is mandatory. |
| Token in the header | Compared in constant time; never in the URL. |
| No extra data in errors | An internal failure answers a generic `500`; the detail goes to the service log. |
| Uncached answers | `Cache-Control: no-store`: proxies do not keep visitors' IPs. |
| Personal data | The API returns IP addresses. Protect it with a token and HTTPS, and give access only to those who need it. |

## How it behaves

| Topic | Behaviour |
|---|---|
| Fresh data | Every request checks whether the logs changed (date and size). If not, it answers from memory. |
| Rotating logs | Wildcards are resolved on every request: `access.log.1`, `access.log.2.gz`… are picked up by themselves. |
| Network ranges | Downloaded at start and every `--refresh-hours`. If a download fails, it keeps the previous ones and retries in ten minutes. |
| Times | All in UTC, in ISO 8601. |
| Large logs | The first computation reads every file; it takes time in proportion to their size. Use `since` and rotated logs to narrow it. |
| Versions | Endpoints carry `/v1/`. An incompatible change would go under `/v2/`. |

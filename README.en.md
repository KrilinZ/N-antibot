<div align="center">

<img src="assets/logo.png" alt="N-antibot: Secure your digital ecosystem" width="300">

# N-antibot

### Cut bots off at your server, count the ad clicks they made and prepare the claim.

No accounts · no keys · no JavaScript on your site · open source (MIT)

[![Version](https://img.shields.io/github/v/tag/KrilinZ/N-antibot?label=version&color=7c3aed&sort=semver)](https://github.com/KrilinZ/N-antibot/releases)
[![CI](https://github.com/KrilinZ/N-antibot/actions/workflows/ci.yml/badge.svg)](https://github.com/KrilinZ/N-antibot/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-against%20real%20servers-22c55e)](#-tests)
[![License MIT](https://img.shields.io/github/license/KrilinZ/N-antibot?label=license&color=2563eb)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/KrilinZ/N-antibot?label=last%20commit&color=2563eb)](https://github.com/KrilinZ/N-antibot/commits/main)
[![Stars](https://img.shields.io/github/stars/KrilinZ/N-antibot?style=flat&label=stars&color=f59e0b)](https://github.com/KrilinZ/N-antibot/stargazers)

[![Python 3.9 – 3.14](https://img.shields.io/badge/python-3.9%20%E2%80%93%203.14-3776ab?logo=python&logoColor=white)](#-compatibility)
[![Linux · macOS · Windows](https://img.shields.io/badge/Linux%20%C2%B7%20macOS%20%C2%B7%20Windows-tested-0ea5e9)](#-compatibility)
[![Dependencies: 0](https://img.shields.io/badge/dependencies-0%20on%20Python%203.11%2B-22c55e)](pyproject.toml)
[![Docs](https://img.shields.io/badge/docs-ES%20%C2%B7%20EN-8b5cf6)](docs/en/README.md)
[![OpenAPI 3.1](https://img.shields.io/badge/OpenAPI-3.1-6ba539?logo=openapiinitiative&logoColor=white)](docs/openapi.json)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-ec4899)](CONTRIBUTING.md)

[![Caddy](https://img.shields.io/badge/Caddy-2.x-1f88c0?logo=caddy&logoColor=white)](docs/en/caddy.md)
[![nginx](https://img.shields.io/badge/nginx-1.x-009639?logo=nginx&logoColor=white)](docs/en/nginx.md)
[![Apache](https://img.shields.io/badge/Apache-2.4-d22128?logo=apache&logoColor=white)](docs/en/apache.md)
[![nftables](https://img.shields.io/badge/Linux-nftables-f59e0b?logo=linux&logoColor=white)](docs/en/nftables.md)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-WAF-f38020?logo=cloudflare&logoColor=white)](docs/en/cloudflare.md)
[![Node.js](https://img.shields.io/badge/Node.js-18%20%E2%80%93%2024-339933?logo=nodedotjs&logoColor=white)](docs/en/node-express.md)
[![Next.js](https://img.shields.io/badge/Next.js-middleware-000000?logo=nextdotjs&logoColor=white)](docs/en/vercel-nextjs.md)
[![Google Ads](https://img.shields.io/badge/Google%20Ads-claim%20file-4285f4?logo=googleads&logoColor=white)](#-where-to-claim-fraudulent-clicks)

[**Install**](#-install-in-2-steps) · [What it does](#-what-it-does) · [Guides](docs/en/README.md) · [Ad report](#-report-bots-and-ad-clicks) · [Where to claim](#-where-to-claim-fraudulent-clicks) · [API](#-data-api) · [Changelog](CHANGELOG.md)

[🇪🇸 Español](README.md) · 🇬🇧 English

<br>

<img src="assets/demo.svg" alt="N-antibot installed in two commands, then a report of ad clicks made by bots" width="860">

</div>

---

## ⚡ Install in 2 steps

On your web server (Caddy, nginx or Apache):

```bash
curl -fsSL https://raw.githubusercontent.com/KrilinZ/N-antibot/main/install.sh | sudo sh
```

```bash
sudo n-antibot install --site example.com --check-url https://example.com
```

```console
n-antibot: found example.com in /etc/caddy/Caddyfile (caddy)
n-antibot: server: caddy, configuration: /etc/caddy/Caddyfile, file: /etc/caddy/n-antibot.caddy
n-antibot: add 1 line: import /etc/caddy/n-antibot.caddy
n-antibot: backup in /var/backups/n-antibot/20261112-233030
n-antibot: caddy reloaded
n-antibot: ok   browser    -> 200
n-antibot: ok   Googlebot  -> 200
n-antibot: ok   curl       -> 200
n-antibot: ok   Bytespider -> closed (expected closed)
n-antibot: installed: example.com is protected
```

| Step | What it does | If something fails |
|---|---|---|
| 1. The script | Installs the `n-antibot` command in its own environment (`/opt/n-antibot`), without touching the system Python. It only needs Python 3.9 or later. | Nothing else is changed |
| 2. `n-antibot install` | Finds your site in the server configuration, backs it up, adds **one line**, validates with the server itself, reloads and checks live that a browser and Google get in and a robot does not. | Everything is put back as it was |

| Do you want to…? | Command |
|---|---|
| See what it would do, changing nothing | `sudo n-antibot install --site example.com --dry-run` |
| Remove it | `sudo n-antibot install --site example.com --uninstall` |
| Name the server and file yourself | `sudo n-antibot install nginx --site example.com --config-file /etc/nginx/sites-enabled/example` |
| Use your own configuration | `sudo n-antibot install -c n-antibot.toml --site example.com` |
| Cut at the Linux firewall | `sudo n-antibot install nftables` |
| Read the script before running it | [install.sh](install.sh) (60 lines) |

No administrator access, or your site goes through Cloudflare, Vercel or Node? See the
[guides by technology](#-guides-by-technology-and-by-use-case).

## ✨ What it does

<table>
<tr>
<td width="33%" valign="top">

### 🛡️ Cuts bots off

Data-center networks and scrapers get no answer. Google, Bing, AI crawlers and your customers get in as usual.

</td>
<td width="33%" valign="top">

### 💶 Counts fake clicks

Reads your server logs and tells you how many paid ad clicks were made by a bot.

</td>
<td width="33%" valign="top">

### 📁 Prepares the claim

One file set per platform with what each one asks for: GCLID, IP, browser, campaign, deadline and the text to paste.

</td>
</tr>
<tr>
<td width="33%" valign="top">

### ⚡ Installs itself

Two commands. It backs up, validates, reloads, checks live and, if anything fails, puts everything back.

</td>
<td width="33%" valign="top">

### 🔌 Data API

`n-antibot serve`: the same data as JSON for your dashboard or alerts. Read-only, with a token and OpenAPI.

</td>
<td width="33%" valign="top">

### 🌍 Wherever your site runs

Caddy, nginx, Apache and `.htaccess`, the Linux firewall, Cloudflare, Node.js and Next.js.

</td>
</tr>
</table>

<table align="center">
<tr><td align="center"><b>7</b><br><sub>technologies</sub></td><td align="center"><b>6</b><br><sub>ad platforms documented</sub></td><td align="center"><b>90+</b><br><sub>tests, against real servers</sub></td><td align="center"><b>14</b><br><sub>combinations tested on every change</sub></td><td align="center"><b>0</b><br><sub>dependencies (Python 3.11+)</sub></td><td align="center"><b>2</b><br><sub>languages</sub></td></tr>
</table>

## 📚 Contents

<table>
<tr>
<td valign="top">

**Start**

- [Install in 2 steps](#-install-in-2-steps)
- [What it does](#-what-it-does)
- [Why it exists](#-why-it-exists)
- [What it blocks and what it does not](#️-what-it-blocks-and-what-it-does-not)
- [How it works](#️-how-it-works)
- [Guides by technology and by use case](#-guides-by-technology-and-by-use-case)

</td>
<td valign="top">

**Use**

- [Report: bots and ad clicks](#-report-bots-and-ad-clicks)
- [Where to claim fraudulent clicks](#-where-to-claim-fraudulent-clicks)
- [Data API](#-data-api)
- [Manual installation](#-installation)
- [Keeping the lists fresh](#-keeping-the-lists-fresh)
- [Checking that it works](#-checking-that-it-works)
- [Removing it](#-removing-it)

</td>
<td valign="top">

**Reference**

- [Configuration](#-configuration)
- [Built-in lists](#-built-in-lists)
- [Commands](#️-commands)
- [Python API](#-python-api)
- [Requirements](#-requirements)
- [Compatibility](#-compatibility)
- [Tests](#-tests)
- [Limits](#-limits-what-n-antibot-does-not-do)
- [FAQ](#-faq)
- [Roadmap](#️-roadmap)
- [Project layout](#️-project-layout)
- [Contributing](#-contributing)

</td>
</tr>
</table>

## 💡 Why it exists

Commercial anti-bot services work well, but many require a contract, are billed per request and cannot always be
placed in front of any server. For a shop or a small
site, what hurts most is often much simpler: **data-center traffic that will never buy anything** and **scrapers
that do not even hide their name**.

N-antibot was born on a real online shop to cut exactly that, with three principles:

| Principle | What it means |
|---|---|
| **Nothing to sign up for** | No accounts, no API keys, no JavaScript on your site and no Python dependencies (on 3.9 and 3.10, `tomli` is installed automatically to read the configuration). |
| **Do not break the site** | Search engines, AI crawlers, real browsers, `curl` and your webhooks are never touched. A configuration is rejected if one of your rules could cut off a browser or Google. |
| **All or nothing** | If downloading the ranges fails, no file is written. The installer backs up, validates, reloads, checks the live site and rolls back by itself if anything is off. |

## 🛡️ What it blocks and what it does not

| Visit | Default | How to change it |
|---|:---:|---|
| Tencent Cloud (AS132203, AS45090) | ⛔ cut off | `[networks] presets` |
| Alibaba Cloud, Huawei Cloud | ✅ allowed | add `alibaba-cloud`, `huawei-cloud` |
| Any other network (by ASN or by range) | ✅ allowed | `[networks] asns` and `block` |
| Bytespider, MJ12bot, DotBot, BLEXBot, PetalBot, MegaIndex, SeekportBot | ⛔ cut off | `[robots] presets` / `allow` |
| python-requests, python-urllib, Go-http-client, Scrapy, aiohttp, libwww-perl | ⛔ cut off | `[robots] allow` |
| zgrab, masscan, Nuclei, sqlmap, Nikto | ⛔ cut off | `[robots] allow` |
| AhrefsBot, SemrushBot and other SEO tools | ✅ allowed | add the `seo-tools` preset |
| GPTBot, ClaudeBot, CCBot and other AI crawlers | ✅ allowed | add the `ai-training` preset |
| Googlebot, Bingbot, DuckDuckBot, Yandex, Applebot | ✅ always allowed | cannot be blocked by mistake |
| Chrome, Safari, Firefox, mobile browsers | ✅ always allowed | cannot be blocked by mistake |
| `curl`, `wget` | ✅ always allowed | they are your own testing tools |
| Excluded paths (`/.well-known/*` and the ones you add) | ✅ always allowed | `[paths] exclude` |

> [!IMPORTANT]
> AI crawlers are allowed by default on purpose: if you want your site to show up in ChatGPT, Claude or Perplexity
> answers (GEO), do not block them.

## ⚙️ How it works

```mermaid
flowchart LR
    A[n-antibot.toml<br/>your configuration] --> B[n-antibot generate]
    R[(RIPEstat<br/>public BGP data)] -->|ranges per ASN| B
    P[Built-in lists<br/>networks and robots] --> B
    B -->|merge, dedupe,<br/>subtract allowed| C{Format}
    C --> D[n-antibot.caddy]
    C --> E[n-antibot.conf · nginx]
    C --> F[Apache · nftables ·<br/>Cloudflare · JSON]
    D --> G[install/caddy.sh<br/>backup · validate · reload ·<br/>live check · rollback]
```

1. **It downloads the ranges** announced by each autonomous system (ASN) from [RIPEstat](https://stat.ripe.net/),
   which publishes BGP data without an account. There is a timeout, retries with growing waits and validation of
   the answer.
2. **It merges** the ranges (joins adjacent ones, drops nested ones) and **subtracts** the ones you mark as allowed.
3. **It generates** the file for your server. On every request the server looks at the IP and the `User-Agent`; if
   one matches and the path is not excluded, it **closes the connection without answering**. The bot does not even
   get an error: it uses none of your bandwidth and never reaches your application.

<details>
<summary><b>The Caddy detail that is hardest to find out</b></summary>

In Caddy, a `handle @matcher` with a named matcher is sorted **after** every `handle /path/*`. If your site has
`handle /product/*` or `handle /api/*`, a block written as `handle @bots { abort }` would never reach those routes.

N-antibot solves it in two steps: a `rewrite` (which Caddy runs before any `handle`) sends the request to a private
path, and an **exact-path** `handle` (which wins over prefix ones) aborts it:

```caddyfile
rewrite @nAntibotNet /__n_antibot_blocked
rewrite @nAntibotAgent /__n_antibot_blocked
handle /__n_antibot_blocked {
	abort
}
```

The tests start a real Caddy with `handle /product/*` and check that the cut reaches it too.
</details>

## 📊 Report: bots and ad clicks

`n-antibot report` reads your server's access logs (Caddy, nginx or Apache) and tells you how many visits are bots
and **how many paid ad clicks were made by a bot**, with a CSV (date, IP, browser and `gclid`) that is exactly what
Google asks for to investigate invalid clicks and credit them.

```console
$ n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --csv bot-clicks.csv
Bots
  Requests from bots: 3 (50.0%) from 2 IPs
    cut off:  2
    served:   1   <- N-antibot is not stopping these yet
Paid ad clicks
  google: 4 clicks
    bots:        3 (75.0%)  [network 2, robot 1]
    suspicious:  0 (0.0%)  [repeated IP 0, no resources 0]
    clean:       1
  ...
n-antibot: 4 ad clicks written to bot-clicks.csv
```

> [!WARNING]
> Cutting the bot off does not avoid the charge: the click happens at Google before reaching your site. The money
> is recovered by claiming, and that is what the CSV is for.

Full guide: [docs/en/ads-report.md](docs/en/ads-report.md).

## 💶 Where to claim fraudulent clicks

What each platform's official documentation says, read on 12 November 2026. Platforms change their rules: open the
source before you claim.

| Platform | Where to claim | Deadline | What it asks for | What you can expect |
|---|---|---|---|---|
| **Google Ads** | [Click Quality Form](https://support.google.com/google-ads/contact/click_quality) | Last 60 days | Dates; campaigns and ad groups; keywords; web server logs with IP, browser and GCLID; why it is suspicious | Specialists review it and email the findings. If they find more invalid traffic, they notify you of the credit. No click-by-click confirmation. [Source](https://support.google.com/google-ads/answer/11182074) |
| **Microsoft Advertising** (Bing) | [Support](https://go.microsoft.com/fwlink?LinkId=398371), saying it is an "invalid clicks" issue | Best within 30 days; no investigation after 60 | Ad group and its number; ad ID and keywords; dates; what you see in your reports or logs; a log sample if asked | They try to finish within 9 days and recommend reimbursement if the traffic is invalid. [Source](https://help.ads.microsoft.com/#apex/ads/en/60220/0) |
| **LinkedIn Ads** | [Marketing Solutions support](https://www.linkedin.com/help/lms/ask), in writing | 90 days | The fees you dispute and why | Ad credit only, at LinkedIn's discretion; no cash refund. [Source](https://www.linkedin.com/legal/sas-terms) |
| **X Ads** | [Support ticket](https://ads.x.com/en/help), in writing | 60 days from the charge (US agreement) | The charges you dispute | A refund only if they find a billing or technical error. [Source](https://help.x.com/en/business-and-advertising/billing-basics) |
| **Meta Ads** (Facebook, Instagram) | [Ads payment support form](https://www.facebook.com/help/contact/649167531904667). **No documented process for invalid clicks** | None stated | It does not say | Decided case by case, at Meta's discretion, and final. At least one month. No refunds for poor performance. [Source](https://www.facebook.com/business/help/211313200321572) |
| **Pinterest Ads** | Support. **No documented process for invalid clicks** | None stated | It does not say | It says standard charges are usually not eligible for a refund. [Source](https://help.pinterest.com/en/business/article/refunds-and-chargebacks) |
| **TikTok Ads, Amazon Ads** | No process found in their help (searched only; their pages were not opened one by one) | | | |

`n-antibot report --claim-dir claim/` prepares **one file set per platform** with what each one asks for:

```console
$ n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --claim-dir claim/
n-antibot: Google Ads: 4 clicks (4 within the deadline) -> claim/google-claim.txt
n-antibot: Meta Ads (Facebook, Instagram): 1 clicks (1 within the deadline) -> claim/meta-claim.txt (the platform documents no process for invalid clicks)
```

| File | Content |
|---|---|
| `google-claim.txt` | Where to claim, the deadline, what the platform asks for, how many clicks are still within the deadline, the IPs with the reason, and **a text ready to paste** explaining why they are suspicious |
| `google-clicks.csv` | One click per row: date and time (UTC), `click_id` (GCLID), IP, browser, verdict, reason, network and ASN, campaign, ad group, ad and keyword (when the URL carries them) and whether it is within the deadline |
| `google-log-sample.log` | The exact web server log lines of those clicks |

What the log cannot know and you must add: your account ID and the campaign, ad group and keyword names of the
clicks whose URL does not carry them. If you add those to your tracking template (`utm_campaign`, `utm_term`…), the
next report already has them.

> [!WARNING]
> **Cutting the bot off does not avoid the charge:** the click happens at the platform before the visit reaches
> your site. And no platform guarantees a refund: they all decide themselves, and several only give ad credit.

## 🔌 Data API

`n-antibot serve` starts a read-only JSON API with the same data: for your dashboard, a spreadsheet or an alert.

```console
$ export N_ANTIBOT_TOKEN="$(openssl rand -hex 24)"
$ n-antibot serve '/var/log/nginx/access.log*'
n-antibot: API on http://127.0.0.1:8787 (token required)
$ curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" "http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&platform=google"
```

| Endpoint | What it returns |
|---|---|
| `GET /v1/summary` | Requests, bots and ad clicks per platform |
| `GET /v1/bots` | Bots by network and by robot, and the busiest unblocked visitors |
| `GET /v1/ad-clicks` | Ad clicks one by one, with filters, paging and CSV |
| `GET /v1/claims` | Where to claim on each platform, what it asks for and how many clicks you have within the deadline |
| `GET /v1/check` | Whether an IP or a browser would be blocked |
| `GET /v1/blocklist` | The ranges and robots in use |
| `GET /health`, `GET /v1/openapi.json` | Service status and OpenAPI 3.1 specification (no token) |

It only listens on `127.0.0.1` unless you give it a token; the token goes in the header, never in the URL.

Full guide, with every parameter, every field, errors, examples and deployment:
[docs/en/api.md](docs/en/api.md) · [openapi.json](docs/openapi.json).

## 📖 Guides by technology and by use case

The full documentation lives in [`docs/en/`](docs/en/README.md). Every guide says what has been tested and what
has not.

| Technology | Guide | What it cuts | Tested |
|---|---|---|:---:|
| Caddy | [docs/en/caddy.md](docs/en/caddy.md) | networks and robots | ✅ |
| nginx | [docs/en/nginx.md](docs/en/nginx.md) | networks and robots | ✅ |
| Apache and `.htaccess` | [docs/en/apache.md](docs/en/apache.md) | networks and robots | ✅ |
| Linux firewall (nftables) | [docs/en/nftables.md](docs/en/nftables.md) | networks only | ✅ |
| Node.js and Express | [docs/en/node-express.md](docs/en/node-express.md) | networks and robots | ✅ |
| Next.js and Vercel | [docs/en/vercel-nextjs.md](docs/en/vercel-nextjs.md) | networks and robots | ⚠️ logic only |
| Cloudflare | [docs/en/cloudflare.md](docs/en/cloudflare.md) | networks and robots | ⚠️ no real account |

| Use case | Ready configuration |
|---|---|
| [Online shop](docs/en/cases.md#-online-shop) | [`shop.toml`](examples/cases/shop.toml) |
| [Blog, magazine or corporate site](docs/en/cases.md#-blog-magazine-or-corporate-site) | [`blog.toml`](examples/cases/blog.toml) |
| [Site with a public API](docs/en/cases.md#-site-with-a-public-api) | [`public-api.toml`](examples/cases/public-api.toml) |
| [WordPress](docs/en/cases.md#-wordpress) | [`wordpress.toml`](examples/cases/wordpress.toml) |
| [Behind a CDN or load balancer](docs/en/cases.md#-behind-a-cdn-or-load-balancer) | [`behind-cdn.toml`](examples/cases/behind-cdn.toml) |
| [Maximum protection](docs/en/cases.md#-maximum-protection) | [`strict.toml`](examples/cases/strict.toml) |
| [No AI crawlers](docs/en/cases.md#-no-ai-crawlers) | [`no-ai.toml`](examples/cases/no-ai.toml) |
| [Cutting before the web server](docs/en/cases.md#-cutting-before-the-web-server) | [`firewall.toml`](examples/cases/firewall.toml) |
| [Several sites on one server](docs/en/cases.md#-several-sites-on-one-server) · [I am being hit from another network](docs/en/cases.md#-i-am-being-hit-from-another-network) · [I blocked someone I should not have](docs/en/cases.md#-i-blocked-someone-i-should-not-have) | |

## 🚀 Installation

The shortest way is the [two-step script](#-install-in-2-steps). If you would rather install it yourself with `pip`:

```bash
pip install git+https://github.com/KrilinZ/N-antibot.git
```

Or isolated, with [pipx](https://pipx.pypa.io/):

```bash
pipx install git+https://github.com/KrilinZ/N-antibot.git
```

To pin a version, append the tag: `...N-antibot.git@v0.6.0`.

### 🟦 Caddy setup

**1. Create your configuration** (optional: defaults are used without it).

```bash
n-antibot init -o n-antibot.toml
```

**2. Generate the file.**

```bash
n-antibot generate -c n-antibot.toml -o n-antibot.caddy
```

**3. Install it** (on the server, as root). Steps 2 and 3 are done in one go with:

```bash
sudo n-antibot install caddy -c n-antibot.toml --site example.com --check-url https://example.com
```

If there is no Python on the server, generate the file on another machine and use the bash installer:

```bash
sudo ./install/caddy.sh --site example.com --snippet n-antibot.caddy --check-url https://example.com
```

The installer does this, in order, and **rolls back by itself** if anything fails:

| Step | What it does |
|:---:|---|
| 1 | Backs up the `Caddyfile` and the previous file to `/var/backups/n-antibot/<date>/` |
| 2 | Copies the new file to `/etc/caddy/n-antibot.caddy` |
| 3 | Adds `import /etc/caddy/n-antibot.caddy` as the first line of your site block (only once) |
| 4 | `caddy validate` and, if it passes, `caddy reload` |
| 5 | With `--check-url`: Chrome, Googlebot and curl must get an answer, and Bytespider must be cut off |

<details>
<summary><b>Installer options</b></summary>

| Option | Default | Description |
|---|---|---|
| `--site ADDRESS` | (required) | The block to protect, exactly as its line starts in the Caddyfile (`example.com {`) |
| `--snippet FILE` | (required) | The file made by `n-antibot generate` |
| `--caddyfile FILE` | `/etc/caddy/Caddyfile` | Your Caddyfile |
| `--dest FILE` | `/etc/caddy/n-antibot.caddy` | Where it is installed |
| `--backup-dir DIR` | `/var/backups/n-antibot` | Where backups are kept |
| `--address HOST:PORT` | Caddy's own | Caddy admin endpoint used for the reload |
| `--check-url URL` | (none) | Live check after the reload |
| `--uninstall` | | Removes the `import` line and reloads |

</details>

<details>
<summary><b>Manual setup</b></summary>

```caddyfile
example.com {
	# Must be the FIRST line of the block.
	import /etc/caddy/n-antibot.caddy

	handle /api/* {
		reverse_proxy 127.0.0.1:3000
	}
	handle {
		root * /var/www/example
		file_server
	}
}
```

```bash
sudo cp n-antibot.caddy /etc/caddy/n-antibot.caddy
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

</details>

> [!NOTE]
> Is your Caddy behind Cloudflare or a load balancer? Set `ip_matcher = "client_ip"` under `[caddy]` and configure
> `trusted_proxies` in Caddy. Otherwise Caddy would see the proxy's IP instead of the visitor's.

### 🟩 nginx setup

**1. Generate the file.**

```bash
n-antibot generate -c n-antibot.toml -f nginx -o n-antibot.conf
sudo cp n-antibot.conf /etc/nginx/n-antibot.conf
```

**2. Include it once inside `http { }`** and add one line to every `server` you want to protect.

```nginx
http {
	include /etc/nginx/n-antibot.conf;

	server {
		server_name example.com;

		if ($n_antibot_block) { return 444; }

		# ... the rest of your configuration
	}
}
```

**3. Validate and reload.**

```bash
sudo nginx -t && sudo nginx -s reload
```

All three steps, with backup and rollback, are done by `sudo n-antibot install nginx --site example.com`.

`444` is nginx's special code for **closing the connection without answering**, the same as `abort` in Caddy.

The file defines four variables:

| Variable | Is `1` when… |
|---|---|
| `$n_antibot_net` | the IP is in a blocked network (`geo`) |
| `$n_antibot_agent` | the `User-Agent` matches a blocked robot (`map`) |
| `$n_antibot_excluded` | the path is in `[paths] exclude` |
| `$n_antibot_block` | the request must be cut: network or robot, and the path is not excluded |

> [!NOTE]
> Behind a proxy or CDN, configure nginx's `realip` module (`set_real_ip_from`, `real_ip_header`) so that `geo`
> sees the visitor's real IP.

### 🟨 More technologies

| Your site goes through… | Command | Guide |
|---|---|---|
| Apache or an `.htaccess` | `n-antibot generate -f apache -o n-antibot.conf` | [Apache](docs/en/apache.md) |
| The Linux firewall | `n-antibot generate -f nftables -o n-antibot.nft` | [nftables](docs/en/nftables.md) |
| Cloudflare | `n-antibot generate -f cloudflare \| tail -1` | [Cloudflare](docs/en/cloudflare.md) |
| Node.js or Express | `n-antibot generate -f json -o n-antibot.json` | [Node.js and Express](docs/en/node-express.md) |
| Next.js or Vercel | `n-antibot generate -f json -o n-antibot.json` | [Next.js and Vercel](docs/en/vercel-nextjs.md) |

For anything else (another CDN, fail2ban, your own code), the JSON output carries the plain lists:

```bash
n-antibot generate -f json -o n-antibot.json
```

```json
{
  "generator": "n-antibot 0.6.0",
  "generated_on": "2026-11-12",
  "asns": ["AS132203", "AS45090"],
  "ipv4": ["1.12.0.0/14", "1.116.0.0/15", "…"],
  "ipv6": ["2402:4e00::/32", "…"],
  "user_agents": ["Bytespider", "MJ12bot", "…"],
  "user_agent_regex": "(?i)(Bytespider|MJ12bot|…)",
  "exclude_paths": ["/.well-known/*"]
}
```

## 🧩 Configuration

A single TOML file. **Every key is optional.** Create it with `n-antibot init -o n-antibot.toml`.

```toml
[networks]
presets = ["tencent-cloud"]        # cloud networks to block
asns    = ["AS45102"]              # extra autonomous systems
block   = ["203.0.113.0/24"]       # single ranges you want cut off
allow   = ["43.153.10.20/32"]      # ranges that are NEVER cut (your server, your monitor)

[robots]
presets = ["aggressive-crawlers", "scraping-libraries", "vulnerability-scanners"]
block   = ["BadBot"]               # extra User-Agent fragments
allow   = ["aiohttp"]              # take them out of the built-in lists

[paths]
exclude = ["/.well-known/*", "/api/*", "/webhooks/*", "/health"]

[output]
format = "caddy"                   # caddy | nginx | apache | nftables | cloudflare | json

[caddy]
prefix     = "nAntibot"
block_path = "/__n_antibot_blocked"
ip_matcher = "remote_ip"           # or "client_ip" behind a proxy

[nginx]
prefix = "n_antibot"

[nftables]
table = "n_antibot"
ports = [80, 443]
```

### Full reference

| Key | Type | Default | Description |
|---|---|---|---|
| `networks.presets` | list | `["tencent-cloud"]` | Built-in networks to block. See [lists](#-built-in-lists). |
| `networks.asns` | list | `[]` | Extra ASNs, written as `AS12345`. |
| `networks.block` | list | `[]` | Extra ranges (`203.0.113.0/24`, `2001:db8::/32`). |
| `networks.allow` | list | `[]` | Ranges **subtracted** from what is blocked, even inside a blocked network. |
| `robots.presets` | list | the 3 default families | Robot families to block. |
| `robots.block` | list | `[]` | Extra fragments. Matched anywhere in the `User-Agent`, case-insensitively. |
| `robots.allow` | list | `[]` | Fragments removed from the families. |
| `paths.exclude` | list | `["/.well-known/*"]` | Paths that are never cut. Forms: `/exact`, `/prefix/*`, `*.ext`. |
| `output.format` | string | `"caddy"` | `caddy`, `nginx`, `apache`, `nftables`, `cloudflare` or `json`. Can be overridden with `-f`. |
| `caddy.prefix` | string | `"nAntibot"` | Prefix of the matchers in the file. |
| `caddy.block_path` | string | `"/__n_antibot_blocked"` | Private path where requests are aborted. |
| `caddy.ip_matcher` | string | `"remote_ip"` | `remote_ip` (direct connection) or `client_ip` (behind a proxy). |
| `nginx.prefix` | string | `"n_antibot"` | Prefix of the nginx variables. |
| `nftables.table` | string | `"n_antibot"` | Name of the firewall table. |
| `nftables.ports` | list of numbers | `[80, 443]` | Protected ports (TCP and UDP). |

### Validations that protect you

A configuration is rejected, with a message naming the key and the reason, when:

| Case | Example | Message |
|---|---|---|
| Misspelled section or key | `[netwroks]` | `unknown section [netwroks]` |
| A robot that would cut off a browser or search engine | `block = ["Mozilla"]` | `'Mozilla' would block a real browser or search engine` |
| A fragment with regular-expression symbols | `block = ["bad\|bot"]` | `must be 3-64 characters of letters, digits, '_' or '-'` |
| A fragment that is too short | `block = ["ab"]` | same |
| Something that is not a range or an ASN | `asns = ["132203"]` | `is not an ASN like 'AS132203'` |
| An unsupported path form | `exclude = ["/a/*/b"]` | `must be '/exact', '/prefix/*' or '*.ext'` |
| Every list is empty | | `nothing to block` |

> [!WARNING]
> Always exclude the paths that **other servers** call: payment webhooks, APIs used by your integrations, health
> checks. Many integrations use python-requests or Go and would be cut off.

## 📦 Built-in lists

See them at any time with `n-antibot presets`.

### Networks

| Preset | Default | ASN | Description |
|---|:---:|---|---|
| `tencent-cloud` | ✅ | AS132203, AS45090 | Tencent Cloud, international and China. A common source of bots imitating Chrome. |
| `alibaba-cloud` | | AS45102 | Alibaba Cloud. |
| `huawei-cloud` | | AS136907 | Huawei Cloud. |

### Robots

| Preset | Default | Fragments | Description |
|---|:---:|---|---|
| `aggressive-crawlers` | ✅ | Bytespider, MJ12bot, DotBot, BLEXBot, PetalBot, MegaIndex, SeekportBot | Crawlers that bring no visits and load the site. |
| `scraping-libraries` | ✅ | python-requests, python-urllib, Go-http-client, Scrapy, aiohttp, libwww-perl | HTTP libraries used by scrapers. No `curl` or `wget`. |
| `vulnerability-scanners` | ✅ | zgrab, masscan, Nuclei, sqlmap, Nikto | Port and vulnerability scanners. |
| `seo-tools` | | AhrefsBot, SemrushBot, DataForSeoBot, serpstatbot, Barkrowler | Commercial SEO tools. Blocking them only hides your site from those tools. |
| `ai-training` | | GPTBot, ClaudeBot, anthropic-ai, CCBot, meta-externalagent, Amazonbot, cohere-ai | AI crawlers. Blocking them takes your site out of AI answers. |

## 🖥️ Commands

| Command | What it does | Exit code |
|---|---|---|
| `n-antibot generate [-c CFG] [-f FORMAT] [-o FILE]` | Downloads ranges and writes the file (or prints it). | `0` ok |
| `n-antibot check [-c CFG] [-f FORMAT] -o FILE` | Says whether the file is up to date. | `0` up to date · `1` out of date |
| `n-antibot install [SERVER] --site SITE [--check-url URL] [--dry-run] [--uninstall]` | Installs it on Caddy, nginx, Apache or nftables: backs up, validates, reloads, checks and rolls back on failure. | `0` · `5` not installed |
| `n-antibot report [-c CFG] LOG… [--csv FILE]` | Reads access logs: bots and ad clicks made by bots. [Guide](docs/en/ads-report.md). | `0` |
| `n-antibot report … --claim-dir DIR` | Also one file set per ad platform with what each one asks for. | `0` |
| `n-antibot serve [-c CFG] LOG…` | Read-only JSON API with that data. [Guide](docs/en/api.md). | `0` |
| `n-antibot test-agent [-c CFG] "USER-AGENT"` | Would this `User-Agent` be cut off? Uses no network. | `0` blocked · `2` allowed |
| `n-antibot test-ip [-c CFG] IP` | Would this IP be cut off? | `0` blocked · `2` allowed |
| `n-antibot presets` | Lists the built-in networks and robots. | `0` |
| `n-antibot init [-o FILE]` | Creates an example configuration (never overwrites). | `0` · `1` if it exists |
| `n-antibot --version` | Version. | `0` |

Error codes shared by all: `3` invalid configuration · `4` RIPEstat could not be read (nothing is written).

```console
$ n-antibot test-agent "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)"
BLOCKED by 'Bytespider'

$ n-antibot test-agent "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
allowed

$ n-antibot test-ip 43.173.132.9
BLOCKED by 43.173.0.0/16

$ n-antibot test-ip 66.249.66.1
allowed

$ n-antibot check -o /etc/caddy/n-antibot.caddy
/etc/caddy/n-antibot.caddy: up to date
```

## 🐍 Python API

```python
from n_antibot import Config, generate, load

# With the defaults
print(generate(Config().validate()))

# From a file
cfg = load("n-antibot.toml")
text = generate(cfg)

# Would this User-Agent be cut off?
cfg.blocks_agent("python-requests/2.32")   # -> 'python-requests'
cfg.blocks_agent("Mozilla/5.0 ... Chrome") # -> None
```

| Object | Description |
|---|---|
| `Config` | Immutable configuration. `.validate()` checks it; `.agents()`, `.all_asns()` and `.blocks_agent(ua)` give the final lists. |
| `load(path)` | Reads and validates a TOML file (`None` gives the defaults). |
| `generate(cfg)` | Returns the file text in the format of `cfg.format`. |
| `ConfigError` | The configuration is not valid. |
| `FetchError` | RIPEstat could not be read. |

## 🔄 Keeping the lists fresh

Cloud networks change their ranges. Regenerate the file from time to time; once a week is enough.
[`examples/n-antibot-update.sh`](examples/n-antibot-update.sh) does it for Caddy: it checks for changes, generates,
validates and reloads, and **keeps the previous file** if the new one does not validate.

```cron
# /etc/cron.d/n-antibot — Mondays at 4:00
0 4 * * 1  root  /usr/local/bin/n-antibot-update.sh
```

If you would rather decide when it changes, commit the generated file to your repository and run `n-antibot check`
in CI: it reports (exit code `1`) when the lists have changed.

## ✅ Checking that it works

From any computer, with `curl`:

```bash
# A browser: must answer 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/131.0 Safari/537.36' https://example.com/

# Google: must answer 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)' https://example.com/

# A scraper: 000 (connection cut)
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/

# An excluded path, same scraper: must answer
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/.well-known/security.txt
```

| Result | Meaning |
|---|---|
| `200`, `301`, `404`… | The request goes through and your site answers. |
| `000` | Connection cut by N-antibot: the server closes without sending an answer. |

## 🧹 Removing it

**Caddy**, with the installer:

```bash
sudo ./install/caddy.sh --site example.com --uninstall
```

By hand: delete the `import /etc/caddy/n-antibot.caddy` line and reload Caddy.

**nginx:** delete the `if ($n_antibot_block) { return 444; }` line and the `include`, then reload with
`sudo nginx -t && sudo nginx -s reload`.

## 📋 Requirements

| What | Version | What for |
|---|---|---|
| Python | 3.9 or later | Running `n-antibot` (standard library only; on 3.9 and 3.10, plus `tomli`) |
| Caddy | 2.x | If you use the `caddy` output |
| nginx | 1.x with `geo` and `map` (built in) | If you use the `nginx` output |
| Apache | 2.4 with `mod_rewrite` | If you use the `apache` output |
| nftables | Linux, as root | If you use the `nftables` output |
| Node.js | 18 or later | If you use the middleware in `integrations/node/` |
| Internet access | to `stat.ripe.net` | Only when generating the lists, not when serving the site |

Nothing has to be installed on the server itself if you generate the file elsewhere and copy it over.

## 🧬 Compatibility

These are the versions the tests run against on every change
([continuous integration](https://github.com/KrilinZ/N-antibot/actions/workflows/ci.yml)). Anything not listed
here is untested, even if it may work.

| Piece | Tested versions | How |
|---|---|---|
| **Python** | 3.9, 3.10, 3.11, 3.12, 3.13 and 3.14 | Every test, on each version |
| **Systems** | Ubuntu 22.04, 24.04 and 26.04, macOS | The tests for the servers available on each system |
| **Windows** | Windows Server (GitHub) | Generator and command line only: there are no servers to test |
| **Caddy** | 2.6.2 (Ubuntu 24.04 and 26.04) and 2.11 (macOS) | End to end |
| **nginx** | 1.18 (Ubuntu 22.04), 1.24 (Ubuntu 24.04) and 1.31 (macOS) | End to end |
| **Apache** | 2.4.52, 2.4.58, 2.4.66 and 2.4.67 | End to end, in `<VirtualHost>` and in `.htaccess` |
| **nftables** | 1.0.2 (Ubuntu 22.04) and 1.0.9 (Ubuntu 24.04) | End to end: loads the rules and checks the cut |
| **Node.js** | 18, 20, 22 and 24 | The middleware, with a real HTTP server |
| **Cloudflare** | | Not tested on an account: expression checked against their documentation |
| **Vercel** | | Not tested on a deployment: middleware logic only |

| Compatible with… | Detail |
|---|---|
| **IPv4 and IPv6** | In every output. The Node middleware also understands IPv4 written inside IPv6 (`::ffff:1.2.3.4`). |
| **HTTP/1.1, HTTP/2 and HTTP/3** | The cut is made by IP, `User-Agent` and path, which exist in all three. The firewall covers TCP and UDP. |
| **Proxies and CDNs** | With the real IP configured: `client_ip` in Caddy, `realip` in nginx, `mod_remoteip` in Apache. |
| **Docker** | The file is mounted into the container; the firewall also covers ports published by Docker. |
| **Your current rules** | Caddy: one `import`. nginx: variables with their own prefix. Apache: `Rewrite` rules that live alongside yours. nftables: a separate table. Nothing overwrites what you already have. |
| **Shared hosting** | Through `.htaccess`, if the host runs Apache 2.4 with `mod_rewrite`. |
| **Plain-text output** | Generated files and messages are ASCII: no encoding trouble on any console. |

## 🧪 Tests

```bash
git clone https://github.com/KrilinZ/N-antibot.git && cd N-antibot
pip install -e . pytest ruff
pytest -q
node --test tests/node/n-antibot.test.mjs
ruff check src tests && ruff format --check src tests
```

| File | What it checks |
|---|---|
| [`tests/test_unit.py`](tests/test_unit.py) | Merging and subtracting ranges, validation of the RIPEstat answer, retries, every configuration rule, that no built-in list cuts off a browser or search engine, the three output formats and the command line. |
| [`tests/test_servers.py`](tests/test_servers.py) | **End to end:** starts a real Caddy, nginx and Apache with the generated file and sends requests. Chrome, Googlebot and curl get `200`; Bytespider and python-requests are cut off, also on routes with their own `handle` and from an `.htaccess`; excluded paths answer. On Linux it also loads the nftables rules and checks that the blocked network can no longer connect. Each test is skipped when its server is not installed. |
| [`tests/node/n-antibot.test.mjs`](tests/node/n-antibot.test.mjs) | The Node middleware with a real HTTP server: IPv4 and IPv6 ranges, robots, excluded paths, connection cut and 403 mode. |

## 🚧 Limits: what N-antibot does not do

Worth knowing before you install it:

- **It does not detect bots by behaviour.** No browser fingerprinting, JavaScript challenges or CAPTCHA. A bot
  coming from a home IP (residential proxies) with a Chrome `User-Agent` gets through.
- **The `User-Agent` can be faked.** A scraper that changes its name does not match the robot list, though it still
  matches the network list if it comes from a blocked network.
- **Blocking a whole network has a cost.** If a real customer browses from a server in that network (a VPN hosted
  there, for instance), they will be cut off. That is what `networks.allow` is for.
- **It does not replace a web application firewall (WAF)** or per-IP rate limiting.
- **It depends on RIPEstat** at generation time. If it does not answer, nothing is generated and your previous file
  keeps working.

## ❓ FAQ

<details>
<summary><b>Does it affect SEO?</b></summary>

No. Googlebot, Bingbot, DuckDuckBot, Yandex and Applebot are in no list, and a configuration is rejected if one of
your rules could cut them off. The tests check it with their real `User-Agent` strings.
</details>

<details>
<summary><b>And my presence in ChatGPT, Claude or Perplexity?</b></summary>

Not either: AI crawlers are allowed by default. They are only blocked if you add the `ai-training` preset yourself.
</details>

<details>
<summary><b>Why cut the connection instead of answering 403?</b></summary>

Because answering costs. With the cut, the bot gets no headers and no body, and your application never sees the
request.
</details>

<details>
<summary><b>Can I protect several sites on the same server?</b></summary>

Yes. In Caddy, import the same file in each block (or run the installer once per site). In nginx, the `include`
goes once in `http { }` and the `if` line in each `server`.
</details>

<details>
<summary><b>A service of mine uses python-requests against my site and stopped working.</b></summary>

Three ways out, from most to least recommended: exclude the path it uses (`paths.exclude`), change your service's
`User-Agent`, or take the fragment out of the list (`robots.allow = ["python-requests"]`).
</details>

<details>
<summary><b>How many rules does it add?</b></summary>

With the default configuration, about 260 IP ranges and one regular expression with 18 names. The exact figure is
printed when generating: `241 IPv4 + 17 IPv6 ranges, 18 robots`.
</details>

<details>
<summary><b>Does it work behind Cloudflare?</b></summary>

Yes, as long as your server knows the visitor's real IP: `ip_matcher = "client_ip"` and `trusted_proxies` in Caddy,
or the `realip` module in nginx. Without that, the robot list works the same, but the network list would compare
Cloudflare's IP.
</details>

<details>
<summary><b>How do I know which ASN to block?</b></summary>

Look in your access logs for the IPs making the most requests and look them up on
[stat.ripe.net](https://stat.ripe.net/): it tells you which ASN they belong to. Add it to `networks.asns`.
</details>

## 🗺️ Roadmap

Ideas, with no committed date. If you need one, [say so in an issue](https://github.com/KrilinZ/N-antibot/issues).

| Idea | Status |
|---|---|
| Publish on PyPI (`pip install n-antibot`) | Pending |
| Outputs for HAProxy, Traefik and IIS | Pending |
| Docker image with the API | Pending |
| More built-in networks (other clouds) with their ASN verified | Pending |
| Test Cloudflare on a real account and Vercel on a deployment | Pending: today it is only checked against their documentation |
| Claim routes for TikTok Ads and Amazon Ads | Pending: no documented route was found |

What is already done, version by version: [CHANGELOG.md](CHANGELOG.md).

## 🗂️ Project layout

```text
N-antibot/
├── src/n_antibot/
│   ├── presets.py      # built-in networks and robots, and the User-Agents that are never cut
│   ├── config.py       # TOML configuration and its validations
│   ├── ranges.py       # RIPEstat download, merging and subtracting ranges
│   ├── render.py       # outputs: Caddy, nginx, Apache, nftables, Cloudflare and JSON
│   ├── report.py       # report from the logs: bots and ad clicks
│   ├── claims.py       # where each ad platform takes claims, and the per-platform file set
│   ├── api.py          # read-only API (n-antibot serve)
│   ├── installer.py    # n-antibot install: backs up, validates, reloads, checks and rolls back
│   ├── core.py         # generate(): from configuration to file
│   ├── cli.py          # command line
│   └── example.toml    # example configuration (n-antibot init)
├── install.sh          # one-command install (own environment, system Python untouched)
├── install/caddy.sh    # bash installer for Caddy, for servers without Python
├── integrations/node/  # middleware for Node.js, Express and Next.js
├── docs/es/ · docs/en/ # guides by technology and by use case
├── examples/           # Caddyfile, nginx.conf, weekly update and cases/ (configurations per use case)
├── tests/              # unit and end-to-end with real servers
└── assets/logo.png
```

## 🤝 Contributing

Proposals are welcome, especially:

- **New robots or networks**, with a reference showing why they belong (logs, the robot's documentation).
- **Outputs for other servers** (HAProxy, Traefik, IIS).
- **Bugs**: open an [issue](https://github.com/KrilinZ/N-antibot/issues) with your configuration and the output.

Before sending changes, run `pytest -q` and `ruff check src tests`. More in [CONTRIBUTING.md](CONTRIBUTING.md).

| Document | What for |
|---|---|
| [CHANGELOG.md](CHANGELOG.md) | What changed in each version |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to propose robots, networks, outputs and ad platforms |
| [SECURITY.md](SECURITY.md) | How to report a security problem |

## 📄 License

[MIT](LICENSE) © 2026 Nacho López.

IP ranges come from [RIPEstat](https://stat.ripe.net/), the public data service of the RIPE NCC.

<div align="center">
<br>
<img src="assets/logo.png" alt="N-antibot" width="120">
<br>
<sub><b>N-antibot</b> · Secure your digital ecosystem</sub>
</div>

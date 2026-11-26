# Changelog

All notable changes to N-antibot. Versions follow [semantic versioning](https://semver.org/).

## 0.9.0 (2026-11-26)

- **Bots that pose as a browser (`[stealth]`).** Fingerprint rules that cut a fake Chrome on residential proxies by
  how it talks, not by where it comes from. Every condition of a rule must hold. Three opt-in presets:
  `chrome-without-fetch-metadata` (Chrome 90+ over HTTPS without `Sec-Fetch-Mode` and `Sec-Ch-Ua`),
  `chrome-http1-without-fetch-metadata` (Chrome over HTTP/1.x to an HTTPS site without `Sec-Fetch-Mode`) and
  `residential-proxy-zh` (the fixed fingerprint of a scraper seen in November 2026).
- **Your own fingerprints** with `[[stealth.fingerprint]]`: protocol, HTTPS, headers with an exact value, missing
  headers, minimum Chrome version and Chrome versions behind today's stable.
- **Impossible Chrome versions** (`future_chrome`): newer than today's Canary, read from Google's version history.
- **Referer spam** (`referers`), also inside redirects such as `google.com/url?q=http://domain/`.
- **Guards that cannot be turned off:** a User-Agent that declares a robot or a tool, a signed agent
  (`Signature-Agent`), the published addresses of AI crawlers and search engines and `networks.allow` are never cut by
  these rules. A rule that would cut a real browser request (Chrome over HTTP/2, HTTP/3, HTTP/1.1 behind a proxy,
  plain HTTP, Edge, Android, Safari, Firefox) is refused when the configuration loads.
- `n-antibot ai-check` also tries 29 search engines, AI crawlers and assistants against the fingerprint rules, in the
  worst case. New `n-antibot test-request`.
- Caddy, nginx, Apache, Cloudflare, JSON and the Node middleware. The report counts these requests as `fingerprint`
  (Caddy JSON logs; referer and version rules also with combined logs).
- The default output does not change.

## 0.8.0 (2026-11-13)

- **AI crawlers and search engines are protected.** N-antibot downloads the address lists that OpenAI, Perplexity,
  Google, Microsoft, Apple, Mistral, Common Crawl and DuckDuckGo publish, and never cuts those addresses, even
  inside a cloud network you block. On by default (`[ai] protect`).
- A configuration that would cut an AI crawler by name is rejected unless `[ai] protect = false`.
- **`n-antibot ai-check`** reports, with today's data, whether a configuration lets each AI crawler and search
  engine in. Exit code 1 if any is cut.
- The Cloudflare expression keeps Cloudflare's verified bots.

## 0.7.0 (2026-11-13)

- **Ad bots.** The report now counts as a bot every paid ad click that comes from a data-center network, even when
  that cloud is not blocked.
- **`[ads] cut = true`.** The server cuts only the ad clicks coming from those networks; the rest of their traffic
  keeps getting in. Caddy, nginx, Apache, Cloudflare and the Node middleware.
- Ten more network presets, all opt-in: `aws`, `google-cloud`, `digitalocean`, `ovh`, `hetzner`, `linode`, `vultr`,
  `oracle-cloud`, `contabo`, `scaleway`.
- Downloaded ranges are cached for a day (`~/.cache/n-antibot`), and an older copy is used if a download fails.

## 0.6.0 (2026-11-12)

- **One-command install.** `install.sh` puts the `n-antibot` command in its own virtual environment, without
  touching the system Python.
- **`n-antibot install`.** Finds the site in Caddy, nginx or Apache, backs up, adds one line, validates with the
  server's own checker, reloads, checks the live site and rolls back on failure. Also loads nftables. `--dry-run`
  and `--uninstall`.

## 0.5.0 (2026-11-12)

- **Claim files per ad platform.** `n-antibot report --claim-dir` writes, for each platform, where to claim, the
  deadline, what the platform asks for, a text to paste, a CSV of the clicks and the matching log lines.
- **Where to claim.** Rules of Google Ads, Microsoft Advertising, LinkedIn, X, Meta and Pinterest, read on their own
  pages, with sources.
- **Data API.** `n-antibot serve`: read-only JSON API (summary, bots, ad clicks, claims, check, blocklist) with a
  bearer token and an OpenAPI 3.1 description.
- Campaign, ad group, ad and keyword are read from the landing URL. Meta and other platforms are recognised by
  `utm_source`.

## 0.4.0 (2026-11-12)

- **Traffic report.** `n-antibot report` reads Caddy, nginx and Apache access logs and counts bot requests and paid
  ad clicks made by bots, with CSV and JSON output.

## 0.3.0 (2026-11-12)

- Python 3.9 to 3.14 (was 3.11+). Output and messages are plain ASCII.
- Continuous integration on Ubuntu 22.04, 24.04 and 26.04, macOS and Windows, and Node 18 to 24.
- Compatibility table with the versions actually tested.

## 0.2.0 (2026-11-12)

- New outputs: Apache (also `.htaccess`), nftables and Cloudflare.
- Node.js middleware for Express and Next.js.
- Guides by technology and by use case, in Spanish and English, and eight ready configurations.

## 0.1.0 (2026-11-12)

- First release: generator for Caddy, nginx and JSON, TOML configuration, built-in network and robot lists, safe
  Caddy installer, end-to-end tests against real servers.

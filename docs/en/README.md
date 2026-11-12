# N-antibot documentation

[← Back to the README](../../README.en.md) · [🇪🇸 Español](../es/README.md)

> Tested versions of every piece: [compatibility table](../../README.en.md#-compatibility).

## By technology

Pick the guide for whatever sits **in front of your site** (the first thing that receives the visitor's request).

| Technology | Output | What it cuts | Answer to the bot | Test status |
|---|---|---|---|---|
| [Caddy](caddy.md) | `caddy` | networks and robots | connection closed | ✅ end to end with a real Caddy |
| [nginx](nginx.md) | `nginx` | networks and robots | connection closed (444) | ✅ end to end with a real nginx |
| [Apache](apache.md) (also `.htaccess`) | `apache` | networks and robots | 403 | ✅ end to end with a real Apache 2.4 |
| [Linux firewall](nftables.md) (nftables) | `nftables` | networks only | packets dropped | ✅ end to end on Linux (continuous integration) |
| [Node.js and Express](node-express.md) | `json` + middleware | networks and robots | connection closed or 403 | ✅ with a real Node HTTP server |
| [Next.js and Vercel](vercel-nextjs.md) | `json` + middleware | networks and robots | 403 | ⚠️ logic tested; not tested on a Vercel deployment |
| [Cloudflare](cloudflare.md) | `cloudflare` | networks and robots | Cloudflare block | ⚠️ expression written from their documentation; not tested on an account |

Not sure what serves your site? Look at the `server` header:

```bash
curl -sI https://example.com | grep -i -E '^(server|via|cf-ray|x-vercel-id)'
```

| If you see… | Use the guide for… |
|---|---|
| `server: Caddy` | [Caddy](caddy.md) |
| `server: nginx` | [nginx](nginx.md) |
| `server: Apache` | [Apache](apache.md) |
| `server: cloudflare` or `cf-ray` | [Cloudflare](cloudflare.md), or your server's guide with the real IP configured |
| `server: Vercel` or `x-vercel-id` | [Next.js and Vercel](vercel-nextjs.md) |
| Something else (LiteSpeed, IIS, a PaaS…) | [Node.js](node-express.md) if your app is Node, or the [firewall](nftables.md) if the server is yours |

## Bot and ad-click report

[Bot and ad-click report](ads-report.md): how many visits are bots and how many paid clicks (Google Ads, Microsoft
Ads…) were made by a bot, with a CSV to claim them. ✅ Tested with real logs from Caddy, nginx and Apache.

## Data API

[Data API](api.md): `n-antibot serve`, a read-only JSON API with the bots, the ad clicks and where to claim them.
✅ Tested with the real server. [OpenAPI specification](../openapi.json).

## By use case

[Use cases](cases.md): ready-to-copy configurations, each with its file in
[`examples/cases/`](../../examples/cases/).

| Case | File |
|---|---|
| [Online shop](cases.md#-online-shop) | [`shop.toml`](../../examples/cases/shop.toml) |
| [Blog, magazine or corporate site](cases.md#-blog-magazine-or-corporate-site) | [`blog.toml`](../../examples/cases/blog.toml) |
| [Site with a public API](cases.md#-site-with-a-public-api) | [`public-api.toml`](../../examples/cases/public-api.toml) |
| [WordPress](cases.md#-wordpress) | [`wordpress.toml`](../../examples/cases/wordpress.toml) |
| [Behind a CDN or load balancer](cases.md#-behind-a-cdn-or-load-balancer) | [`behind-cdn.toml`](../../examples/cases/behind-cdn.toml) |
| [Maximum protection](cases.md#-maximum-protection) | [`strict.toml`](../../examples/cases/strict.toml) |
| [No AI crawlers](cases.md#-no-ai-crawlers) | [`no-ai.toml`](../../examples/cases/no-ai.toml) |
| [Protecting ad campaigns](cases.md#-protecting-ad-campaigns) | [`ad-campaigns.toml`](../../examples/cases/ad-campaigns.toml) |
| [Cutting before the web server](cases.md#-cutting-before-the-web-server) | [`firewall.toml`](../../examples/cases/firewall.toml) |
| [Several sites on one server](cases.md#-several-sites-on-one-server) | |
| [I am being hit from another network](cases.md#-i-am-being-hit-from-another-network) | |
| [I blocked someone I should not have](cases.md#-i-blocked-someone-i-should-not-have) | |

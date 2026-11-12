# N-antibot on Cloudflare

[← Documentation](README.md) · [🇪🇸 Español](../es/cloudflare.md)

> ⚠️ **Not tested on a real account.** The expression is built from the fields and functions Cloudflare documents
> (`ip.src.asnum`, `ip.src`, `http.user_agent`, `http.request.uri.path`, `lower()`, `starts_with()`,
> `ends_with()`), and the tests check its shape and that it fits the 4,096-character limit. Before leaving it on
> "Block", try it for a few days with the "Log" or "Managed Challenge" action.

## When to use this guide

Your site goes through Cloudflare (orange proxy on). Cutting there is the most effective: the request never reaches
your server.

## Steps

**1. Generate the expression.**

```bash
n-antibot generate -c n-antibot.toml -f cloudflare | tail -1
```

```text
(ip.src.asnum in {132203 45090} or lower(http.user_agent) contains "bytespider" or … ) and not starts_with(http.request.uri.path, "/.well-known/")
```

**2. Create the rule.** In the Cloudflare dashboard: your domain → **Security** → **WAF** → **Custom rules** (the
menu name may vary with the dashboard version) → **Create rule** → **Edit expression**. Paste the expression.

**3. Choose the action.** Start with **Log** (if your plan allows it) or **Managed Challenge**; once you see that
only bots match, switch it to **Block**.

**4. Deploy the rule.**

## How your configuration is translated

| In `n-antibot.toml` | In the expression |
|---|---|
| `networks.presets` and `networks.asns` | `ip.src.asnum in {132203 45090}`. Cloudflare knows every visitor's ASN: **no ranges to download or paste**. |
| `networks.block` | `ip.src in {203.0.113.0/24}` |
| `networks.allow` | `and not ip.src in {…}` |
| `robots` | `lower(http.user_agent) contains "bytespider"` (one per robot) |
| `paths.exclude` `/api/*` | `and not starts_with(http.request.uri.path, "/api/")` |
| `paths.exclude` `/health` | `and not http.request.uri.path eq "/health"` |
| `paths.exclude` `*.xml` | `and not ends_with(http.request.uri.path, ".xml")` |

## Good to know

- **No ranges to maintain.** Matching by ASN means Cloudflare follows the network's changes for you. You only need
  to regenerate the expression when your configuration changes.
- **Size limit.** An expression can be up to 4,096 characters. The default configuration takes under 1,000. If you
  add many robots or ranges and go over, split it into two rules.
- **Verified bots.** The expression ends with `and not cf.client.bot`: the search engines and crawlers that
  Cloudflare considers verified are never cut. Remove it with `protect = false` under `[ai]`.
- **Combining it with your server.** If you also install N-antibot on Caddy or nginx behind Cloudflare, configure
  the visitor's real IP (see their guides).

## Remove it

Disable or delete the rule under **Security → WAF → Custom rules**.

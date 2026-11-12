# N-antibot on Caddy

[← Documentation](README.md) · [🇪🇸 Español](../es/caddy.md)

> ✅ **Tested end to end** with a real Caddy: browsers, Google and curl get an answer; blocked robots and networks
> see the connection closed, also on routes with their own `handle`.

## When to use this guide

Your site is served by Caddy 2, directly or as a reverse proxy for your application.

## The short way

```bash
sudo n-antibot install caddy --site example.com --check-url https://example.com
```

It generates the file, backs up, adds the line to your site's configuration, validates, reloads and checks live; if
anything fails, it puts everything back. With `--dry-run` it only says what it would do; with `--uninstall` it
removes it. Tested end to end with a real server. What follows is the same, step by step and by hand.

## Steps

**1. Generate the file.**

```bash
n-antibot generate -c n-antibot.toml -o n-antibot.caddy
```

**2. Install it.** With the installer (backs up, validates, reloads, checks and rolls back if anything fails):

```bash
sudo ./install/caddy.sh --site example.com --snippet n-antibot.caddy --check-url https://example.com
```

Or by hand: copy the file and add the `import` as the **first line** of your site block.

```caddyfile
example.com {
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

## Special situations

| Situation | What to do |
|---|---|
| **Behind Cloudflare or a load balancer** | `ip_matcher = "client_ip"` under `[caddy]` and `trusted_proxies` in Caddy's global options. Without it, Caddy compares the proxy's IP. |
| **Several sites in the same Caddyfile** | Run the installer once per site (`--site`), or add the same `import` to each block. |
| **Caddy in Docker** | Mount the file into the container (`-v ./n-antibot.caddy:/etc/caddy/n-antibot.caddy`) and reload with `docker exec <container> caddy reload --config /etc/caddy/Caddyfile`. |
| **Block with several addresses** (`example.com, www.example.com {`) | `--site example.com` finds it: the first address of the line is enough. |
| **You already use a `/__n_antibot_blocked` path** | Change `block_path` under `[caddy]`. |
| **Two files on the same site** (e.g. different rules) | Give them a different `prefix` under `[caddy]` so the matchers do not clash. |

## Why `rewrite` + `handle` and not a `handle @bots`

Caddy sorts `handle` blocks with a named matcher **after** every `handle /path/*`. A `handle @bots { abort }` would
not reach `/api/*` or `/product/*` if they have their own `handle`. The generated file uses a `rewrite` (which runs
before any `handle`) to a private path and an exact-path `handle` (which wins over prefix ones) with `abort`.

## Check

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 000
```

## Remove it

```bash
sudo ./install/caddy.sh --site example.com --uninstall
```

By hand: delete the `import /etc/caddy/n-antibot.caddy` line and reload Caddy.

# N-antibot on nginx

[← Documentation](README.md) · [🇪🇸 Español](../es/nginx.md)

> ✅ **Tested end to end** with a real nginx: browsers, Google and curl get an answer; blocked robots and networks
> see the connection closed; excluded paths answer.

## When to use this guide

Your site is served by nginx, directly or as a reverse proxy (Node, PHP-FPM, Python, Ruby…).

## The short way

```bash
sudo n-antibot install nginx --site example.com --check-url https://example.com
```

It generates the file, backs up, adds the line to your site's configuration, validates, reloads and checks live; if
anything fails, it puts everything back. With `--dry-run` it only says what it would do; with `--uninstall` it
removes it. Tested end to end with a real server. What follows is the same, step by step and by hand.

## Steps

**1. Generate the file and copy it.**

```bash
n-antibot generate -c n-antibot.toml -f nginx -o n-antibot.conf
sudo cp n-antibot.conf /etc/nginx/n-antibot.conf
```

**2. Include it once inside `http { }`.** On Debian and Ubuntu the easiest way is `conf.d`, which is already
included inside `http`:

```bash
sudo cp n-antibot.conf /etc/nginx/conf.d/n-antibot.conf
```

Or add the line by hand to `/etc/nginx/nginx.conf`:

```nginx
http {
	include /etc/nginx/n-antibot.conf;
	# ...
}
```

**3. Add one line to every `server` you want to protect.**

```nginx
server {
	server_name example.com;

	if ($n_antibot_block) { return 444; }

	location / {
		proxy_pass http://127.0.0.1:3000;
	}
}
```

**4. Validate and reload.**

```bash
sudo nginx -t && sudo nginx -s reload
```

## How it works

| Piece | What it does |
|---|---|
| `geo $n_antibot_net` | `1` if the visitor's IP is in a blocked network. nginx resolves it with a tree: fast even with hundreds of ranges. |
| `map $http_user_agent $n_antibot_agent` | `1` if the `User-Agent` contains a blocked robot (case-insensitive). |
| `map $uri $n_antibot_excluded` | `1` if the path is in `[paths] exclude`. |
| `map … $n_antibot_block` | `1` when there is a network or robot match and the path is not excluded. |
| `return 444` | nginx's own code: closes the connection without sending an answer. |

## Special situations

| Situation | What to do |
|---|---|
| **Behind Cloudflare, a CDN or a load balancer** | Configure the `realip` module (`set_real_ip_from <proxy ranges>;` and `real_ip_header X-Forwarded-For;` or `CF-Connecting-IP`). Then `geo` sees the real IP. |
| **You would rather answer 403** | Replace `return 444;` with `return 403;`. |
| **You only want to log, not cut yet** | Add `$n_antibot_block` to your `log_format` and leave the `if` out. The log will show what would be cut. |
| **You already have variables with that name** | Change `prefix` under `[nginx]`. |
| **nginx in Docker** | Mount the file into `/etc/nginx/conf.d/` and reload with `docker exec <container> nginx -s reload`. |
| **Protect only a part** | Put the `if` inside the `location` you want instead of the `server`. |

## Check

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 000
```

## Remove it

Delete the `if ($n_antibot_block) { return 444; }` line and the `include` (or the file in `conf.d`), then reload:

```bash
sudo nginx -t && sudo nginx -s reload
```

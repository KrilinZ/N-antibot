# Use cases

[← Documentation](README.md) · [🇪🇸 Español](../es/casos.md)

Every case has a ready configuration in [`examples/cases/`](../../examples/cases/). The tests load and generate
all of them, so they are always valid. Copy one, adjust it and generate with the format of
[your technology](README.md#by-technology):

```bash
n-antibot generate -c examples/cases/shop.toml -f caddy -o n-antibot.caddy
```

> [!TIP]
> Before installing, ask the configuration what it would do with a given visit:
> `n-antibot test-agent -c mine.toml "python-requests/2.32"` and `n-antibot test-ip -c mine.toml 43.173.132.9`.

## 🛒 Online shop

**Problem:** bots crawling the whole catalogue from data centers, and price scrapers. They use up the server and
pollute your statistics, but they never buy.

**Watch out for:** the payment gateway and your integrations call your site from servers, often with HTTP
libraries. If they are cut off, orders are not confirmed.

[`shop.toml`](../../examples/cases/shop.toml)

```toml
[paths]
exclude = [
  "/.well-known/*",  # certificates
  "/api/*",          # your API: payment webhooks, back office, mobile app
  "/webhooks/*",     # other providers calling you
  "/health",         # uptime monitor
]
```

| Check afterwards | How |
|---|---|
| A test order reaches "paid" | Make a purchase in your gateway's test mode |
| Google Merchant still reads your feed | `curl -A 'Mozilla/5.0 (compatible; Googlebot/2.1)' https://your-shop/feed.xml` |
| The admin panel opens | Sign in with your browser |

## 📰 Blog, magazine or corporate site

**Problem:** aggressive crawlers and content scrapers.

**Watch out for:** RSS readers and aggregators read your feeds with programs, not browsers. Leave the feeds open.

[`blog.toml`](../../examples/cases/blog.toml)

```toml
[paths]
exclude = ["/.well-known/*", "/feed", "/feed/*", "/rss.xml", "/atom.xml", "/robots.txt"]
```

## 🔌 Site with a public API

**Problem:** you want to slow down scrapers of the site, but other people's programs are your customers.

**Two ways:**

1. If the API lives under its own path, exclude it (`exclude = ["/api/*"]`) and keep the default lists.
2. If the API and the site share paths, drop the HTTP-library family:

[`public-api.toml`](../../examples/cases/public-api.toml)

```toml
[robots]
presets = ["aggressive-crawlers", "vulnerability-scanners"]
```

## 📝 WordPress

**Problem:** the same as any site, plus scanners looking for vulnerable plugins.

**Watch out for:** WordPress receives legitimate calls from servers: the REST API (apps, Jetpack, payment
gateways), `wp-cron.php` and `admin-ajax.php`.

[`wordpress.toml`](../../examples/cases/wordpress.toml), with Apache output: see the [Apache guide](apache.md),
option B if you can only touch `.htaccess`.

```toml
[paths]
exclude = [
  "/.well-known/*",
  "/wp-json/*",
  "/wp-cron.php",
  "/wp-admin/admin-ajax.php",
  "/xmlrpc.php",          # remove this line if you do not use XML-RPC
  "/feed",
  "/feed/*",
]

[output]
format = "apache"
```

If your WordPress sits behind nginx, use the same path list with `-f nginx`.

## 🌐 Behind a CDN or load balancer

**Problem:** your server sees the proxy's IP, not the visitor's. The robot list works the same, but the network
list would compare the wrong IP.

| Your server | What to configure |
|---|---|
| Caddy | `ip_matcher = "client_ip"` under `[caddy]` and `trusted_proxies` in Caddy: [`behind-cdn.toml`](../../examples/cases/behind-cdn.toml) |
| nginx | `realip` module: `set_real_ip_from` and `real_ip_header` |
| Apache | `mod_remoteip`: `RemoteIPHeader` and `RemoteIPTrustedProxy` |
| Cloudflare in front | Better still: cut at Cloudflare with the [Cloudflare guide](cloudflare.md) |
| Firewall (nftables) | No use behind a proxy |

## 🔒 Maximum protection

**Problem:** bots reach you from several clouds, and you do not care about showing up in third-party SEO tools.

**Watch out for:** the more networks you cut, the more likely you leave someone legitimate out. Look at your logs
first and let your own servers through with `allow`.

[`strict.toml`](../../examples/cases/strict.toml)

```toml
[networks]
presets = ["tencent-cloud", "alibaba-cloud", "huawei-cloud"]
allow = ["203.0.113.10/32"]     # your server or your monitor

[robots]
presets = ["aggressive-crawlers", "scraping-libraries", "vulnerability-scanners", "seo-tools"]
```

## 🤖 No AI crawlers

**Problem:** you do not want AI crawlers reading your content.

**Watch out for:** your site will stop showing up in answers from ChatGPT, Claude and the like. It is a business
decision, not a technical one.

[`no-ai.toml`](../../examples/cases/no-ai.toml)

```toml
[robots]
presets = ["aggressive-crawlers", "scraping-libraries", "vulnerability-scanners", "ai-training"]
block = ["PerplexityBot"]       # add any other by name
```

## 🧱 Cutting before the web server

**Problem:** you want those networks not to reach any web service on the machine, whatever you have installed
(Docker containers included).

[`firewall.toml`](../../examples/cases/firewall.toml) and the [firewall guide](nftables.md). It only cuts networks:
for robots, combine it with your web server's guide.

## 🏢 Several sites on one server

One generated file serves them all.

| Server | How |
|---|---|
| Caddy | The same `import` in each block, or the installer once per site (`--site`) |
| nginx | The `include` once in `http { }` and the `if` line in each `server` |
| Apache | The same `Include` in each `<VirtualHost>` |
| Firewall | Protects every web port on the machine at once |

If each site needs different excluded paths, generate one file per site with its own configuration. In Caddy, give
each a different `prefix`; in nginx, a different `prefix` under `[nginx]`.

## 🎯 I am being hit from another network

**1. Find the IPs making the most requests** in your access log:

```bash
awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -20
```

**2. See who they belong to** on [stat.ripe.net](https://stat.ripe.net/): look up the IP and note its ASN.

**3. Add it** and check before installing:

```toml
[networks]
presets = ["tencent-cloud"]
asns = ["AS45102"]
```

```bash
n-antibot test-ip -c mine.toml 47.74.1.1
```

For a single range, without an ASN: `block = ["203.0.113.0/24"]`.

> [!WARNING]
> Do not block home or mobile access providers by ASN (your own carrier, for example): they are your customers.
> This tool is meant for **server** networks.

## 🆘 I blocked someone I should not have

| Symptom | Fix |
|---|---|
| A service of yours or a partner's stopped working | Exclude the path it uses: `paths.exclude` |
| A legitimate program uses a blocked library | `robots.allow = ["aiohttp"]`, or change its `User-Agent` |
| A customer or a monitor is in a blocked network | `networks.allow = ["203.0.113.10/32"]` |
| You do not know which rule cuts it | `n-antibot test-agent -c mine.toml "its user-agent"` and `n-antibot test-ip -c mine.toml its.ip` |
| It has to go right now | See "Remove it" in your technology's guide: it is one line |

After changing the configuration, generate the file again and reinstall it.

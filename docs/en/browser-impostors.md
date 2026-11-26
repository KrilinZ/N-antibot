# Bots that pose as a browser

[← Back to the documentation](README.md) · [🇪🇸 Español](../es/navegadores-falsos.md)

Since version 0.9.0. For scrapers that rent **residential proxies**: every request leaves from a different home
connection with a Chrome `User-Agent`, so neither network lists nor robot lists stop them. How they talk gives them
away.

## Spotting them in your log

With Caddy's JSON log (it has protocol, TLS and headers), look for requests that claim Chrome and carry no
`Sec-Fetch-Mode`:

```bash
jq -r 'select(.request.headers["User-Agent"][0] | test("Chrome/"))
  | select(.request.headers["Sec-Fetch-Mode"] == null)
  | [.request.proto, .request.remote_ip, (.request.headers["Accept-Language"][0] // "-"),
     .request.headers["User-Agent"][0]] | @tsv' /var/log/caddy/access.log | sort | uniq -c | sort -rn | head
```

A real Chrome, Edge, Opera or Brave always sends to an HTTPS site:

| Header | Since | Example |
|---|---|---|
| `Sec-Fetch-Mode`, `Sec-Fetch-Site`, `Sec-Fetch-Dest` | Chrome 76-80 | `navigate`, `none`, `document` |
| `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform` | Chrome 89 | `"Chromium";v="159", "Google Chrome";v="159", ...` |

and negotiates HTTP/2 or HTTP/3 when the server offers it. The scraper of the real case (November 2026) always used
HTTP/1.1, none of those headers, `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8`, `Accept-Encoding: gzip`,
`Connection: close`, `Pragma: no-cache` and Chrome versions 123 to 154 (all real but old: stable was 159). Googlebot
and GoogleOther also use HTTP/1.1 without those headers, but they declare themselves in their `User-Agent`: that is
why the rules never look at anyone who declares a robot.

## Turning it on

```toml
[paths]
exclude = ["/.well-known/*", "/api/*"]

[stealth]
presets = ["chrome-http1-without-fetch-metadata", "chrome-without-fetch-metadata", "residential-proxy-zh"]
future_chrome = true
referers = []
```

A ready example: [`examples/cases/browser-impostors.toml`](../../examples/cases/browser-impostors.toml). Then, as
always:

```bash
n-antibot ai-check -c n-antibot.toml        # search engines and AI: all "ok"
n-antibot generate -c n-antibot.toml -o /etc/caddy/n-antibot.caddy
sudo caddy reload --config /etc/caddy/Caddyfile
```

## The rules

| Rule | Conditions (all at once) |
|---|---|
| `chrome-without-fetch-metadata` | Chrome 90 or later, HTTPS, no `Sec-Fetch-Mode` and no `Sec-Ch-Ua`. |
| `chrome-http1-without-fetch-metadata` | Chrome, HTTP/1.0 or HTTP/1.1, HTTPS, no `Sec-Fetch-Mode`. |
| `residential-proxy-zh` | Chrome, HTTP/1.x, HTTPS, `Accept-Language` exactly `zh-CN,zh;q=0.9,en;q=0.8`, no `Sec-Fetch-Mode`. |
| `chrome-language-not-from-chrome` | Chrome 90 or later, HTTPS, no `Sec-Ch-Ua` and an `Accept-Language` Chrome never writes (such as Firefox's `en-US,en;q=0.5`). |
| `languages = ["zh-CN,zh;q=0.9,en;q=0.8"]` | Chrome, HTTPS, no `Sec-Fetch-Mode` and an `Accept-Language` equal to one of these values, over any protocol. `residential-proxy-zh` widened to the languages you choose. |
| `block_languages = ["zh"]` | Any browser whose first language is one of these (`zh` covers `zh`, `zh-CN`, `zh-TW`...). **It also cuts people** who browse in that language: see [Languages](#languages). |
| `future_chrome = true` | Chrome newer than today's Canary + `future_margin` (2 by default). The version is read from Google's official API (`versionhistory.googleapis.com`) when generating; if it does not answer, nothing is written. |
| `referers = ["spam.example"]` | The `Referer` contains that domain, also inside `google.com/url?q=http://spam.example/` or encoded (`%2F%2Fspam.example`). |

And your own, with `[[stealth.fingerprint]]`:

| Key | What it asks for |
|---|---|
| `name` | Rule name (lowercase, digits and `-`). Shown in the file's comments and in the report. |
| `browser` | `"chrome"` (default: the `User-Agent` claims Chrome or a Chromium) or `"any"` (any `Mozilla/5.0`). |
| `protocols` | `["http/1.0", "http/1.1", "http/2", "http/3"]`, any of them. |
| `https` | `true`: only over HTTPS. |
| `headers` | `{ "Header" = "exact value" }`. No quotes, backslashes, braces, `*` or `\|`. |
| `missing` | Headers that must be absent, e.g. `["Sec-Fetch-Mode"]`. |
| `chrome_min` | The claimed Chrome version is at least this. |
| `chrome_behind` | The claimed Chrome version is more than N versions behind today's stable. |

## Languages

`Accept-Language` gives a lot away, but a language alone is not enough: "zh-CN,zh;q=0.9,en;q=0.8" is exactly what a
Chrome set to Chinese sends. So there are three levels, from safest to least safe:

1. **`chrome-language-not-from-chrome`** (preset). Chrome always writes the language the same way: the first one
   without `q`, then `q=0.9`, `0.8`... down to `0.1`. Firefox writes `en-US,en;q=0.5`. A "Chrome" that sends Firefox's
   language and no `Sec-Ch-Ua` carries a header set borrowed from another tool. Seen on 2026-11-26: Chrome on Android
   over HTTP/2, 872 requests from 260 addresses in one day. A real Chrome with an extension that changes the language
   still sends `Sec-Ch-Ua` and passes; a missing language does not count as odd.
2. **`languages`**: the fixed languages of a scraping kit, exact. They are only cut when `Sec-Fetch-Mode` is missing
   too, which a real Chrome always sends over HTTPS, so a real Chinese visitor is not cut.
3. **`block_languages`**: cuts by language, nothing else. It is a business decision, not a fingerprint: it stops
   robots that arrive with a complete browser from a home address, but also every customer who browses in that
   language. Search engines and AI crawlers still pass (by name, signature and official address). Use it only if you
   really do not sell to people who speak that language.

```toml
[stealth]
presets = ["chrome-language-not-from-chrome"]
languages = ["zh-CN,zh;q=0.9,en;q=0.8"]
# block_languages = ["zh"]   # only if you do not sell in Chinese: it also cuts people
```

## What is never cut

1. **Anyone who declares a robot or a tool.** If the `User-Agent` contains `bot`, `spider`, `crawl`, `slurp`,
   `compatible;`, `google`, `bing`, `preview`, `lighthouse`, `pagespeed`, `facebook`, `openai`, `gpt`, `claude`,
   `anthropic`, `perplexity`, `applebot`, `mistral`, `duckduck`, `amazon`, `yandex`, `baidu`, `petal`, `cohere`,
   `yahoo`, `headlesschrome`... (and the names of every protected AI crawler and of your `robots.allow`), no rule cuts it.
2. **Signed agents** with Web Bot Auth (`Signature-Agent`).
3. **The official addresses** of AI crawlers and search engines (with `[ai] protect = true`, the default) and your
   `networks.allow` ranges.
4. **Excluded paths** (`paths.exclude`).

On top of that, when the configuration loads every rule is tried against real browser requests (Chrome over HTTP/2,
HTTP/3 and HTTP/1.1 behind a corporate proxy, in Spanish and in Chinese, Chrome over plain HTTP, Edge, Android, Mac,
Safari, Firefox). If any of them would be cut, the configuration is refused:

```console
$ n-antibot generate -c bad.toml
n-antibot: configuration error: stealth: rule 'only-http1' would cut a real visitor: Chrome behind a corporate proxy (HTTP/1.1)
```

## Checking it

```bash
# Would this request be cut?
n-antibot test-request -c n-antibot.toml --protocol HTTP/1.1 -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

# Live, against your site (the connection must be closed: curl prints 000 or a connection error)
curl -s -o /dev/null -w '%{http_code}\n' --http1.1 -H 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8' \
  -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36' \
  https://example.com/

# And a real browser still gets in (200)
curl -s -o /dev/null -w '%{http_code}\n' --http2 -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Ch-Ua: "Chromium";v="159"' \
  -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36' \
  https://example.com/
```

`n-antibot report` counts these requests separately (`fingerprint <rule>`). nginx and Apache "combined" logs carry no
headers: only referer spam and version rules apply there.

## By server

| Server | How | Answer |
|---|---|---|
| Caddy | One matcher per rule (`header`, `header_regexp`, `protocol https`, `expression {http.request.proto}`, `not remote_ip`) | connection closed |
| nginx | One `map` per rule over `$server_protocol`, `$https` and the headers; `$n_antibot_block` adds them up | 444 |
| Apache | One `RewriteCond` block per rule (`%{SERVER_PROTOCOL}`, `%{HTTPS}`, `%{HTTP:Header}`) | 403 |
| Cloudflare | One group in the expression (`http.request.version`, `ssl`, `http.request.headers`) | block |
| Node | `check({ ip, userAgent, path, headers, protocol, https })` | connection closed or 403 |
| nftables | No: a firewall does not see headers. The configuration is refused. | |

## Limits

- **Behind a CDN** the protocol and HTTPS your server sees are the CDN's. Use rules without `protocols` or `https`,
  or set the rule in the CDN.
- **Over plain HTTP** a real Chrome sends no Fetch Metadata: it cannot be told apart, and nothing is cut. Redirect to
  HTTPS.
- **Baidu's renderer** (Chrome with no "spider" in its name) falls under `chrome-http1-without-fetch-metadata`. If you
  want it in, add its ranges to `networks.allow`.
- **Your own site's checks** with Playwright or Puppeteer (`route.fetch`, `request`) send the `HeadlessChrome` agent
  over HTTP/1.1 without Fetch Metadata. They say they are an automated browser, so they pass. If you run them from
  your server, do **not** put its address in `networks.allow`: your live checks with curl would pass too and you would
  not know whether the cut works.
- **Cloudflare**: rules with a Chrome version or a language use `matches` (Business or Enterprise plan). Not tested on a real
  account.
- A bot driving a full real browser (every header, HTTP/2) from a home IP still gets through.

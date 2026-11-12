# Bot and ad-click report

[← Documentation](README.md) · [🇪🇸 Español](../es/informe-anuncios.md)

> ✅ **Tested end to end** with the logs written by a real Caddy, nginx and Apache: visits are sent with and without
> `gclid`, from browsers and from robots, and the report counts them correctly in all three formats.

`n-antibot report` reads your server's access logs and answers two questions:

1. **How many visits are bots**, from which networks and robots, and how many were cut off?
2. **How many paid ad clicks were made by a bot?** With date, IP, browser and `gclid`, in a CSV ready to ask Google
   to investigate them.

It sends nothing anywhere: it reads your files on your machine. The only thing it downloads is the network ranges,
just like `generate`.

## Usage

```bash
n-antibot report /var/log/caddy/access.log
n-antibot report /var/log/nginx/access.log /var/log/nginx/access.log.1 /var/log/nginx/access.log.*.gz
n-antibot report -c n-antibot.toml access.log --since 2026-10-01 --until 2026-10-31 --csv bot-clicks.csv
```

```text
N-antibot traffic report
  Period:    2026-11-12 09:00 to 2026-11-12 09:03 UTC
  Requests:  6 from 4 IP addresses (1 unreadable lines)

Bots
  Requests from bots: 3 (50.0%) from 2 IPs
    cut off:  2
    served:   1   <- N-antibot is not stopping these yet
          2  AS132203 (tencent-cloud)
          1  python-requests

Paid ad clicks
  google: 4 clicks
    bots:        3 (75.0%)  [network 2, robot 1]
    suspicious:  0 (0.0%)  [repeated IP 0, no resources 0]
    clean:       1
  microsoft: 1 clicks
    bots:        0 (0.0%)  [network 0, robot 0]
    suspicious:  1 (100.0%)  [repeated IP 0, no resources 1]
    clean:       0

IP addresses behind bot and suspicious ad clicks (clicks, IP, why)
      2  43.173.132.9                             AS132203 (tencent-cloud) 43.173.0.0/16
      1  8.8.8.8                                  python-requests
      1  81.40.1.2                                loaded no page resources (hint)
```

## Options

| Option | Description |
|---|---|
| `FILE…` | One or more logs. `.gz` is accepted, and `-` reads standard input. |
| `-c CONFIG` | Your configuration: it decides which networks and robots count as bots. Defaults without it. |
| `--since YYYY-MM-DD` | First day to include (UTC). |
| `--until YYYY-MM-DD` | Last day to include (UTC). |
| `--csv FILE` | Writes the bot and suspicious ad clicks to a CSV. |
| `--all-clicks` | With `--csv`: include the clean clicks too. |
| `--json` | Prints the summary as JSON, for your dashboard or alerts. |
| `--min-repeat N` | Ad clicks from one IP to flag it as repeated (default 3). |

## Which logs it understands

| Server | Format | How to enable it |
|---|---|---|
| **Caddy** | JSON (its default) | Caddy does **not** keep access logs unless you ask. Add to your site block: `log { output file /var/log/caddy/access.log }` |
| **nginx** | `combined` (its default) | On by default: `/var/log/nginx/access.log` |
| **Apache** | `combined` | On by default in most installs: `/var/log/apache2/access.log` |

Requests that were cut off are logged too, and the report recognises them by their code: `0` in Caddy (`abort`),
`444` in nginx and `403` in Apache.

> [!NOTE]
> Behind a proxy or CDN, the log must record the visitor's real IP (see "Behind a CDN" in the
> [use cases](cases.md#-behind-a-cdn-or-load-balancer)). If it records the proxy's, the report cannot tell which
> network each visit comes from.

## How it recognises an ad click

By the identifier the platform appends to the landing URL:

| Platform | Parameters |
|---|---|
| Google Ads | `gclid`, `gbraid`, `wbraid` |
| Microsoft Ads | `msclkid` |
| TikTok, X, LinkedIn | `ttclid`, `twclid`, `li_fat_id` |
| Any other | `utm_medium` = `cpc`, `ppc`, `paid`, `paid-social`, `display`… (the platform comes from `utm_source`) |

Each identifier counts **only once**, even if the visitor reloads the page. `fbclid` does not count: Meta appends it
to every link, paid or not.

> [!IMPORTANT]
> In Google Ads, auto-tagging must be on for URLs to carry `gclid`. Without it, the report only sees clicks that
> bring `utm_medium=cpc`.

## How it classifies each click

| Verdict | Reason | What it means | Reliability |
|---|---|---|---|
| **bot** | `from a blocked network` | The IP belongs to a server network you block (with its ASN and range). | High: people do not browse from a data center |
| **bot** | `blocked robot or scraper` | The browser identifies itself as a robot or a scraping library. | High |
| **suspicious** | `same IP clicked several ads` | The same IP made 3 or more different ad clicks in the period. | Hint |
| **suspicious** | `loaded no page resources` | That IP only requested the page: no images, styles or scripts. A real browser requests them. | Hint |
| **clean** | | None of the above. | |

"Hints" are not proof: a whole office may share one IP, and a browser may have the page cached. They help you
decide what to look at, not to claim fraud.

## Claiming bot clicks from Google

Google describes the process in [About invalid traffic](https://support.google.com/google-ads/answer/11182074): it
filters the invalid traffic it detects on its own and, if you request an investigation and it finds more, it
**notifies you of the credit**. The investigation covers **the last 60 days** and is requested with the
[Click Quality Form](https://support.google.com/google-ads/contact/click_quality).

This is what Google asks for and where it comes from:

| Google asks for | Where it comes from |
|---|---|
| Date range (last 60 days) | `--since` and `--until`; the report prints the period |
| IP addresses with repetitive clicks or no conversions | The `ip` column of the CSV and the "IP addresses behind…" list |
| Browser or device | The `user_agent` column |
| **GCLIDs** of the suspicious clicks | The `click_id` column |
| Web server logs | The access log itself |
| Why it is suspicious | The `reason` and `detail` columns (network, ASN, robot) |
| Campaigns, ad groups and keywords | Your Google Ads account: the log does not know them |

```bash
n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --until 2026-11-12 --csv bot-clicks.csv
```

```csv
date_utc,time_utc,platform,click_id,ip,verdict,reason,detail,cut_off,status,user_agent,url
2026-11-12,09:00:01,google,AAA111,43.173.132.9,bot,from a blocked network,AS132203 (tencent-cloud) 43.173.0.0/16,yes,444,Mozilla/5.0 (Windows NT 10.0…,/producto/a/?gclid=AAA111
```

> [!WARNING]
> **Cutting the bot off does not avoid the charge.** The click happens at Google before the visit reaches your
> site. N-antibot keeps the bot from using your server and polluting your statistics; the money is recovered by
> claiming.

Three things worth knowing before you claim:

- **Google may not have charged you already.** Check the "Invalid traffic" card on your account's Overview page and the invalid
  clicks columns first: some of these clicks may already be discounted.
- **Google does not confirm click by click.** Its help says an investigation will not tell which specific clicks
  were marked valid or invalid; if it finds additional invalid traffic, it notifies you of the credit.
- **CSV times are in UTC.** Keep that in mind when comparing them with Google Ads reports.

## Privacy

IP addresses are personal data. The report stays on your machine; share it only with the platform you are claiming
from and keep it only as long as the claim lasts.

## Running it every week

```cron
# /etc/cron.d/n-antibot-report — Mondays at 7:00, the week's summary as JSON
0 7 * * 1  root  n-antibot report /var/log/nginx/access.log /var/log/nginx/access.log.1 --json > /var/log/n-antibot-report.json
```

In the JSON, a non-zero `bots.served` means some bots still get an answer: check that the N-antibot file is
installed and up to date.

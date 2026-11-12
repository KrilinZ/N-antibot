# Bot and ad-click report

[← Documentation](README.md) · [🇪🇸 Español](../es/informe-anuncios.md)

> ✅ **Tested end to end** with the logs written by a real Caddy, nginx and Apache: visits are sent with and without
> `gclid`, from browsers and from robots, and the report counts them correctly in all three formats.

`n-antibot report` reads your server's access logs and answers two questions:

1. **How many visits are bots**, from which networks and robots, and how many were cut off?
2. **How many paid ad clicks were made by a bot?** With date, IP, browser and `gclid`, in a CSV ready to claim
   them, plus one file set per platform with what each one asks for.

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
| `--claim-dir DIR` | Writes one file set per ad platform with what each one asks for. See [Claiming](#claiming-bot-clicks). |
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
| Meta and any other | `utm_medium` = `cpc`, `ppc`, `paid`, `paid-social`, `display`… The platform comes from `utm_source` (`facebook`, `instagram`, `fb`, `ig` and `meta` count as Meta) |

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

## Claiming bot clicks

What each platform's official documentation says, read on 12 November 2026. Open the source before claiming: rules
change.

| Platform | Where to claim | Deadline | What it asks for | What you can expect |
|---|---|---|---|---|
| **Google Ads** | [Click Quality Form](https://support.google.com/google-ads/contact/click_quality) | Last 60 days | Dates; campaigns and ad groups; keywords; web server logs with IP, browser and GCLID; why it is suspicious | Specialists review it and email the findings. If they find more invalid traffic, they notify you of the credit. No click-by-click confirmation. [Source](https://support.google.com/google-ads/answer/11182074) |
| **Microsoft Advertising** (Bing) | [Support](https://go.microsoft.com/fwlink?LinkId=398371), saying it is an "invalid clicks" issue | Best within 30 days; no investigation after 60 | Ad group and its number; ad ID and keywords; dates; what you see in your reports or logs; a log sample if asked | They try to finish within 9 days and recommend reimbursement if the traffic is invalid. [Source](https://help.ads.microsoft.com/#apex/ads/en/60220/0) |
| **LinkedIn Ads** | [Marketing Solutions support](https://www.linkedin.com/help/lms/ask), in writing | 90 days | The fees you dispute and why | Ad credit only, at LinkedIn's discretion; no cash refund. [Source](https://www.linkedin.com/legal/sas-terms) |
| **X Ads** | [Support ticket](https://ads.x.com/en/help), in writing | 60 days from the charge (US agreement) | The charges you dispute | A refund only if they find a billing or technical error. [Source](https://help.x.com/en/business-and-advertising/billing-basics) |
| **Meta Ads** (Facebook, Instagram) | [Ads payment support form](https://www.facebook.com/help/contact/649167531904667). **No documented process for invalid clicks** | None stated | It does not say | Decided case by case, at Meta's discretion, and final. At least one month. No refunds for poor performance. [Source](https://www.facebook.com/business/help/211313200321572) |
| **Pinterest Ads** | Support. **No documented process for invalid clicks** | None stated | It does not say | It says standard charges are usually not eligible for a refund. [Source](https://help.pinterest.com/en/business/article/refunds-and-chargebacks) |
| **TikTok Ads, Amazon Ads** | No process found in their help (searched only; their pages were not opened one by one) | | | |

### The file set per platform

`--claim-dir` writes, for every platform with bot or suspicious clicks, three files with what each one asks for:

```bash
n-antibot report /var/log/nginx/access.log* --since 2026-10-01 --claim-dir claim/
```

| File | Content |
|---|---|
| `<platform>-claim.txt` | Where to claim, the deadline, what the platform asks for, how many clicks are still within the deadline, a summary, the IPs with the reason and a text ready to paste |
| `<platform>-clicks.csv` | One click per row, with every column below |
| `<platform>-log-sample.log` | The exact web server log lines of those clicks (up to 500) |

| What they ask for | CSV column | Where it comes from |
|---|---|---|
| Dates | `date_utc`, `time_utc` | The log |
| GCLID or other click identifier | `click_id` | The URL (`gclid`, `msclkid`…) |
| IP address | `ip` | The log |
| Browser or device | `user_agent` | The log |
| Why it is suspicious | `verdict`, `reason`, `detail` | N-antibot: network with its ASN, robot or hint |
| Campaign | `campaign` | `utm_campaign`, `gad_campaignid`, `campaignid` |
| Ad group | `ad_group` | `utm_adgroup`, `adgroupid`, `adset_id` |
| Ad | `ad_id` | `adid`, `ad_id`, `creative`, `utm_content` |
| Keyword | `keyword` | `utm_term`, `keyword` |
| Whether it can still be claimed | `within_deadline` | The platform's deadline (60 or 90 days) |
| Whether the visit was cut off | `cut_off`, `status` | The log |

Campaign, ad group, ad and keyword only appear when the landing URL carries them. To make it carry them, add them to
the campaign's tracking template; for example, in Google Ads:
`{lpurl}?utm_campaign={campaignid}&utm_adgroup={adgroupid}&utm_content={creative}&utm_term={keyword}`.

> [!WARNING]
> **Cutting the bot off does not avoid the charge.** The click happens at the platform before the visit reaches your
> site. N-antibot keeps the bot from using your server and polluting your statistics; the money is recovered by
> claiming, and no platform guarantees it.

Three things worth knowing before you claim:

- **You may not have been charged.** Platforms filter part of the invalid traffic on their own. In Google Ads, check
  the "Invalid traffic" card on your account's Overview page first.
- **Google does not confirm click by click.** Its help says an investigation will not tell which specific clicks
  were marked valid or invalid; if it finds additional invalid traffic, it notifies you of the credit.
- **CSV times are in UTC.** Keep that in mind when comparing them with the platform's reports.

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

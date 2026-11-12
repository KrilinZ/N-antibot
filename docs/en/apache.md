# N-antibot on Apache

[← Documentation](README.md) · [🇪🇸 Español](../es/apache.md)

> ✅ **Tested end to end** with a real Apache 2.4, both included in a `<VirtualHost>` and pasted into an
> `.htaccess`: browsers, Google and curl get `200`; blocked robots and networks get `403`; excluded paths answer.

## When to use this guide

- Your site is served by Apache 2.4 and you can edit its configuration, **or**
- you are on shared hosting and can only touch `.htaccess` (WordPress, PrestaShop, Joomla…).

It needs `mod_rewrite`, which is enabled on almost every host.

> [!NOTE]
> Apache cannot close a connection from its configuration, so the bot gets a **403 Forbidden** instead of the hard
> cut of Caddy or nginx. It is a minimal answer, and your application (PHP, database) never runs.

## Option A: in the server configuration

```bash
n-antibot generate -c n-antibot.toml -f apache -o n-antibot.conf
sudo cp n-antibot.conf /etc/apache2/n-antibot.conf
```

```apache
<VirtualHost *:443>
	ServerName example.com
	Include /etc/apache2/n-antibot.conf
	# ... the rest of your configuration
</VirtualHost>
```

```bash
sudo a2enmod rewrite                       # Debian and Ubuntu, if it was not enabled
sudo apachectl configtest && sudo apachectl graceful
```

## Option B: in `.htaccess`

```bash
n-antibot generate -c n-antibot.toml -f apache -o n-antibot.htaccess
```

Paste the content **at the top** of the `.htaccess` in your site root, above your CMS rules (the
`# BEGIN WordPress` block, for instance). Nothing needs reloading.

## How it works

```apache
RewriteEngine On
RewriteCond %{REQUEST_URI} "!^/\.well\-known/"                # 1. the path is not excluded
RewriteCond %{HTTP_USER_AGENT} "(Bytespider|MJ12bot|…)" [NC,OR]  # 2. and it is a robot…
RewriteCond expr "-R '1.12.0.0/14' || -R '1.116.0.0/15' || …" [OR]  #    …or comes from a blocked network
RewriteCond expr "-R '240d:c010:5c::/48' || -R '240d:c040::/43'"
RewriteRule ^ - [F,L]                                           # 3. then, 403
```

Conditions are joined with "and", except those flagged `[OR]`, which group together.

## Special situations

| Situation | What to do |
|---|---|
| **Behind Cloudflare, a CDN or a load balancer** | Enable `mod_remoteip` (`RemoteIPHeader X-Forwarded-For` and `RemoteIPTrustedProxy <proxy ranges>`). Then `-R` compares the real IP. |
| **WordPress** | Use [`examples/cases/wordpress.toml`](../../examples/cases/wordpress.toml): it excludes the REST API, `wp-cron.php` and `admin-ajax.php`. See [cases](cases.md#-wordpress). |
| **Error 500 after pasting it into `.htaccess`** | The host does not allow `RewriteEngine` (`AllowOverride`) or runs Apache 2.2, which does not understand `expr`. Remove the block and ask your provider. |
| **LiteSpeed** | LiteSpeed reads `.htaccess`, but its support for `RewriteCond expr` has not been tested here. |
| **Several sites** | Add the same `Include` to each `<VirtualHost>`. |

## Check

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 403
```

## Remove it

Delete the `Include` line and reload (`sudo apachectl graceful`), or delete the block from `.htaccess`.

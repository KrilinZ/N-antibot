# Bots que se hacen pasar por un navegador

[← Volver a la documentación](README.md) · [🇬🇧 English](../en/browser-impostors.md)

Desde la versión 0.9.0. Sirve para los raspadores que alquilan **proxies residenciales**: cada petición sale de una
conexión de casa distinta y lleva un `User-Agent` de Chrome, así que ni las listas de redes ni las de robots los
paran. Lo que los delata es cómo hablan.

## Cómo reconocerlos en tu registro

Con el registro JSON de Caddy (trae protocolo, TLS y cabeceras), busca peticiones que digan ser Chrome y no traigan
`Sec-Fetch-Mode`:

```bash
jq -r 'select(.request.headers["User-Agent"][0] | test("Chrome/"))
  | select(.request.headers["Sec-Fetch-Mode"] == null)
  | [.request.proto, .request.remote_ip, (.request.headers["Accept-Language"][0] // "-"),
     .request.headers["User-Agent"][0]] | @tsv' /var/log/caddy/access.log | sort | uniq -c | sort -rn | head
```

Un Chrome, Edge, Opera o Brave de verdad manda siempre a una web HTTPS:

| Cabecera | Desde | Ejemplo |
|---|---|---|
| `Sec-Fetch-Mode`, `Sec-Fetch-Site`, `Sec-Fetch-Dest` | Chrome 76-80 | `navigate`, `none`, `document` |
| `Sec-Ch-Ua`, `Sec-Ch-Ua-Mobile`, `Sec-Ch-Ua-Platform` | Chrome 89 | `"Chromium";v="159", "Google Chrome";v="159", …` |

y negocia HTTP/2 o HTTP/3 cuando el servidor lo ofrece. El raspador del caso real (noviembre de 2026) iba siempre por
HTTP/1.1, sin ninguna de esas cabeceras, con `Accept-Language: zh-CN,zh;q=0.9,en;q=0.8`, `Accept-Encoding: gzip`,
`Connection: close`, `Pragma: no-cache` y versiones de Chrome de la 123 a la 154 (todas reales pero antiguas: la
estable era la 159). Googlebot y GoogleOther también van por HTTP/1.1 y sin esas cabeceras, pero se declaran en su
`User-Agent`: por eso las reglas nunca miran a quien se declara robot.

## Activarlo

```toml
[paths]
exclude = ["/.well-known/*", "/api/*"]

[stealth]
presets = ["chrome-http1-without-fetch-metadata", "chrome-without-fetch-metadata", "residential-proxy-zh"]
future_chrome = true
referers = []
```

Hay un ejemplo listo en [`examples/cases/browser-impostors.toml`](../../examples/cases/browser-impostors.toml).
Después, como siempre:

```bash
n-antibot ai-check -c n-antibot.toml        # buscadores e IA: todos «ok»
n-antibot generate -c n-antibot.toml -o /etc/caddy/n-antibot.caddy
sudo caddy reload --config /etc/caddy/Caddyfile
```

## Las reglas

| Regla | Condiciones (todas a la vez) |
|---|---|
| `chrome-without-fetch-metadata` | Chrome 90 o posterior, HTTPS, sin `Sec-Fetch-Mode` y sin `Sec-Ch-Ua`. |
| `chrome-http1-without-fetch-metadata` | Chrome, HTTP/1.0 o HTTP/1.1, HTTPS, sin `Sec-Fetch-Mode`. |
| `residential-proxy-zh` | Chrome, HTTP/1.x, HTTPS, `Accept-Language` exacto `zh-CN,zh;q=0.9,en;q=0.8`, sin `Sec-Fetch-Mode`. |
| `future_chrome = true` | Chrome más nuevo que la Canary de hoy + `future_margin` (2 por defecto). La versión se lee de la API oficial de Google (`versionhistory.googleapis.com`) al generar; si no responde, no se escribe nada. |
| `referers = ["spam.example"]` | El `Referer` contiene ese dominio, también dentro de `google.com/url?q=http://spam.example/` o codificado (`%2F%2Fspam.example`). |

Y las tuyas, con `[[stealth.fingerprint]]`:

| Clave | Qué pide |
|---|---|
| `name` | Nombre de la regla (minúsculas, cifras y `-`). Sale en los comentarios del archivo y en el informe. |
| `browser` | `"chrome"` (por defecto: el `User-Agent` dice Chrome o un Chromium) o `"any"` (cualquier `Mozilla/5.0`). |
| `protocols` | `["http/1.0", "http/1.1", "http/2", "http/3"]`, los que quieras. |
| `https` | `true`: solo por HTTPS. |
| `headers` | `{ "Cabecera" = "valor exacto" }`. Sin comillas, barras invertidas, llaves, `*` ni `\|`. |
| `missing` | Cabeceras que deben faltar, p. ej. `["Sec-Fetch-Mode"]`. |
| `chrome_min` | La versión de Chrome que dice es al menos esta. |
| `chrome_behind` | La versión de Chrome que dice va más de N versiones por detrás de la estable de hoy. |

## Qué nunca se corta

1. **Quien se declara robot o herramienta.** Si el `User-Agent` contiene `bot`, `spider`, `crawl`, `slurp`,
   `compatible;`, `google`, `bing`, `preview`, `lighthouse`, `pagespeed`, `facebook`, `openai`, `gpt`, `claude`,
   `anthropic`, `perplexity`, `applebot`, `mistral`, `duckduck`, `amazon`, `yandex`, `baidu`, `petal`, `cohere`,
   `yahoo`… (y los nombres de todas las IA protegidas y de tu `robots.allow`), ninguna regla lo corta.
2. **Los agentes firmados** con Web Bot Auth (`Signature-Agent`).
3. **Las direcciones oficiales** de las IA y los buscadores (con `[ai] protect = true`, como viene) y tus rangos de
   `networks.allow`.
4. **Las rutas excluidas** (`paths.exclude`).

Además, al cargar la configuración se prueban todas las reglas contra peticiones reales de navegadores (Chrome por
HTTP/2, HTTP/3 y HTTP/1.1 detrás de un proxy corporativo, en español y en chino, Chrome por HTTP sin cifrar, Edge,
Android, Mac, Safari, Firefox). Si alguna cortara una, la configuración se rechaza:

```console
$ n-antibot generate -c mala.toml
n-antibot: configuration error: stealth: rule 'solo-http1' would cut a real visitor: Chrome behind a corporate proxy (HTTP/1.1)
```

## Comprobarlo

```bash
# ¿Cortaría esta petición?
n-antibot test-request -c n-antibot.toml --protocol HTTP/1.1 -H "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8" \
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

# En vivo, contra tu web (debe cerrar la conexión: curl da el código 000 o un error de conexión)
curl -s -o /dev/null -w '%{http_code}\n' --http1.1 -H 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8' \
  -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36' \
  https://example.com/

# Y un navegador real sigue entrando (200)
curl -s -o /dev/null -w '%{http_code}\n' --http2 -H 'Sec-Fetch-Mode: navigate' -H 'Sec-Ch-Ua: "Chromium";v="159"' \
  -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36' \
  https://example.com/
```

`n-antibot report` cuenta estas peticiones aparte (`fingerprint <regla>`). Con registros «combined» de nginx o Apache
no hay cabeceras: solo se aplican el spam de referer y las reglas de versión.

## Por servidor

| Servidor | Cómo lo hace | Respuesta |
|---|---|---|
| Caddy | Un matcher por regla (`header`, `header_regexp`, `protocol https`, `expression {http.request.proto}`, `not remote_ip`) | conexión cerrada |
| nginx | Un `map` por regla sobre `$server_protocol`, `$https` y las cabeceras; `$n_antibot_block` las suma | 444 |
| Apache | Un bloque `RewriteCond` por regla (`%{SERVER_PROTOCOL}`, `%{HTTPS}`, `%{HTTP:Cabecera}`) | 403 |
| Cloudflare | Un grupo en la expresión (`http.request.version`, `ssl`, `http.request.headers`) | bloqueo |
| Node | `check({ ip, userAgent, path, headers, protocol, https })` | conexión cerrada o 403 |
| nftables | No: el cortafuegos no ve las cabeceras. La configuración se rechaza. | |

## Límites

- **Detrás de un CDN** el protocolo y el HTTPS que ve tu servidor son los del CDN. Usa reglas sin `protocols` ni
  `https`, o configura la regla en el CDN.
- **En HTTP sin cifrar** un Chrome real no manda Fetch Metadata: no se puede distinguir y no se corta. Redirige a HTTPS.
- **El renderizador de Baidu** (Chrome sin «spider» en el nombre) cae en `chrome-http1-without-fetch-metadata`. Si lo
  quieres dentro, añade sus rangos a `networks.allow`.
- **Cloudflare**: las reglas con versión de Chrome usan `matches` (plan Business o Enterprise). Sin probar en una
  cuenta real.
- Un bot que maneja un navegador real completo (todas las cabeceras, HTTP/2) desde una IP doméstica sigue pasando.

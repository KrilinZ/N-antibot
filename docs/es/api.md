# API de datos

[← Documentación](README.md) · [🇬🇧 English](../en/api.md) · [Especificación OpenAPI](../openapi.json)

> ✅ **Probada con el servidor real en marcha:** permisos, filtros, paginación, CSV, errores, registros que rotan y
> fallo de la descarga de rangos. Las respuestas de ejemplo de esta página son salidas reales.

`n-antibot serve` levanta una API **de solo lectura** con los mismos datos que `n-antibot report`: bots, clics de
anuncios hechos por bots y dónde reclamarlos. Responde en JSON (o CSV) para que la consultes desde tu panel, una hoja
de cálculo, un script o una alerta.

- [Arrancarla](#arrancarla) · [Autenticación](#autenticación) · [Direcciones](#direcciones) · [Errores](#errores)
- [Ejemplos](#ejemplos) · [Dejarla en marcha](#dejarla-en-marcha) · [Seguridad](#seguridad) · [Cómo se comporta](#cómo-se-comporta)

## Arrancarla

```bash
export N_ANTIBOT_TOKEN="$(openssl rand -hex 24)"
n-antibot serve -c n-antibot.toml '/var/log/nginx/access.log*'
# n-antibot: API on http://127.0.0.1:8787 (token required)
```

| Opción | Por defecto | Descripción |
|---|---|---|
| `REGISTRO…` | (obligatorio) | Registros de acceso. Admite comodines **entre comillas** (`'access.log*'`): se vuelven a buscar en cada consulta, así que los archivos que rotan entran solos. También `.gz`. |
| `-c CONFIG` | valores por defecto | Tu configuración: qué redes y robots cuentan como bot. |
| `--host` | `127.0.0.1` | Dirección en la que escucha. Fuera de `127.0.0.1` exige clave. |
| `--port` | `8787` | Puerto. |
| `--token-file ARCHIVO` | | Archivo con la clave. Alternativa a la variable `N_ANTIBOT_TOKEN`. |
| `--cors-origin ORIGEN` | | Permite que un panel web en ese origen (`https://panel.example.com`) llame a la API desde el navegador. |
| `--refresh-hours H` | `24` | Cada cuántas horas se vuelven a descargar los rangos de las redes. |

## Autenticación

Con clave, cada petición lleva la cabecera `Authorization`:

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" http://127.0.0.1:8787/v1/summary
```

| Regla | Detalle |
|---|---|
| La clave va **solo en la cabecera** | Si llega en la dirección (`?token=`), la API responde `400 token_in_url`: las direcciones acaban en registros e historiales. |
| Mínimo 16 caracteres | Con una más corta, el servicio no arranca. |
| Sin clave, solo en local | Si no hay clave, la API solo arranca en `127.0.0.1`. En otra dirección se niega a arrancar. |
| Sin clave nunca | `/health` y `/v1/openapi.json` son las únicas direcciones abiertas. |

## Direcciones

| Dirección | Qué devuelve |
|---|---|
| [`GET /health`](#get-health) | Si el servicio está en marcha, y su versión |
| [`GET /v1/summary`](#get-v1summary) | Resumen: peticiones, bots y clics de anuncios por plataforma |
| [`GET /v1/bots`](#get-v1bots) | Bots por red y por robot, y los visitantes con más peticiones que no están bloqueados |
| [`GET /v1/ad-clicks`](#get-v1ad-clicks) | Los clics de anuncios, uno a uno, con su veredicto (JSON o CSV) |
| [`GET /v1/claims`](#get-v1claims) | Dónde se reclama en cada plataforma, qué pide, y cuántos clics tienes dentro de plazo |
| [`GET /v1/check`](#get-v1check) | ¿Se bloquearía esta IP o este navegador? |
| [`GET /v1/blocklist`](#get-v1blocklist) | Los rangos y robots en uso |
| `GET /v1/openapi.json` | Esta API descrita en OpenAPI 3.1 |

Parámetros comunes de periodo, en las direcciones que los admiten:

| Parámetro | Formato | Descripción |
|---|---|---|
| `since` | `AAAA-MM-DD` | Primer día incluido (UTC). Sin él, desde el principio de los registros. |
| `until` | `AAAA-MM-DD` | Último día incluido (UTC). Sin él, hasta el final. |

### `GET /health`

Sin clave. Para tu monitor.

```json
{ "status": "ok", "version": "0.5.0" }
```

### `GET /v1/summary`

Parámetros: `since`, `until`.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "requests": 8,
  "ips": 5,
  "unreadable_lines": 1,
  "bots": {
    "requests": 5,
    "ips": 3,
    "cut_off": 4,
    "served": 1,
    "by": { "AS132203 (tencent-cloud)": 4, "python-requests": 1 }
  },
  "ad_clicks": {
    "google": { "network": 3, "agent": 1, "clean": 1, "total": 5 },
    "meta": { "network": 1, "total": 1 },
    "microsoft": { "no-resources": 1, "total": 1 }
  },
  "top_unblocked": [
    { "ip": "81.40.1.1", "requests": 2, "resources": 1, "user_agent": "Mozilla/5.0 (iPhone) Safari" }
  ]
}
```

| Campo | Significado |
|---|---|
| `period.from`, `period.to` | Primera y última petición leídas (UTC). |
| `requests`, `ips` | Peticiones y direcciones IP distintas. |
| `unreadable_lines` | Líneas del registro que no son accesos. |
| `bots.requests`, `bots.ips` | Peticiones de bots y desde cuántas IP. |
| `bots.cut_off` | Las que se cortaron (estado `0` en Caddy, `444` en nginx, `403` en Apache). |
| `bots.served` | Las que recibieron respuesta. Si no es `0`, el freno no está instalado o no está al día. |
| `bots.by` | Reparto por red (con su ASN) y por robot. |
| `ad_clicks.<plataforma>` | Clics de pago: `total`, `network`, `agent` y `datacenter` (bots), `repeated` y `no-resources` (sospechosos), `clean`. |
| `top_unblocked` | Los visitantes con más peticiones que no están bloqueados, con cuántos recursos (imágenes, estilos) pidieron. |

### `GET /v1/bots`

Parámetros: `since`, `until`. Es la parte de bots del resumen, sin los anuncios.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "total_requests": 8,
  "requests": 5,
  "ips": 3,
  "cut_off": 4,
  "served": 1,
  "by": { "AS132203 (tencent-cloud)": 4, "python-requests": 1 },
  "top_unblocked": [ { "ip": "81.40.1.1", "requests": 2, "resources": 1, "user_agent": "Mozilla/5.0 (iPhone) Safari" } ]
}
```

`total_requests` son todas las peticiones del periodo; `requests`, las de bots (`cut_off` + `served`).

### `GET /v1/ad-clicks`

| Parámetro | Valores | Por defecto | Descripción |
|---|---|---|---|
| `since`, `until` | `AAAA-MM-DD` | | Periodo. |
| `verdict` | `bot`, `suspicious`, `clean`, `all` | `all` | Qué clics devolver. |
| `platform` | `google`, `microsoft`, `meta`… | todas | Solo esa plataforma. |
| `limit` | 1 a 1000 | `100` | Clics por página. |
| `offset` | 0 o más | `0` | Clics que se saltan. |
| `format` | `json`, `csv` | `json` | `csv` devuelve todos los que coinciden, sin paginar. |

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" "http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&limit=1"
```

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "total": 5,
  "limit": 1,
  "offset": 0,
  "clicks": [
    {
      "timestamp": "2026-11-12T09:00:01+00:00",
      "date_utc": "2026-11-12",
      "time_utc": "09:00:01",
      "platform": "google",
      "click_id": "AAA111",
      "ip": "43.173.132.9",
      "verdict": "bot",
      "reason": "from a blocked network",
      "detail": "AS132203 (tencent-cloud) 43.173.0.0/16",
      "cut_off": true,
      "status": 444,
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
      "campaign": null,
      "ad_group": null,
      "ad_id": null,
      "keyword": null,
      "url": "/product/a/?gclid=AAA111"
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `total` | Clics que cumplen los filtros (no solo los de esta página). |
| `click_id` | El `gclid`, `msclkid`… del clic. Si la visita de pago no trae identificador, `(no id) IP ruta`. |
| `verdict` | `bot`, `suspicious` o `clean`. |
| `reason`, `detail` | Por qué: la red con su ASN y rango, el robot, o el indicio. `null` en los limpios. |
| `cut_off` | `true` si la visita se cortó. El clic se cobra igual: ocurre en la plataforma antes de llegar a tu web. |
| `status` | Código con el que respondió tu servidor. |
| `campaign`, `ad_group`, `ad_id`, `keyword` | Lo que traiga la dirección (`utm_campaign`, `gad_campaignid`, `adgroupid`, `utm_term`…). `null` si no lo trae. |

Para descargar el CSV listo para adjuntar:

```bash
curl -H "Authorization: Bearer $N_ANTIBOT_TOKEN" \
  "http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&platform=google&since=2026-10-01&format=csv" -o google-bots.csv
```

### `GET /v1/claims`

Parámetros: `since`, `until`. Una entrada por plataforma, con lo que dice su documentación oficial (leída el día de
`checked`) y tus clics del periodo.

```json
{
  "period": { "from": "2026-11-12T09:00:01+00:00", "to": "2026-11-12T10:00:09+00:00" },
  "platforms": [
    {
      "platform": "google",
      "name": "Google Ads",
      "has_process": true,
      "where": "Click Quality Form",
      "url": "https://support.google.com/google-ads/contact/click_quality",
      "deadline_days": 60,
      "asks": [
        "Date range of the suspicious activity (within the past 60 days)",
        "Campaign and ad group names",
        "Suspicious keywords",
        "Web server logs: IP addresses with repetitive clicks or clicks without conversions",
        "Web server logs: browser or device information",
        "Web server logs: GCLIDs of the suspicious clicks",
        "A brief explanation of why the traffic is suspicious"
      ],
      "outcome": "Specialists review the last 60 days and email the findings; if more invalid traffic is found, Google notifies you of the credit. It does not confirm click by click.",
      "source": "https://support.google.com/google-ads/answer/11182074",
      "checked": "2026-11-12",
      "clicks": 5,
      "bot_clicks": 4,
      "suspicious_clicks": 0,
      "flagged_within_deadline": 4
    }
  ]
}
```

| Campo | Significado |
|---|---|
| `has_process` | `true` si la plataforma documenta una vía para disputar clics no válidos. |
| `where`, `url` | Dónde se reclama. |
| `deadline_days` | Plazo en días desde la actividad. `null` si no lo indica. |
| `asks` | Lo que la plataforma dice que necesita. Vacío si no lo dice. |
| `outcome` | Qué puedes esperar. |
| `source`, `checked` | La página oficial de donde sale y el día en que se leyó. |
| `clicks`, `bot_clicks`, `suspicious_clicks` | Tus clics de esa plataforma en el periodo. |
| `flagged_within_deadline` | Clics de bots y sospechosos que aún están dentro del plazo. |

### `GET /v1/check`

| Parámetro | Descripción |
|---|---|
| `ip` | Dirección IPv4 o IPv6. |
| `user_agent` | Cabecera `User-Agent`. |
| `path` | Ruta pedida, para aplicar las rutas excluidas. Por defecto `/`. |

Hace falta `ip`, `user_agent` o los dos.

```json
{
  "ip": "43.173.132.9",
  "user_agent": "Mozilla/5.0",
  "path": "/",
  "is_bot": true,
  "reason": "network",
  "match": "AS132203 (tencent-cloud) 43.173.0.0/16",
  "path_excluded": false,
  "would_block": true
}
```

| Campo | Significado |
|---|---|
| `is_bot` | Está en una red bloqueada o es un robot bloqueado. |
| `reason` | `network` o `agent`; `null` si no es bot. |
| `match` | El rango con su ASN, o el nombre del robot. |
| `path_excluded` | La ruta está en `[paths] exclude`. |
| `would_block` | `is_bot` y la ruta no está excluida: lo que haría tu servidor. |

### `GET /v1/blocklist`

Lo mismo que `n-antibot generate -f json`: `asns`, `ipv4`, `ipv6`, `user_agents`, `user_agent_regex` y
`exclude_paths`. Sirve para alimentar otro sistema (un cortafuegos, un panel) desde un solo sitio.

## Errores

Siempre con la misma forma:

```json
{ "error": { "code": "invalid_parameter", "message": "since must be a date like 2026-11-12" } }
```

| Estado | `code` | Cuándo |
|:---:|---|---|
| 400 | `invalid_parameter` | Una fecha, un número o un valor que no es válido. El mensaje dice cuál. |
| 400 | `token_in_url` | La clave llegó en la dirección en lugar de en la cabecera. |
| 401 | `unauthorized` | Falta la clave o no es correcta. |
| 404 | `not_found` | Esa dirección no existe. |
| 405 | `method_not_allowed` | La API es de solo lectura: solo `GET`. |
| 500 | `internal_error` | Error inesperado. El detalle queda en el registro del servicio, no en la respuesta. |
| 503 | `no_logs` | No encuentra o no puede leer los registros de acceso. |
| 503 | `ranges_unavailable` | No pudo descargar los rangos de las redes y no tiene una copia anterior. |

## Ejemplos

**Python** (solo biblioteca estándar):

```python
import json, os, urllib.request

def n_antibot(path):
    req = urllib.request.Request(
        "http://127.0.0.1:8787" + path,
        headers={"Authorization": "Bearer " + os.environ["N_ANTIBOT_TOKEN"]},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

resumen = n_antibot("/v1/summary?since=2026-11-01")
google = resumen["ad_clicks"].get("google", {})
bots = google.get("network", 0) + google.get("agent", 0)
print(f"Google Ads: {bots} de {google.get('total', 0)} clics los hizo un bot")
```

**JavaScript** (Node 18 o un panel web con `--cors-origin`):

```js
const res = await fetch('http://127.0.0.1:8787/v1/ad-clicks?verdict=bot&limit=1000', {
  headers: { Authorization: `Bearer ${process.env.N_ANTIBOT_TOKEN}` },
});
if (!res.ok) throw new Error((await res.json()).error.message);
const { total, clicks } = await res.json();
console.log(total, clicks.map((c) => c.click_id));
```

**Alerta diaria** (avisa si hay bots que siguen recibiendo respuesta):

```bash
servidos=$(curl -s -H "Authorization: Bearer $N_ANTIBOT_TOKEN" \
  "http://127.0.0.1:8787/v1/bots?since=$(date -u +%F)" | python3 -c 'import json,sys; print(json.load(sys.stdin)["served"])')
[ "$servidos" -gt 0 ] && echo "N-antibot: $servidos peticiones de bots recibieron respuesta hoy"
```

## Dejarla en marcha

Con systemd:

```ini
# /etc/systemd/system/n-antibot-api.service
[Unit]
Description=N-antibot API
After=network-online.target

[Service]
ExecStart=/usr/local/bin/n-antibot serve -c /etc/n-antibot.toml --token-file /etc/n-antibot.token '/var/log/nginx/access.log*'
User=n-antibot
Group=adm
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --no-create-home n-antibot
openssl rand -hex 24 | sudo tee /etc/n-antibot.token >/dev/null
sudo chown n-antibot /etc/n-antibot.token && sudo chmod 600 /etc/n-antibot.token
sudo systemctl enable --now n-antibot-api
```

Este archivo de systemd es un ejemplo: no está cubierto por las pruebas. El usuario del servicio tiene que poder **leer** los registros (en Debian y Ubuntu, el grupo `adm`).

Para consultarla desde fuera, ponla detrás de tu servidor web con HTTPS, y no la abras directamente:

```caddyfile
panel.example.com {
	handle_path /n-antibot/* {
		reverse_proxy 127.0.0.1:8787
	}
}
```

## Seguridad

| Medida | Detalle |
|---|---|
| Solo lectura | Solo responde a `GET`. No hay ninguna dirección que cambie nada. |
| Local por defecto | Escucha en `127.0.0.1`. Fuera de ahí, exige clave. |
| Clave en la cabecera | Comparada en tiempo constante; nunca en la dirección. |
| Sin datos de más en los errores | Un fallo interno responde `500` genérico; el detalle va al registro del servicio. |
| Respuestas sin caché | `Cache-Control: no-store`: los proxies no guardan IP de visitantes. |
| Datos personales | La API devuelve direcciones IP. Protégela con clave y HTTPS, y da acceso solo a quien lo necesite. |

## Cómo se comporta

| Tema | Comportamiento |
|---|---|
| Datos al día | Cada consulta mira si los registros han cambiado (fecha y tamaño). Si no, responde de memoria. |
| Registros que rotan | Los comodines se resuelven en cada consulta: `access.log.1`, `access.log.2.gz`… entran solos. |
| Rangos de redes | Se descargan al arrancar y cada `--refresh-hours`. Si una descarga falla, sigue con los anteriores y reintenta a los diez minutos. |
| Horas | Todas en UTC, en formato ISO 8601. |
| Registros grandes | El primer cálculo lee todos los archivos; tarda en proporción a su tamaño. Usa `since` y registros rotados para acotar. |
| Versiones | Las direcciones llevan `/v1/`. Un cambio incompatible iría en `/v2/`. |

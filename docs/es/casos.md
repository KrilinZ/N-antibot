# Casos de uso

[← Documentación](README.md) · [🇬🇧 English](../en/cases.md)

Cada caso tiene su configuración lista en [`examples/cases/`](../../examples/cases/). Las pruebas cargan y generan
todas ellas, así que siempre son válidas. Cópiala, ajústala y genera con el formato de
[tu tecnología](README.md#por-tecnología):

```bash
n-antibot generate -c examples/cases/shop.toml -f caddy -o n-antibot.caddy
```

> [!TIP]
> Antes de instalar, pregunta a la configuración qué haría con una visita concreta:
> `n-antibot test-agent -c mi.toml "python-requests/2.32"` y `n-antibot test-ip -c mi.toml 43.173.132.9`.

## 🛒 Tienda online

**Problema:** bots que recorren todo el catálogo desde centros de datos y raspadores de precios. Consumen servidor
y ensucian las estadísticas, pero no compran.

**Cuidado con:** la pasarela de pago y tus integraciones llaman a tu web desde servidores, a menudo con librerías
HTTP. Si se cortan, los pedidos no se confirman.

[`shop.toml`](../../examples/cases/shop.toml)

```toml
[paths]
exclude = [
  "/.well-known/*",  # certificados
  "/api/*",          # tu API: webhooks de pago, panel, app móvil
  "/webhooks/*",     # otros proveedores que te llaman
  "/health",         # monitor de disponibilidad
]
```

| Comprueba después | Cómo |
|---|---|
| Un pedido de prueba llega a «pagado» | Haz una compra en modo de pruebas de tu pasarela |
| Google Merchant sigue leyendo tu feed | `curl -A 'Mozilla/5.0 (compatible; Googlebot/2.1)' https://tu-tienda/feed.xml` |
| El panel de administración abre | Entra con tu navegador |

## 📰 Blog, medio o web corporativa

**Problema:** rastreadores agresivos y raspadores de contenido.

**Cuidado con:** los lectores de RSS y los agregadores leen tus feeds con programas, no con navegadores. Deja los
feeds abiertos.

[`blog.toml`](../../examples/cases/blog.toml)

```toml
[paths]
exclude = ["/.well-known/*", "/feed", "/feed/*", "/rss.xml", "/atom.xml", "/robots.txt"]
```

## 🔌 Web con API pública

**Problema:** quieres frenar raspadores de la web, pero los programas de otras personas son tus clientes.

**Dos caminos:**

1. Si la API vive en una ruta propia, exclúyela (`exclude = ["/api/*"]`) y deja las listas por defecto.
2. Si la API y la web comparten rutas, quita la familia de librerías HTTP:

[`public-api.toml`](../../examples/cases/public-api.toml)

```toml
[robots]
presets = ["aggressive-crawlers", "vulnerability-scanners"]
```

## 📝 WordPress

**Problema:** el mismo que cualquier web, más escáneres que buscan plugins vulnerables.

**Cuidado con:** WordPress recibe llamadas legítimas de servidores: la API REST (aplicaciones, Jetpack, pasarelas
de pago), `wp-cron.php` y `admin-ajax.php`.

[`wordpress.toml`](../../examples/cases/wordpress.toml), con salida para Apache: ver la [guía de Apache](apache.md),
opción B si solo puedes tocar el `.htaccess`.

```toml
[paths]
exclude = [
  "/.well-known/*",
  "/wp-json/*",
  "/wp-cron.php",
  "/wp-admin/admin-ajax.php",
  "/xmlrpc.php",          # quita esta línea si no usas XML-RPC
  "/feed",
  "/feed/*",
]

[output]
format = "apache"
```

Si tu WordPress va detrás de nginx, usa la misma lista de rutas con `-f nginx`.

## 🌐 Detrás de un CDN o balanceador

**Problema:** a tu servidor le llega la IP del proxy, no la del visitante. La lista de robots funciona igual, pero
la de redes compararía la IP equivocada.

| Tu servidor | Qué configurar |
|---|---|
| Caddy | `ip_matcher = "client_ip"` en `[caddy]` y `trusted_proxies` en Caddy: [`behind-cdn.toml`](../../examples/cases/behind-cdn.toml) |
| nginx | Módulo `realip`: `set_real_ip_from` y `real_ip_header` |
| Apache | `mod_remoteip`: `RemoteIPHeader` y `RemoteIPTrustedProxy` |
| Cloudflare delante | Mejor aún: corta en Cloudflare con la [guía de Cloudflare](cloudflare.md) |
| Cortafuegos (nftables) | No sirve detrás de un proxy |

## 🔒 Protección máxima

**Problema:** te llegan bots de varias nubes y no te interesa aparecer en herramientas SEO de terceros.

**Cuidado con:** cuantas más redes cortes, más probable es dejar fuera a alguien legítimo. Mira antes tus registros
y deja pasar tus propios servidores con `allow`.

[`strict.toml`](../../examples/cases/strict.toml)

```toml
[networks]
presets = ["tencent-cloud", "alibaba-cloud", "huawei-cloud"]
allow = ["203.0.113.10/32"]     # tu servidor o tu monitor

[robots]
presets = ["aggressive-crawlers", "scraping-libraries", "vulnerability-scanners", "seo-tools"]
```

## 🤖 Sin robots de IA

**Problema:** no quieres que los rastreadores de IA lean tu contenido.

**Cuidado con:** tu web dejará de aparecer en las respuestas de ChatGPT, Claude y similares. Es una decisión de
negocio, no técnica.

[`no-ai.toml`](../../examples/cases/no-ai.toml)

```toml
[ai]
protect = false                 # las IA van protegidas por defecto: hay que quitarlo expresamente

[robots]
presets = ["aggressive-crawlers", "scraping-libraries", "vulnerability-scanners", "ai-training"]
block = ["PerplexityBot"]       # añade por nombre cualquier otro
```

## 🎯 Proteger las campañas de anuncios

**Problema:** bots que hacen clic en tus anuncios desde servidores en la nube. Gastan presupuesto y, además,
ensucian las visitas, las conversiones y los públicos de remarketing.

**Cuidado con:** cortar el clic no evita el cobro, y una persona real con una VPN alojada en esas nubes vería la
página cortada. El informe los cuenta siempre; cortarlos es opcional.

[`ad-campaigns.toml`](../../examples/cases/ad-campaigns.toml)

```toml
[ads]
cut = true
```

Después, saca el expediente para reclamar: `n-antibot report /var/log/nginx/access.log* --claim-dir reclamacion/`.
Ver el [informe de anuncios](informe-anuncios.md).

## 🧱 Cortar antes del servidor web

**Problema:** quieres que esas redes no lleguen a ningún servicio web de la máquina, tengas lo que tengas instalado
(incluidos contenedores Docker).

[`firewall.toml`](../../examples/cases/firewall.toml) y la [guía del cortafuegos](nftables.md). Solo corta redes:
para los robots, combínalo con la guía de tu servidor web.

## 🏢 Varias webs en un servidor

Un solo archivo generado vale para todas.

| Servidor | Cómo |
|---|---|
| Caddy | El mismo `import` en cada bloque, o el instalador una vez por web (`--site`) |
| nginx | El `include` una vez en `http { }` y la línea `if` en cada `server` |
| Apache | El mismo `Include` en cada `<VirtualHost>` |
| Cortafuegos | Protege todos los puertos web de la máquina de una vez |

Si cada web necesita rutas excluidas distintas, genera un archivo por web con su propia configuración. En Caddy,
dale a cada uno un `prefix` distinto; en nginx, un `prefix` distinto en `[nginx]`.

## 🎯 Me atacan desde otra red

**1. Encuentra las IP que más piden** en tu registro de accesos:

```bash
awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -20
```

**2. Mira a quién pertenecen** en [stat.ripe.net](https://stat.ripe.net/): busca la IP y apunta su ASN.

**3. Añádelo** y comprueba antes de instalar:

```toml
[networks]
presets = ["tencent-cloud"]
asns = ["AS45102"]
```

```bash
n-antibot test-ip -c mi.toml 47.74.1.1
```

Para un rango suelto, sin ASN: `block = ["203.0.113.0/24"]`.

> [!WARNING]
> No bloquees por ASN a proveedores de acceso doméstico o móvil (tu operadora, por ejemplo): son tus clientes.
> Esta herramienta está pensada para redes de **servidores**.

## 🆘 He bloqueado a quien no debía

| Síntoma | Solución |
|---|---|
| Un servicio tuyo o de un socio dejó de funcionar | Excluye la ruta que usa: `paths.exclude` |
| Un programa legítimo usa una librería bloqueada | `robots.allow = ["aiohttp"]`, o cámbiale el `User-Agent` |
| Un cliente o un monitor está en una red bloqueada | `networks.allow = ["203.0.113.10/32"]` |
| No sabes qué regla lo corta | `n-antibot test-agent -c mi.toml "su user-agent"` y `n-antibot test-ip -c mi.toml su.ip` |
| Hay que quitarlo ya | Ver «Quitarlo» en la guía de tu tecnología: es una línea |

Después de cambiar la configuración, vuelve a generar el archivo y a instalarlo.

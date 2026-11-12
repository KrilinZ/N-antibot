# Documentación de N-antibot

[← Volver al README](../../README.md) · [🇬🇧 English](../en/README.md)

## Por tecnología

Elige la guía de lo que tienes **delante de tu web** (lo primero que recibe la petición del visitante).

| Tecnología | Salida | Qué corta | Respuesta al bot | Estado de las pruebas |
|---|---|---|---|---|
| [Caddy](caddy.md) | `caddy` | redes y robots | conexión cerrada | ✅ de punta a punta con Caddy real |
| [nginx](nginx.md) | `nginx` | redes y robots | conexión cerrada (444) | ✅ de punta a punta con nginx real |
| [Apache](apache.md) (también `.htaccess`) | `apache` | redes y robots | 403 | ✅ de punta a punta con Apache 2.4 real |
| [Cortafuegos de Linux](nftables.md) (nftables) | `nftables` | solo redes | paquetes descartados | ✅ de punta a punta en Linux (integración continua) |
| [Node.js y Express](node-express.md) | `json` + middleware | redes y robots | conexión cerrada o 403 | ✅ con un servidor HTTP real de Node |
| [Next.js y Vercel](vercel-nextjs.md) | `json` + middleware | redes y robots | 403 | ⚠️ lógica probada; no probado en un despliegue de Vercel |
| [Cloudflare](cloudflare.md) | `cloudflare` | redes y robots | bloqueo de Cloudflare | ⚠️ expresión escrita según su documentación; no probada en una cuenta |

¿No sabes qué sirve tu web? Míralo en la cabecera `server`:

```bash
curl -sI https://example.com | grep -i -E '^(server|via|cf-ray|x-vercel-id)'
```

| Si ves… | Usa la guía de… |
|---|---|
| `server: Caddy` | [Caddy](caddy.md) |
| `server: nginx` | [nginx](nginx.md) |
| `server: Apache` | [Apache](apache.md) |
| `server: cloudflare` o `cf-ray` | [Cloudflare](cloudflare.md), o la de tu servidor con la IP real configurada |
| `server: Vercel` o `x-vercel-id` | [Next.js y Vercel](vercel-nextjs.md) |
| Otra cosa (LiteSpeed, IIS, un PaaS…) | [Node.js](node-express.md) si tu app es Node, o el [cortafuegos](nftables.md) si el servidor es tuyo |

## Por caso de uso

[Casos de uso](casos.md): configuraciones listas para copiar, cada una con su archivo en
[`examples/cases/`](../../examples/cases/).

| Caso | Archivo |
|---|---|
| [Tienda online](casos.md#-tienda-online) | [`shop.toml`](../../examples/cases/shop.toml) |
| [Blog, medio o web corporativa](casos.md#-blog-medio-o-web-corporativa) | [`blog.toml`](../../examples/cases/blog.toml) |
| [Web con API pública](casos.md#-web-con-api-pública) | [`public-api.toml`](../../examples/cases/public-api.toml) |
| [WordPress](casos.md#-wordpress) | [`wordpress.toml`](../../examples/cases/wordpress.toml) |
| [Detrás de un CDN o balanceador](casos.md#-detrás-de-un-cdn-o-balanceador) | [`behind-cdn.toml`](../../examples/cases/behind-cdn.toml) |
| [Protección máxima](casos.md#-protección-máxima) | [`strict.toml`](../../examples/cases/strict.toml) |
| [Sin robots de IA](casos.md#-sin-robots-de-ia) | [`no-ai.toml`](../../examples/cases/no-ai.toml) |
| [Cortar antes del servidor web](casos.md#-cortar-antes-del-servidor-web) | [`firewall.toml`](../../examples/cases/firewall.toml) |
| [Varias webs en un servidor](casos.md#-varias-webs-en-un-servidor) | |
| [Me atacan desde otra red](casos.md#-me-atacan-desde-otra-red) | |
| [He bloqueado a quien no debía](casos.md#-he-bloqueado-a-quien-no-debía) | |

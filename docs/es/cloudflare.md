# N-antibot en Cloudflare

[← Documentación](README.md) · [🇬🇧 English](../en/cloudflare.md)

> ⚠️ **Sin probar en una cuenta real.** La expresión se genera con los campos y funciones que documenta Cloudflare
> (`ip.src.asnum`, `ip.src`, `http.user_agent`, `http.request.uri.path`, `lower()`, `starts_with()`,
> `ends_with()`), y las pruebas comprueban su forma y que cabe en el límite de 4.096 caracteres. Antes de dejarla en
> «Block», pruébala unos días con la acción «Log» o «Managed Challenge».

## Cuándo usar esta guía

Tu web pasa por Cloudflare (proxy naranja activado). Cortar ahí es lo más eficaz: la petición no llega a tu
servidor.

## Pasos

**1. Genera la expresión.**

```bash
n-antibot generate -c n-antibot.toml -f cloudflare | tail -1
```

```text
(ip.src.asnum in {132203 45090} or lower(http.user_agent) contains "bytespider" or … ) and not starts_with(http.request.uri.path, "/.well-known/")
```

**2. Crea la regla.** En el panel de Cloudflare: tu dominio → **Security** → **WAF** → **Custom rules** (el nombre del menú puede variar según la versión del panel) →
**Create rule** → **Edit expression**. Pega la expresión.

**3. Elige la acción.** Empieza por **Log** (si tu plan lo permite) o **Managed Challenge**; cuando veas que solo
caen bots, pásala a **Block**.

**4. Despliega la regla.**

## Cómo se traduce tu configuración

| En `n-antibot.toml` | En la expresión |
|---|---|
| `networks.presets` y `networks.asns` | `ip.src.asnum in {132203 45090}`. Cloudflare conoce el ASN de cada visitante: **no hace falta descargar ni pegar rangos**. |
| `networks.block` | `ip.src in {203.0.113.0/24}` |
| `networks.allow` | `and not ip.src in {…}` |
| `robots` | `lower(http.user_agent) contains "bytespider"` (uno por robot) |
| `paths.exclude` `/api/*` | `and not starts_with(http.request.uri.path, "/api/")` |
| `paths.exclude` `/health` | `and not http.request.uri.path eq "/health"` |
| `paths.exclude` `*.xml` | `and not ends_with(http.request.uri.path, ".xml")` |

## Lo que conviene saber

- **No hay que mantener rangos.** Al ir por ASN, Cloudflare sigue los cambios de la red por ti. Solo hay que
  regenerar la expresión si cambias tu configuración.
- **Límite de tamaño.** Una expresión admite 4.096 caracteres. La configuración por defecto ocupa menos de 1.000.
  Si añades muchos robots o rangos y te pasas, reparte en dos reglas.
- **Bots verificados.** Cloudflare tiene su propio campo `cf.client.bot` para buscadores verificados. N-antibot no
  bloquea ninguno, así que no hace falta añadirlo.
- **Combinarlo con tu servidor.** Si además instalas N-antibot en Caddy o nginx detrás de Cloudflare, configura la
  IP real del visitante (ver sus guías).

## Quitarlo

Desactiva o borra la regla en **Security → WAF → Custom rules**.

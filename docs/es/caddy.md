# N-antibot en Caddy

[← Documentación](README.md) · [🇬🇧 English](../en/caddy.md)

> ✅ **Probado de punta a punta** con un Caddy real: navegadores, Google y curl reciben respuesta; los robots y las
> redes bloqueadas ven la conexión cerrada, también en rutas con su propio `handle`.

## Cuándo usar esta guía

Tu web la sirve Caddy 2, directamente o como proxy inverso de tu aplicación.

## Lo más corto

```bash
sudo n-antibot install caddy --site example.com --check-url https://example.com
```

Genera el archivo, hace copia, añade la línea a la configuración de tu web, valida, recarga y comprueba en vivo; si
algo falla, lo deja como estaba. Con `--dry-run` solo dice qué haría; con `--uninstall` lo quita. Probado de punta a
punta con un servidor real. Lo de abajo es lo mismo, paso a paso y a mano.

## Pasos

**1. Genera el archivo.**

```bash
n-antibot generate -c n-antibot.toml -o n-antibot.caddy
```

**2. Instálalo.** Con el instalador (copia, valida, recarga, comprueba y vuelve atrás si algo falla):

```bash
sudo ./install/caddy.sh --site example.com --snippet n-antibot.caddy --check-url https://example.com
```

O a mano: copia el archivo y añade el `import` como **primera línea** del bloque de tu web.

```caddyfile
example.com {
	import /etc/caddy/n-antibot.caddy

	handle /api/* {
		reverse_proxy 127.0.0.1:3000
	}
	handle {
		root * /var/www/example
		file_server
	}
}
```

```bash
sudo cp n-antibot.caddy /etc/caddy/n-antibot.caddy
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

## Casos particulares

| Situación | Qué hacer |
|---|---|
| **Detrás de Cloudflare o un balanceador** | `ip_matcher = "client_ip"` en `[caddy]` y `trusted_proxies` en las opciones globales de Caddy. Sin eso, Caddy compara la IP del proxy. |
| **Varias webs en el mismo Caddyfile** | Ejecuta el instalador una vez por web (`--site`), o añade el mismo `import` en cada bloque. |
| **Caddy en Docker** | Monta el archivo en el contenedor (`-v ./n-antibot.caddy:/etc/caddy/n-antibot.caddy`) y recarga con `docker exec <contenedor> caddy reload --config /etc/caddy/Caddyfile`. |
| **Bloque con varias direcciones** (`example.com, www.example.com {`) | `--site example.com` lo encuentra: basta con la primera dirección de la línea. |
| **Ya usas una ruta `/__n_antibot_blocked`** | Cambia `block_path` en `[caddy]`. |
| **Dos archivos en la misma web** (p. ej. reglas distintas) | Dales `prefix` distinto en `[caddy]` para que los matchers no choquen. |

## Por qué `rewrite` + `handle` y no un `handle @bots`

Caddy ordena los `handle` con matcher con nombre **detrás** de los `handle /ruta/*`. Un `handle @bots { abort }` no
llegaría a `/api/*` ni a `/product/*` si tienen su propio `handle`. El archivo generado usa un `rewrite` (que va
antes que cualquier `handle`) hacia una ruta privada y un `handle` de ruta exacta (que gana a los de prefijo) con
`abort`.

## Comprobar

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 000
```

## Quitarlo

```bash
sudo ./install/caddy.sh --site example.com --uninstall
```

A mano: borra la línea `import /etc/caddy/n-antibot.caddy` y recarga Caddy.

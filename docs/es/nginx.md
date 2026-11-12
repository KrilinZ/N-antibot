# N-antibot en nginx

[← Documentación](README.md) · [🇬🇧 English](../en/nginx.md)

> ✅ **Probado de punta a punta** con un nginx real: navegadores, Google y curl reciben respuesta; los robots y las
> redes bloqueadas ven la conexión cerrada; las rutas excluidas responden.

## Cuándo usar esta guía

Tu web la sirve nginx, directamente o como proxy inverso (Node, PHP-FPM, Python, Ruby…).

## Lo más corto

```bash
sudo n-antibot install nginx --site example.com --check-url https://example.com
```

Genera el archivo, hace copia, añade la línea a la configuración de tu web, valida, recarga y comprueba en vivo; si
algo falla, lo deja como estaba. Con `--dry-run` solo dice qué haría; con `--uninstall` lo quita. Probado de punta a
punta con un servidor real. Lo de abajo es lo mismo, paso a paso y a mano.

## Pasos

**1. Genera el archivo y cópialo.**

```bash
n-antibot generate -c n-antibot.toml -f nginx -o n-antibot.conf
sudo cp n-antibot.conf /etc/nginx/n-antibot.conf
```

**2. Inclúyelo una vez dentro de `http { }`.** En Debian y Ubuntu, lo más cómodo es dejarlo en `conf.d`, que ya se
incluye dentro de `http`:

```bash
sudo cp n-antibot.conf /etc/nginx/conf.d/n-antibot.conf
```

O añade la línea a mano en `/etc/nginx/nginx.conf`:

```nginx
http {
	include /etc/nginx/n-antibot.conf;
	# ...
}
```

**3. Añade una línea en cada `server` que quieras proteger.**

```nginx
server {
	server_name example.com;

	if ($n_antibot_block) { return 444; }

	location / {
		proxy_pass http://127.0.0.1:3000;
	}
}
```

**4. Valida y recarga.**

```bash
sudo nginx -t && sudo nginx -s reload
```

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `geo $n_antibot_net` | `1` si la IP del visitante está en una red bloqueada. nginx lo resuelve con un árbol: es rápido aunque haya cientos de rangos. |
| `map $http_user_agent $n_antibot_agent` | `1` si el `User-Agent` contiene un robot bloqueado (sin distinguir mayúsculas). |
| `map $uri $n_antibot_excluded` | `1` si la ruta está en `[paths] exclude`. |
| `map … $n_antibot_block` | `1` cuando hay red o robot y la ruta no está excluida. |
| `return 444` | Código propio de nginx: cierra la conexión sin enviar respuesta. |

## Casos particulares

| Situación | Qué hacer |
|---|---|
| **Detrás de Cloudflare, un CDN o un balanceador** | Configura el módulo `realip` (`set_real_ip_from <rangos del proxy>;` y `real_ip_header X-Forwarded-For;` o `CF-Connecting-IP`). Así `geo` ve la IP real. |
| **Prefieres responder 403** | Cambia `return 444;` por `return 403;`. |
| **Solo quieres registrar, sin cortar todavía** | Añade `$n_antibot_block` a tu `log_format` y no pongas el `if`. Verás en el registro qué se cortaría. |
| **Ya tienes variables con ese nombre** | Cambia `prefix` en `[nginx]`. |
| **nginx en Docker** | Monta el archivo en `/etc/nginx/conf.d/` y recarga con `docker exec <contenedor> nginx -s reload`. |
| **Proteger solo una parte** | Pon el `if` dentro del `location` que quieras, en lugar de en el `server`. |

## Comprobar

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 000
```

## Quitarlo

Borra la línea `if ($n_antibot_block) { return 444; }` y el `include` (o el archivo de `conf.d`), y recarga:

```bash
sudo nginx -t && sudo nginx -s reload
```

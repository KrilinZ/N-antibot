# N-antibot en Apache

[← Documentación](README.md) · [🇬🇧 English](../en/apache.md)

> ✅ **Probado de punta a punta** con un Apache 2.4 real, tanto incluido en un `<VirtualHost>` como pegado en un
> `.htaccess`: navegadores, Google y curl reciben `200`; los robots y las redes bloqueadas reciben `403`; las rutas
> excluidas responden.

## Cuándo usar esta guía

- Tu web la sirve Apache 2.4 y puedes editar su configuración, **o**
- estás en un alojamiento compartido y solo puedes tocar el `.htaccess` (WordPress, PrestaShop, Joomla…).

Hace falta `mod_rewrite`, que viene activado en casi todos los alojamientos.

> [!NOTE]
> Apache no puede cerrar una conexión desde su configuración, así que el bot recibe un **403 Forbidden** en lugar del
> corte seco de Caddy o nginx. Es una respuesta mínima, pero tu aplicación (PHP, base de datos) no llega a ejecutarse.

## Opción A: en la configuración del servidor

```bash
n-antibot generate -c n-antibot.toml -f apache -o n-antibot.conf
sudo cp n-antibot.conf /etc/apache2/n-antibot.conf
```

```apache
<VirtualHost *:443>
	ServerName example.com
	Include /etc/apache2/n-antibot.conf
	# ... el resto de tu configuración
</VirtualHost>
```

```bash
sudo a2enmod rewrite                       # Debian y Ubuntu, si no estaba activado
sudo apachectl configtest && sudo apachectl graceful
```

## Opción B: en el `.htaccess`

```bash
n-antibot generate -c n-antibot.toml -f apache -o n-antibot.htaccess
```

Pega el contenido **al principio** del `.htaccess` de la raíz de tu web, por encima de las reglas de tu gestor de
contenidos (el bloque `# BEGIN WordPress`, por ejemplo). No hace falta recargar nada.

## Cómo funciona

```apache
RewriteEngine On
RewriteCond %{REQUEST_URI} "!^/\.well\-known/"                # 1. la ruta no está excluida
RewriteCond %{HTTP_USER_AGENT} "(Bytespider|MJ12bot|…)" [NC,OR]  # 2. y es un robot…
RewriteCond expr "-R '1.12.0.0/14' || -R '1.116.0.0/15' || …" [OR]  #    …o viene de una red bloqueada
RewriteCond expr "-R '240d:c010:5c::/48' || -R '240d:c040::/43'"
RewriteRule ^ - [F,L]                                           # 3. entonces, 403
```

Las condiciones se unen con «y», salvo las marcadas `[OR]`, que se agrupan entre sí.

## Casos particulares

| Situación | Qué hacer |
|---|---|
| **Detrás de Cloudflare, un CDN o un balanceador** | Activa `mod_remoteip` (`RemoteIPHeader X-Forwarded-For` y `RemoteIPTrustedProxy <rangos del proxy>`). Así `-R` compara la IP real. |
| **WordPress** | Usa [`examples/cases/wordpress.toml`](../../examples/cases/wordpress.toml): excluye la API REST, `wp-cron.php` y `admin-ajax.php`. Ver [casos](casos.md#-wordpress). |
| **Error 500 tras pegarlo en `.htaccess`** | El alojamiento no permite `RewriteEngine` (`AllowOverride`) o usa Apache 2.2, que no entiende `expr`. Quita el bloque y pregunta a tu proveedor. |
| **LiteSpeed** | LiteSpeed lee `.htaccess`, pero su compatibilidad con `RewriteCond expr` no está probada aquí. |
| **Varias webs** | Añade el mismo `Include` en cada `<VirtualHost>`. |

## Comprobar

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://example.com/        # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://example.com/           # 403
```

## Quitarlo

Borra la línea `Include` y recarga (`sudo apachectl graceful`), o borra el bloque del `.htaccess`.

# N-antibot en Node.js y Express

[← Documentación](README.md) · [🇬🇧 English](../en/node-express.md)

> ✅ **Probado** con un servidor HTTP real de Node (`node --test`): corta la conexión o responde 403, respeta las
> rutas excluidas y compara rangos IPv4 e IPv6. El middleware usa la firma `(req, res, next)` de Express y Connect;
> con Express en sí no se ha ejecutado una prueba.

## Cuándo usar esta guía

- Tu aplicación Node recibe las peticiones directamente, sin Caddy ni nginx delante, **o**
- estás en una plataforma donde no puedes tocar el servidor web (un PaaS) pero sí tu código.

Si tienes Caddy, nginx o Apache delante, es mejor cortar ahí: la petición ni siquiera llega a Node.

## Pasos

**1. Genera los datos.**

```bash
n-antibot generate -c n-antibot.toml -f json -o n-antibot.json
```

**2. Copia [`integrations/node/n-antibot.mjs`](../../integrations/node/n-antibot.mjs) a tu proyecto.** Es un solo
archivo, sin dependencias.

**3. Úsalo como primer middleware.**

```js
import { readFileSync } from 'node:fs';
import express from 'express';
import { middleware } from './n-antibot.mjs';

const data = JSON.parse(readFileSync(new URL('./n-antibot.json', import.meta.url), 'utf8'));
const app = express();

app.use(middleware(data));          // antes de las rutas y de los archivos estáticos

app.get('/', (req, res) => res.send('ok'));
app.listen(3000);
```

Con el módulo `http` de Node, sin Express:

```js
import http from 'node:http';
const guard = middleware(data);
http.createServer((req, res) => guard(req, res, () => res.end('ok'))).listen(3000);
```

## Opciones del middleware

| Opción | Por defecto | Descripción |
|---|---|---|
| `action` | `'destroy'` | `'destroy'` cierra la conexión sin responder. `'forbidden'` responde `403` vacío. |
| `getIp` | `(req) => req.socket.remoteAddress` | De dónde sale la IP del visitante. |

> [!WARNING]
> Detrás de un proxy, `req.socket.remoteAddress` es la IP del proxy. Lee la cabecera que pone **tu** proxy:
> `middleware(data, { getIp: (req) => req.headers['x-real-ip'] })`. No te fíes de `X-Forwarded-For` si tu
> aplicación está expuesta directamente a Internet: cualquiera puede escribirla.

## Sin middleware

```js
import { createMatcher } from './n-antibot.mjs';

const matcher = createMatcher(data);
matcher.check({ ip: '43.173.132.9', userAgent: 'Mozilla/5.0', path: '/' });
// { blocked: true, reason: 'network', match: '43.173.0.0/16' }
matcher.check({ ip: '8.8.8.8', userAgent: 'python-requests/2.32', path: '/' });
// { blocked: true, reason: 'agent', match: 'python-requests' }
matcher.check({ ip: '8.8.8.8', userAgent: 'python-requests/2.32', path: '/api/hook' });
// { blocked: false, reason: null, match: null }   (ruta excluida)
```

Vale para Fastify, Koa, Hono o un Worker: llama a `check()` donde tengas la IP, el `User-Agent` y la ruta.

## Mantenerlo al día

Regenera `n-antibot.json` y reinicia la aplicación (o vuelve a desplegar). En tu integración continua,
`n-antibot check -f json -o n-antibot.json` avisa con código `1` cuando las listas han cambiado.

## Quitarlo

Borra la línea `app.use(middleware(data))`.

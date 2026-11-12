# N-antibot on Node.js and Express

[← Documentation](README.md) · [🇪🇸 Español](../es/node-express.md)

> ✅ **Tested** with a real Node HTTP server (`node --test`): it cuts the connection or answers 403, honours
> excluded paths and compares IPv4 and IPv6 ranges. The middleware uses the `(req, res, next)` signature of Express
> and Connect; no test has been run with Express itself.

## When to use this guide

- Your Node application receives requests directly, with no Caddy or nginx in front, **or**
- you are on a platform where you cannot touch the web server (a PaaS) but you can touch your code.

If you have Caddy, nginx or Apache in front, cutting there is better: the request never reaches Node.

## Steps

**1. Generate the data.**

```bash
n-antibot generate -c n-antibot.toml -f json -o n-antibot.json
```

**2. Copy [`integrations/node/n-antibot.mjs`](../../integrations/node/n-antibot.mjs) into your project.** It is a
single file with no dependencies.

**3. Use it as the first middleware.**

```js
import { readFileSync } from 'node:fs';
import express from 'express';
import { middleware } from './n-antibot.mjs';

const data = JSON.parse(readFileSync(new URL('./n-antibot.json', import.meta.url), 'utf8'));
const app = express();

app.use(middleware(data));          // before routes and static files

app.get('/', (req, res) => res.send('ok'));
app.listen(3000);
```

With Node's `http` module, without Express:

```js
import http from 'node:http';
const guard = middleware(data);
http.createServer((req, res) => guard(req, res, () => res.end('ok'))).listen(3000);
```

## Middleware options

| Option | Default | Description |
|---|---|---|
| `action` | `'destroy'` | `'destroy'` closes the connection without answering. `'forbidden'` answers an empty `403`. |
| `getIp` | `(req) => req.socket.remoteAddress` | Where the visitor's IP comes from. |

> [!WARNING]
> Behind a proxy, `req.socket.remoteAddress` is the proxy's IP. Read the header **your** proxy sets:
> `middleware(data, { getIp: (req) => req.headers['x-real-ip'] })`. Do not trust `X-Forwarded-For` if your
> application is exposed directly to the internet: anyone can write it.

## Without the middleware

```js
import { createMatcher } from './n-antibot.mjs';

const matcher = createMatcher(data);
matcher.check({ ip: '43.173.132.9', userAgent: 'Mozilla/5.0', path: '/' });
// { blocked: true, reason: 'network', match: '43.173.0.0/16' }
matcher.check({ ip: '8.8.8.8', userAgent: 'python-requests/2.32', path: '/' });
// { blocked: true, reason: 'agent', match: 'python-requests' }
matcher.check({ ip: '8.8.8.8', userAgent: 'python-requests/2.32', path: '/api/hook' });
// { blocked: false, reason: null, match: null }   (excluded path)
```

It works for Fastify, Koa, Hono or a Worker: call `check()` wherever you have the IP, the `User-Agent` and the path.

## Keeping it fresh

Regenerate `n-antibot.json` and restart the application (or redeploy). In CI,
`n-antibot check -f json -o n-antibot.json` exits with code `1` when the lists have changed.

## Remove it

Delete the `app.use(middleware(data))` line.

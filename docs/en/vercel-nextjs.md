# N-antibot on Next.js and Vercel

[← Documentation](README.md) · [🇪🇸 Español](../es/vercel-nextjs.md)

> ⚠️ **Partly tested.** The logic (`n-antibot.mjs`: ranges, robots, excluded paths) is tested with `node --test`.
> The example `middleware.ts` **has not been run on a real Vercel deployment**: try it on a preview branch before
> putting it in production.

## When to use this guide

Your site is a Next.js application, on Vercel or on your own server. On Vercel there is no Caddy or nginx you can
configure, so the cut happens in the Next.js middleware, which runs before every page.

## Steps

**1. Generate the data** and keep it at the project root.

```bash
n-antibot generate -c n-antibot.toml -f json -o n-antibot.json
```

**2. Copy to the project root** these two files from [`integrations/node/`](../../integrations/node/):

| File | Destination |
|---|---|
| `n-antibot.mjs` | `./n-antibot.mjs` |
| `next-middleware.ts` | `./middleware.ts` (or `./src/middleware.ts` if you use `src/`) |

**3. Review `middleware.ts`.**

```ts
import type { NextRequest } from 'next/server';
import data from './n-antibot.json';
import { createMatcher } from './n-antibot.mjs';

const matcher = createMatcher(data);

export function middleware(request: NextRequest) {
  const ip = request.headers.get('x-real-ip') ?? request.headers.get('x-forwarded-for')?.split(',')[0];
  const verdict = matcher.check({
    ip,
    userAgent: request.headers.get('user-agent'),
    path: request.nextUrl.pathname,
  });
  if (verdict.blocked) return new Response(null, { status: 403 });
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };
```

**4. Deploy to a preview branch and check** with the `curl` commands below.

## Good to know

| Topic | Detail |
|---|---|
| **Answer** | The edge runtime cannot close a connection: the bot gets an empty `403`. |
| **Visitor IP** | The example reads `x-real-ip` and, failing that, the first value of `x-forwarded-for`. On your own server, use the header your proxy sets. |
| **If you already have a `middleware.ts`** | Next.js allows only one: copy the check to the top of yours and return the `403` before your own logic. |
| **Excluded paths** | They come from `[paths] exclude`. Exclude `/api/*` if other servers call your API routes. |
| **Cost** | The middleware runs on every request matching `config.matcher`. The example leaves out Next.js static files. |
| **Size** | With the default configuration, `n-antibot.json` is a few KB. |

## Check

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://your-branch.vercel.app/     # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://your-branch.vercel.app/        # 403
```

## Remove it

Delete `middleware.ts` (or the check, if you added it to an existing one) and redeploy.

# N-antibot en Next.js y Vercel

[← Documentación](README.md) · [🇬🇧 English](../en/vercel-nextjs.md)

> ⚠️ **Probado a medias.** La lógica (`n-antibot.mjs`: rangos, robots, rutas excluidas) está probada con
> `node --test`. El archivo `middleware.ts` de ejemplo **no se ha ejecutado en un despliegue real de Vercel**:
> pruébalo en una rama de vista previa antes de ponerlo en producción.

## Cuándo usar esta guía

Tu web es una aplicación Next.js, en Vercel o en tu propio servidor. En Vercel no hay Caddy ni nginx que puedas
configurar, así que el corte se hace en el middleware de Next.js, que se ejecuta antes de cada página.

## Pasos

**1. Genera los datos** y guárdalos en la raíz del proyecto.

```bash
n-antibot generate -c n-antibot.toml -f json -o n-antibot.json
```

**2. Copia a la raíz del proyecto** estos dos archivos de [`integrations/node/`](../../integrations/node/):

| Archivo | Destino |
|---|---|
| `n-antibot.mjs` | `./n-antibot.mjs` |
| `next-middleware.ts` | `./middleware.ts` (o `./src/middleware.ts` si usas `src/`) |

**3. Revisa `middleware.ts`.**

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

**4. Despliega en una rama de vista previa y comprueba** con los `curl` del final.

## Lo que conviene saber

| Tema | Detalle |
|---|---|
| **Respuesta** | El entorno «edge» no puede cerrar una conexión: el bot recibe un `403` vacío. |
| **IP del visitante** | El ejemplo lee `x-real-ip` y, si no está, el primer valor de `x-forwarded-for`. En tu propio servidor, usa la cabecera que ponga tu proxy. |
| **Si ya tienes un `middleware.ts`** | Next.js solo admite uno: copia la comprobación al principio del tuyo y devuelve el `403` antes de tu lógica. |
| **Rutas excluidas** | Salen de `[paths] exclude`. Excluye `/api/*` si otros servidores llaman a tus rutas de API. |
| **Coste** | El middleware se ejecuta en cada petición que cumpla `config.matcher`. El ejemplo deja fuera los estáticos de Next.js. |
| **Tamaño** | Con la configuración por defecto, `n-antibot.json` pesa unos pocos KB. |

## Comprobar

```bash
curl -s -o /dev/null -w '%{http_code}\n' -A 'Mozilla/5.0 Chrome/131.0' https://tu-rama.vercel.app/       # 200
curl -s -o /dev/null -w '%{http_code}\n' -A 'python-requests/2.32.3' https://tu-rama.vercel.app/          # 403
```

## Quitarlo

Borra `middleware.ts` (o la comprobación, si lo añadiste a uno existente) y vuelve a desplegar.

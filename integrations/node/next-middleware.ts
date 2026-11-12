// Next.js middleware (Vercel and self-hosted). Save it as middleware.ts at the root of your project, next to
// n-antibot.mjs and n-antibot.json (n-antibot generate -f json -o n-antibot.json).
// The edge runtime cannot drop a connection, so blocked requests get an empty 403.
import type { NextRequest } from 'next/server';
import data from './n-antibot.json';
import { createMatcher } from './n-antibot.mjs';

const matcher = createMatcher(data);

export function middleware(request: NextRequest) {
  // Vercel sets x-real-ip to the visitor's address. Self-hosted: use the header your proxy sets.
  const ip = request.headers.get('x-real-ip') ?? request.headers.get('x-forwarded-for')?.split(',')[0];
  const verdict = matcher.check({
    ip,
    userAgent: request.headers.get('user-agent'),
    path: request.nextUrl.pathname,
  });
  if (verdict.blocked) return new Response(null, { status: 403 });
}

// Skip Next.js internals and static files: they are not worth a check.
export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };

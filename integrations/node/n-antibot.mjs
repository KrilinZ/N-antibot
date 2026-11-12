// N-antibot for Node.js, Express and edge runtimes (Next.js middleware on Vercel, Cloudflare Workers).
// No dependencies and no Node-only APIs: it only needs the data made by `n-antibot generate -f json`.
//
//   import data from './n-antibot.json' with { type: 'json' };
//   import { createMatcher, middleware } from './n-antibot.mjs';
//   app.use(middleware(data));                       // Express / Connect / plain http
//   createMatcher(data).check({ ip, userAgent, path }) // anywhere else -> { blocked, reason }

const V4 = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;

function parseV4(text) {
  const m = V4.exec(text);
  if (!m) return null;
  let n = 0;
  for (let i = 1; i <= 4; i++) {
    const part = Number(m[i]);
    if (part > 255) return null;
    n = n * 256 + part;
  }
  return n;
}

function parseV6(text) {
  let s = text.replace(/%.*$/, '');
  const tail = s.slice(s.lastIndexOf(':') + 1);
  if (tail.includes('.')) {
    const v4 = parseV4(tail);
    if (v4 === null) return null;
    s = s.slice(0, s.lastIndexOf(':') + 1) + (v4 >>> 16).toString(16) + ':' + (v4 & 0xffff).toString(16);
  }
  const halves = s.split('::');
  if (halves.length > 2) return null;
  const head = halves[0] ? halves[0].split(':') : [];
  const rest = halves.length === 2 && halves[1] ? halves[1].split(':') : [];
  const missing = 8 - head.length - rest.length;
  if (halves.length === 1 ? missing !== 0 : missing < 1) return null;
  const groups = [...head, ...Array(halves.length === 2 ? missing : 0).fill('0'), ...rest];
  let n = 0n;
  for (const g of groups) {
    if (!/^[0-9a-fA-F]{1,4}$/.test(g)) return null;
    n = (n << 16n) | BigInt(parseInt(g, 16));
  }
  return n;
}

/** Parse an address. IPv4-mapped IPv6 (::ffff:1.2.3.4) is treated as IPv4. Returns null if it is not an IP. */
export function parseIp(text) {
  if (typeof text !== 'string') return null;
  const t = text.trim();
  const v4 = parseV4(t);
  if (v4 !== null) return { version: 4, value: v4 };
  if (!t.includes(':')) return null;
  const v6 = parseV6(t);
  if (v6 === null) return null;
  if (v6 >> 32n === 0xffffn) return { version: 4, value: Number(v6 & 0xffffffffn) };
  return { version: 6, value: v6 };
}

function range(cidr) {
  const [addr, len] = cidr.split('/');
  const ip = parseIp(addr);
  const bits = Number(len);
  if (!ip || !Number.isInteger(bits)) throw new Error(`n-antibot: invalid range ${cidr}`);
  if (ip.version === 4) {
    const size = 2 ** (32 - bits);
    const start = Math.floor(ip.value / size) * size;
    return { version: 4, start, end: start + size - 1 };
  }
  const size = 1n << BigInt(128 - bits);
  const start = (ip.value / size) * size;
  return { version: 6, start, end: start + size - 1n };
}

function pathMatcher(pattern) {
  if (pattern.startsWith('*.')) return (p) => p.endsWith(pattern.slice(1));
  if (pattern.endsWith('*')) return (p) => p.startsWith(pattern.slice(0, -1));
  return (p) => p === pattern;
}

/**
 * Build a matcher from the JSON made by `n-antibot generate -f json`.
 * check({ ip, userAgent, path }) -> { blocked: boolean, reason: 'network' | 'agent' | null, match: string | null }
 */
export function createMatcher(data) {
  if (!data || !Array.isArray(data.ipv4) || !Array.isArray(data.ipv6) || !Array.isArray(data.user_agents)) {
    throw new Error('n-antibot: expected the JSON made by `n-antibot generate -f json`');
  }
  const sorted = (list) => list.map((c) => ({ cidr: c, ...range(c) })).sort((a, b) => (a.start < b.start ? -1 : 1));
  const v4 = sorted(data.ipv4);
  const v6 = sorted(data.ipv6);
  const agents = data.user_agents.map((a) => a.toLowerCase());
  const excluded = (data.exclude_paths || []).map(pathMatcher);

  function findRange(ip) {
    const list = ip.version === 4 ? v4 : v6;
    let lo = 0;
    let hi = list.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (ip.value < list[mid].start) hi = mid - 1;
      else if (ip.value > list[mid].end) lo = mid + 1;
      else return list[mid].cidr;
    }
    return null;
  }

  function check({ ip, userAgent, path } = {}) {
    const pathname = String(path || '/').split('?')[0];
    if (excluded.some((m) => m(pathname))) return { blocked: false, reason: null, match: null };
    const ua = String(userAgent || '').toLowerCase();
    const agent = agents.find((a) => ua.includes(a));
    if (agent) return { blocked: true, reason: 'agent', match: agent };
    const parsed = parseIp(ip);
    const net = parsed && findRange(parsed);
    if (net) return { blocked: true, reason: 'network', match: net };
    return { blocked: false, reason: null, match: null };
  }

  return { check };
}

/**
 * Middleware for Express, Connect or a plain http server: (req, res, next).
 * options.action: 'destroy' (default: close the connection without answering) or 'forbidden' (answer 403).
 * options.getIp: (req) => string. Default: the socket address. Behind a proxy, read the header YOUR proxy sets
 * (never trust X-Forwarded-For from the open internet).
 */
export function middleware(data, options = {}) {
  const matcher = createMatcher(data);
  const getIp = options.getIp || ((req) => req.socket?.remoteAddress);
  const action = options.action || 'destroy';
  return function nAntibot(req, res, next) {
    const verdict = matcher.check({ ip: getIp(req), userAgent: req.headers['user-agent'], path: req.url });
    if (!verdict.blocked) return next();
    if (action === 'forbidden') {
      res.statusCode = 403;
      return res.end();
    }
    return req.socket.destroy();
  };
}

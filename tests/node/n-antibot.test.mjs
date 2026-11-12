import assert from 'node:assert/strict';
import http from 'node:http';
import { test } from 'node:test';
import { createMatcher, middleware, parseIp } from '../../integrations/node/n-antibot.mjs';

const data = {
  ipv4: ['43.172.0.0/17', '43.173.0.0/16', '1.12.0.0/14'],
  ipv6: ['2402:4e00::/32', '240d:c040::/43'],
  user_agents: ['Bytespider', 'python-requests'],
  exclude_paths: ['/.well-known/*', '/api/*', '/health', '*.xml'],
};
const CHROME = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36';

test('parseIp', () => {
  assert.deepEqual(parseIp('1.2.3.4'), { version: 4, value: 16909060 });
  assert.deepEqual(parseIp('::ffff:1.2.3.4'), { version: 4, value: 16909060 });
  assert.deepEqual(parseIp('::1'), { version: 6, value: 1n });
  assert.equal(parseIp('2402:4e00::1').version, 6);
  for (const bad of ['', 'nope', '1.2.3', '256.1.1.1', '1::2::3', 'gggg::1', undefined, null, 5]) {
    assert.equal(parseIp(bad), null, String(bad));
  }
});

test('networks', () => {
  const m = createMatcher(data);
  const hit = (ip) => m.check({ ip, userAgent: CHROME, path: '/' });
  assert.deepEqual(hit('43.173.132.9'), { blocked: true, reason: 'network', match: '43.173.0.0/16' });
  assert.equal(hit('43.172.127.255').blocked, true);
  assert.equal(hit('43.172.128.0').blocked, false);
  assert.equal(hit('1.15.255.255').blocked, true);
  assert.equal(hit('1.16.0.0').blocked, false);
  assert.equal(hit('::ffff:43.173.1.1').blocked, true);
  assert.equal(hit('2402:4e00:1234::1').blocked, true);
  assert.equal(hit('2402:4e01::1').blocked, false);
  assert.equal(hit('240d:c040:1f:ffff::1').blocked, true);
  assert.equal(hit('240d:c040:20::1').blocked, false);
  assert.equal(hit('66.249.66.1').blocked, false);
  assert.equal(hit('not an ip').blocked, false);
  assert.equal(hit(undefined).blocked, false);
});

test('agents and excluded paths', () => {
  const m = createMatcher(data);
  const ua = (userAgent, path = '/') => m.check({ ip: '8.8.8.8', userAgent, path }).blocked;
  assert.equal(ua('Mozilla/5.0 (compatible; bytespider; x)'), true);
  assert.equal(ua('python-requests/2.32'), true);
  assert.equal(ua(CHROME), false);
  assert.equal(ua('Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'), false);
  assert.equal(ua(undefined), false);
  assert.equal(ua('python-requests/2.32', '/api/hook?x=1'), false);
  assert.equal(ua('python-requests/2.32', '/.well-known/acme-challenge/a'), false);
  assert.equal(ua('python-requests/2.32', '/health'), false);
  assert.equal(ua('python-requests/2.32', '/healthy'), true);
  assert.equal(ua('python-requests/2.32', '/sitemap.xml'), false);
  assert.equal(m.check({ ip: '43.173.1.1', userAgent: CHROME, path: '/api/x' }).blocked, false);
});

test('rejects data that is not n-antibot JSON', () => {
  assert.throws(() => createMatcher({}), /n-antibot generate -f json/);
  assert.throws(() => createMatcher({ ipv4: ['x/8'], ipv6: [], user_agents: [] }), /invalid range/);
});

async function request(port, path, userAgent) {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path, headers: { 'user-agent': userAgent } }, (res) => {
      res.resume();
      res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', () => resolve('closed'));
  });
}

async function serve(options, fn) {
  const guard = middleware(options.data || data, options);
  const server = http.createServer((req, res) => guard(req, res, () => res.end('ok')));
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  try {
    await fn(server.address().port);
  } finally {
    server.close();
  }
}

test('middleware on a real http server: cuts the connection', async () => {
  await serve({}, async (port) => {
    assert.equal(await request(port, '/', CHROME), 200);
    assert.equal(await request(port, '/', 'Bytespider'), 'closed');
    assert.equal(await request(port, '/api/hook', 'Bytespider'), 200);
  });
});

test('middleware: 403 mode and blocked network (loopback)', async () => {
  const loop = { ...data, ipv4: ['127.0.0.0/8'], ipv6: ['::1/128'] };
  await serve({ data: loop, action: 'forbidden' }, async (port) => {
    assert.equal(await request(port, '/', CHROME), 403);
    assert.equal(await request(port, '/health', CHROME), 200);
  });
  await serve({ data: loop, getIp: () => '8.8.8.8' }, async (port) => {
    assert.equal(await request(port, '/', CHROME), 200);
  });
});

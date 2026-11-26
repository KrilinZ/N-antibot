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

test('paid ad clicks from data centers, only when the data asks for it', () => {
  const withAds = {
    ...data,
    ad_clicks: { cut: true, params: ['gclid', 'msclkid'], ipv4: ['3.0.0.0/9'], ipv6: ['2600:1f00::/24'] },
  };
  const m = createMatcher(withAds);
  const hit = (ip, path) => m.check({ ip, userAgent: CHROME, path });
  assert.deepEqual(hit('3.5.5.5', '/?gclid=abc'), { blocked: true, reason: 'ad-click', match: '3.0.0.0/9' });
  assert.equal(hit('2600:1f00::1', '/p/?x=1&msclkid=abc').blocked, true);
  assert.equal(hit('3.5.5.5', '/').blocked, false); // that cloud is not blocked for normal browsing
  assert.equal(hit('3.5.5.5', '/?notgclid=abc').blocked, false);
  assert.equal(hit('3.5.5.5', '/?gclid=').blocked, false);
  assert.equal(hit('3.5.5.5', '/api/hook?gclid=abc').blocked, false); // excluded path
  assert.equal(hit('81.40.1.1', '/?gclid=abc').blocked, false); // a real visitor's ad click
  assert.equal(createMatcher(data).check({ ip: '3.5.5.5', userAgent: CHROME, path: '/?gclid=abc' }).blocked, false);
  const off = createMatcher({ ...withAds, ad_clicks: { ...withAds.ad_clicks, cut: false } });
  assert.equal(off.check({ ip: '3.5.5.5', userAgent: CHROME, path: '/?gclid=abc' }).blocked, false);
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

// Bots posing as a browser: tests/node/stealth.json is made by `n-antibot generate -f json` with every [stealth]
// preset, future_chrome and two referer-spam domains (tests/test_stealth.py keeps it current).
import { readFileSync } from 'node:fs';

const stealthData = JSON.parse(readFileSync(new URL('./stealth.json', import.meta.url)));
const IMPOSTOR = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36';
const IMPOSTOR_HEADERS = { accept: 'text/html', 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8', 'accept-encoding': 'gzip', connection: 'close' };
const REAL = IMPOSTOR.replace('Chrome/144', 'Chrome/159');
const REAL_HEADERS = {
  'accept-language': 'es-ES,es;q=0.9',
  'sec-ch-ua': '"Chromium";v="159", "Google Chrome";v="159"',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-dest': 'document',
};

test('fingerprints: the impostor is cut, browsers, search engines and AI crawlers are not', () => {
  const m = createMatcher(stealthData);
  const run = (userAgent, headers, protocol = 'HTTP/1.1', ip = '203.0.113.7', https = true, path = '/brand/x') =>
    m.check({ ip, userAgent, path, headers, protocol, https });
  assert.deepEqual(run(IMPOSTOR, IMPOSTOR_HEADERS), {
    blocked: true,
    reason: 'fingerprint',
    match: 'chrome-http1-without-fetch-metadata',
  });
  assert.equal(run(IMPOSTOR, IMPOSTOR_HEADERS, '2.0').match, 'chrome-without-fetch-metadata');
  assert.equal(run(IMPOSTOR, IMPOSTOR_HEADERS, '1.1', '203.0.113.7', false).blocked, false); // plain HTTP
  assert.equal(run(IMPOSTOR, IMPOSTOR_HEADERS, '1.1', '66.249.64.5').blocked, false); // published crawler address
  assert.equal(run(IMPOSTOR, IMPOSTOR_HEADERS, '1.1', '203.0.113.7', true, '/api/x').blocked, false);
  assert.equal(run(IMPOSTOR, { ...IMPOSTOR_HEADERS, 'signature-agent': '"https://chatgpt.com"' }).blocked, false);
  for (const proto of ['1.1', '2.0', 'HTTP/3']) assert.equal(run(REAL, REAL_HEADERS, proto).blocked, false, proto);
  assert.equal(run(REAL.replace('Chrome/159', 'Chrome/163'), REAL_HEADERS, '2.0').match, 'future-chrome');
  // Chrome on Android with Firefox's Accept-Language and no client hints; a real Firefox with it passes.
  const android = 'Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Mobile Safari/537.36';
  const firefoxLang = { 'accept-language': 'en-US,en;q=0.5', 'sec-fetch-mode': 'navigate' };
  assert.equal(run(android, firefoxLang, '2.0').match, 'chrome-language-not-from-chrome');
  assert.equal(run(android, { ...firefoxLang, 'sec-ch-ua': '"Chromium";v="144"' }, '2.0').blocked, false);
  assert.equal(run('Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0', firefoxLang, '2.0').blocked, false);
  // A kit's fixed language ([stealth] languages) without Sec-Fetch-Mode.
  assert.equal(run(REAL, { 'accept-language': 'zh-TW,zh;q=0.9', 'sec-ch-ua': '"Chromium";v="159"' }, '2.0').match, 'fixed-language');
  // HeadlessChrome declares itself (a site's own Playwright checks).
  assert.equal(run('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/156.0.8078.4 Safari/537.36', { 'accept-language': 'fr' }).blocked, false);
  const spam = { ...REAL_HEADERS, referer: 'https://www.google.com/url?q=http://m.baidu.com/' };
  assert.equal(run(REAL, spam, '2.0').match, 'referer-spam');
  for (const ua of [
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/159.0.0.0 Safari/537.36',
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GoogleOther) Chrome/159.0.0.0 Safari/537.36',
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/159.0.0.0 Safari/537.36',
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot',
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot',
    'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot',
  ]) {
    assert.equal(run(ua, IMPOSTOR_HEADERS).blocked, false, ua);
  }
});

test('fingerprints: the middleware reads protocol, TLS and headers from the request', async () => {
  const get = (port, headers) =>
    new Promise((resolve) => {
      const req = http.get({ host: '127.0.0.1', port, path: '/', headers }, (res) => {
        res.resume();
        res.on('end', () => resolve(res.statusCode));
      });
      req.on('error', () => resolve('closed'));
    });
  await serve({ data: stealthData, https: true }, async (port) => {
    assert.equal(await get(port, { 'user-agent': IMPOSTOR, ...IMPOSTOR_HEADERS }), 'closed');
    assert.equal(await get(port, { 'user-agent': REAL, ...REAL_HEADERS }), 200);
  });
});

// Express example. Generate the data first: n-antibot generate -f json -o n-antibot.json
import { readFileSync } from 'node:fs';
import express from 'express';
import { middleware } from './n-antibot.mjs';

const data = JSON.parse(readFileSync(new URL('./n-antibot.json', import.meta.url), 'utf8'));
const app = express();

// First middleware of the app, before routes and static files.
app.use(middleware(data));

// Behind your own reverse proxy, read the header it sets:
// app.use(middleware(data, { getIp: (req) => req.headers['x-real-ip'] }));

app.get('/', (req, res) => res.send('ok'));
app.listen(3000);

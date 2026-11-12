# Contributing to N-antibot

Thank you for helping. Proposals are welcome in English or Spanish.

## Set up

```bash
git clone https://github.com/KrilinZ/N-antibot.git && cd N-antibot
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest ruff
pytest -q
node --test tests/node/n-antibot.test.mjs
ruff check src tests && ruff format --check src tests
```

The end-to-end tests start real Caddy, nginx and Apache servers when they are installed, and skip themselves when
they are not. The nftables tests need Linux and passwordless `sudo`.

## What makes a good proposal

| You want to add… | Please include |
|---|---|
| A robot (User-Agent) | Its documentation page or a log excerpt showing the behaviour. It must not match any browser or search engine: `PROTECTED_AGENTS` in `presets.py` is checked by the tests. |
| A network (ASN) | The ASN and its holder as shown on [stat.ripe.net](https://stat.ripe.net/), and why real visitors do not come from it. |
| An output for another server | A renderer in `render.py`, unit tests for its shape and an end-to-end test with the real server. |
| An ad platform's claim route | The platform's own page that states where to claim, the deadline and what it asks for. Only what that page says goes into `claims.py`, with the date it was read. |

## Rules of the house

- **Nothing unverified.** Documentation says what was tested and what was not. If you could not test something,
  say so in the guide.
- **Never break a site.** A change that could cut off a browser, a search engine or `curl` needs a test proving it
  does not.
- **No dependencies** for the core package (only `tomli` on Python 3.9 and 3.10).
- **Plain ASCII** in generated files and command output.
- Keep examples neutral: `example.com`, documentation IP ranges (`192.0.2.0/24`, `203.0.113.0/24`).

#!/usr/bin/env bash
# Weekly refresh for Caddy: regenerate, validate, reload. Keeps the old file if anything fails.
#   0 4 * * 1  root  /usr/local/bin/n-antibot-update.sh
set -euo pipefail
dest=/etc/caddy/n-antibot.caddy
config=/etc/n-antibot.toml
n-antibot check -c "$config" -o "$dest" && exit 0
cp -p "$dest" "$dest.previous"
n-antibot generate -c "$config" -o "$dest"
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
else
  cp -p "$dest.previous" "$dest"
  echo "n-antibot: new lists did not validate, kept the previous ones" >&2
  exit 1
fi

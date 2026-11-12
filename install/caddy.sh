#!/usr/bin/env bash
# N-antibot installer for Caddy: safe by design.
#
#   sudo ./install/caddy.sh --site example.com --snippet ./n-antibot.caddy [--check-url https://example.com]
#   sudo ./install/caddy.sh --site example.com --uninstall
#
# What it does, in order (any failure puts everything back as it was):
#   1. Backs up the Caddyfile (and the previous snippet) to a dated folder.
#   2. Copies the snippet to /etc/caddy/n-antibot.caddy.
#   3. Adds "import /etc/caddy/n-antibot.caddy" as the first line of the site block (only once).
#   4. caddy validate  ->  caddy reload.
#   5. With --check-url: a real browser and Googlebot must get an answer, Bytespider must be cut off.
#
# Options:
#   --site ADDRESS       site block to protect, exactly as it starts a line in the Caddyfile ("example.com {")
#   --snippet FILE       file made by `n-antibot generate` (not needed with --uninstall)
#   --caddyfile FILE     default /etc/caddy/Caddyfile
#   --dest FILE          default /etc/caddy/n-antibot.caddy
#   --backup-dir DIR     default /var/backups/n-antibot
#   --address HOST:PORT  Caddy admin endpoint for reload (default: Caddy's own default)
#   --check-url URL      live checks after reload (rolls back if they fail)
#   --uninstall          remove the import line and reload
set -euo pipefail

caddyfile=/etc/caddy/Caddyfile
dest=/etc/caddy/n-antibot.caddy
backups=/var/backups/n-antibot
site="" snippet="" check_url="" address="" uninstall=0

while [ $# -gt 0 ]; do
  case "$1" in
    --site) site=$2; shift 2 ;;
    --snippet) snippet=$2; shift 2 ;;
    --caddyfile) caddyfile=$2; shift 2 ;;
    --dest) dest=$2; shift 2 ;;
    --backup-dir) backups=$2; shift 2 ;;
    --address) address=$2; shift 2 ;;
    --check-url) check_url=${2%/}; shift 2 ;;
    --uninstall) uninstall=1; shift ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "n-antibot: unknown option $1" >&2; exit 2 ;;
  esac
done

say() { echo "n-antibot: $*"; }
die() { echo "n-antibot: $*" >&2; exit 1; }

command -v caddy >/dev/null || die "caddy is not installed"
[ -n "$site" ] || die "--site is required"
[ -f "$caddyfile" ] || die "no Caddyfile at $caddyfile"
site_re=$(printf '%s' "$site" | sed 's/[.[\*^$/]/\\&/g')
grep -Eq "^${site_re}([ ,][^{]*)? *\{" "$caddyfile" || die "no line starting with \"$site ... {\" in $caddyfile"
if [ "$uninstall" = 0 ]; then
  [ -s "$snippet" ] || die "--snippet FILE is required (make it with: n-antibot generate -o FILE)"
fi

reload_args=(--config "$caddyfile" --adapter caddyfile)
[ -n "$address" ] && reload_args+=(--address "$address")

stamp=$(date +%Y%m%d-%H%M%S)
bk="$backups/$stamp"
mkdir -p "$bk"
cp -p "$caddyfile" "$bk/Caddyfile"
[ -f "$dest" ] && cp -p "$dest" "$bk/n-antibot.caddy.before"
say "backup in $bk"

restore() {
  cp -p "$bk/Caddyfile" "$caddyfile"
  if [ -f "$bk/n-antibot.caddy.before" ]; then cp -p "$bk/n-antibot.caddy.before" "$dest"; else rm -f "$dest"; fi
  caddy reload "${reload_args[@]}" >/dev/null 2>&1 || true
  say "restored the previous configuration"
}

new="$caddyfile.n-antibot.new"
trap 'rm -f "$new"' EXIT

if [ "$uninstall" = 1 ]; then
  grep -v -e "import $dest\$" -e '# n-antibot:' "$caddyfile" > "$new" || true
else
  install -m 644 "$snippet" "$dest"
  if grep -q "import $dest\$" "$caddyfile"; then
    say "the site already imports $dest: only the lists are updated"
    cp "$caddyfile" "$new"
  else
    N_RE="^${site_re}([ ,][^{]*)? *[{]" N_DEST="$dest" awk '
      BEGIN { re = ENVIRON["N_RE"]; dest = ENVIRON["N_DEST"] }
      $0 ~ re && !done {
        print
        print "\t# n-antibot: blocks bot networks and scrapers. To remove it, delete the next line and reload."
        print "\timport " dest
        done = 1; next
      }
      { print }
      END { if (!done) exit 3 }' "$caddyfile" > "$new" || { restore; die "could not insert the import"; }
  fi
fi

diff -u "$caddyfile" "$new" || true
if ! caddy validate --config "$new" --adapter caddyfile >"$bk/validate.log" 2>&1; then
  tail -5 "$bk/validate.log" >&2
  restore
  die "caddy validate failed: nothing changed"
fi
cp "$new" "$caddyfile"
if ! caddy reload "${reload_args[@]}"; then
  restore
  die "caddy reload failed: previous configuration restored"
fi
say "Caddy reloaded"

if [ "$uninstall" = 1 ]; then
  rm -f "$dest"
  say "uninstalled"
  exit 0
fi

if [ -n "$check_url" ]; then
  sleep 2
  fails=0
  status() { # user-agent -> HTTP status, 000 when the connection is cut
    local c
    c=$(curl -s -o /dev/null --max-time 20 -A "$1" -w '%{http_code}' "$check_url/" || true)
    c=${c:-000}
    echo "${c: -3}"
  }
  expect() { # label, user-agent, "open" | "cut"
    local c ok
    c=$(status "$2")
    if [ "$3" = cut ]; then [ "$c" = 000 ] && ok=1 || ok=0; else [ "$c" != 000 ] && ok=1 || ok=0; fi
    if [ "$ok" = 1 ]; then say "ok   $1 -> $c"; else say "FAIL $1 -> $c (expected $3)"; fails=$((fails + 1)); fi
  }
  expect "Chrome   " "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" open
  expect "Googlebot" "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" open
  expect "curl     " "curl/8.7.1" open
  expect "Bytespider" "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)" cut
  if [ "$fails" != 0 ]; then
    restore
    die "$fails live checks failed: previous configuration restored"
  fi
fi
say "installed: $site is protected (backup in $bk)"

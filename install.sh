#!/bin/sh
# N-antibot installer. Puts the `n-antibot` command on this machine in its own virtual environment, so it never
# touches the system Python. Run it as root to install for the whole machine (recommended on a server):
#
#   curl -fsSL https://raw.githubusercontent.com/KrilinZ/N-antibot/main/install.sh | sudo sh
#
# Then:  sudo n-antibot install --site example.com --check-url https://example.com
#
# Environment (all optional):
#   N_ANTIBOT_VERSION   tag to install, e.g. v0.6.0 (default: the main branch)
#   N_ANTIBOT_HOME      where the virtual environment goes (default: /opt/n-antibot as root, ~/.local/share/n-antibot)
#   N_ANTIBOT_BIN       where the command is linked (default: /usr/local/bin as root, ~/.local/bin)
#   N_ANTIBOT_SOURCE    install from this path or URL instead of GitHub
# To remove it: delete the N_ANTIBOT_HOME folder and the n-antibot link.
set -eu

say() { printf 'n-antibot: %s\n' "$*"; }
die() { printf 'n-antibot: %s\n' "$*" >&2; exit 1; }

if [ "$(id -u)" = 0 ]; then
  home=${N_ANTIBOT_HOME:-/opt/n-antibot}
  bin=${N_ANTIBOT_BIN:-/usr/local/bin}
else
  home=${N_ANTIBOT_HOME:-$HOME/.local/share/n-antibot}
  bin=${N_ANTIBOT_BIN:-$HOME/.local/bin}
fi

if [ -n "${N_ANTIBOT_SOURCE:-}" ]; then
  source=$N_ANTIBOT_SOURCE
elif [ -n "${N_ANTIBOT_VERSION:-}" ]; then
  source="https://github.com/KrilinZ/N-antibot/archive/refs/tags/$N_ANTIBOT_VERSION.tar.gz"
else
  source="https://github.com/KrilinZ/N-antibot/archive/refs/heads/main.tar.gz"
fi

python=""
for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    python=$candidate
    break
  fi
done
[ -n "$python" ] || die "Python 3.9 or later is needed. Install it (Debian/Ubuntu: apt install python3 python3-venv) and run this again."

say "using $($python --version 2>&1), installing into $home"
if ! "$python" -m venv "$home" 2>/dev/null; then
  die "could not create a virtual environment. On Debian and Ubuntu: apt install python3-venv"
fi
"$home/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade "$source" ||
  die "the download or the installation failed. Nothing else was changed."

mkdir -p "$bin"
ln -sf "$home/bin/n-antibot" "$bin/n-antibot"
say "installed $("$bin/n-antibot" --version)"
case ":$PATH:" in
  *":$bin:"*) ;;
  *) say "note: $bin is not in your PATH. Use $bin/n-antibot or add it to PATH." ;;
esac
say "next: n-antibot install --site example.com --check-url https://example.com   (as root, on the web server)"

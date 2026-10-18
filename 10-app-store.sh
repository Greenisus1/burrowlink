#!/bin/bash
# pi-app-store: 1
# pi-app-store-category: network
# pi-app-store-description: A small WireGuard VPN server manager: two-key setup, one-key up/down, add peers with ready-to-paste client configs, live handshake and transfer stats.
set -eu
cd -- "$(dirname -- "$0")"
ready() { python3 -c 'import curses' >/dev/null 2>&1; }
action=${1:-run}
case "${action,,}" in
 install)
  if ! ready; then
   [ "$(id -u)" -eq 0 ] || { echo 'Install through the Store with sudo to add Python.';exit 1; }
   if command -v apt-get >/dev/null;then apt-get update;apt-get install -y python3
   elif command -v apk >/dev/null;then apk add --no-cache python3
   elif command -v pacman >/dev/null;then echo 'Arch may upgrade the whole system; review pacman prompt.';pacman -Syu --needed python
   else echo 'Install Python 3 with curses using your distro tools.';exit 1;fi
  fi
  ready
  python3 -c 'from pathlib import Path;[compile(p.read_bytes(),str(p),"exec") for p in Path(".").glob("*.py")]' ;;
 status) ready ;;
 down)
  [ "$(id -u)" -eq 0 ] || { echo 'Run with sudo: sudo bash app-store.sh down';exit 1; }
  wg-quick down wg0 2>/dev/null && echo 'burrowlink tunnel down' || echo 'tunnel not running' ;;
 run) [ "$#" -eq 0 ] || shift;exec python3 burrowlink.py "$@" ;;
 *) echo 'Use install, status, run or down (any casing).';exit 2 ;;
esac

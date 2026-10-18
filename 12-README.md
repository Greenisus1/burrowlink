# Burrowlink

A small WireGuard VPN server manager for your Pi. Set up a tunnel (wg0),
bring it up and down with one key, and add phones or laptops as peers
with a ready-to-paste client config. Fullscreen terminal UI driving the
OS wireguard tools directly - no NetworkManager, and it never touches
your existing Wi-Fi or ethernet setup; the tunnel is purely additive.

## What it does

- **Two-key setup** (`s`, press twice): installs wireguard via apt if
  needed, generates the server keypair, writes `/etc/wireguard/wg0.conf`,
  enables IP forwarding, brings the tunnel up on UDP 51820.
- **One-key down** (`h`): `wg-quick down` and forwarding back off.
- **Peers** (`a` / `x`): each peer gets the next free IP and a complete
  client config shown on screen to copy. Install `qrencode` and pipe it
  through `qrencode -t ansiutf8` to scan it as a QR code instead.
- **Live stats**: per-peer last handshake and bytes transferred.
- **Inspect anything first**: `BURROWLINK_DRY_RUN=1` walks the whole UI
  printing plans; `python3 burrowlink.py --dump-plan` shows the exact
  setup and shutdown steps.

## Router step (manual, one time)

For access from outside your home, forward UDP port 51820 on your router
to this Pi, and use your home's public IP (or a dynamic DNS name) as the
Endpoint in the client configs. Inside your home network it works with
the Pi's LAN address as-is.

## Install (Pi App Store)

Install through the Pi App Store, or:

```sh
sudo bash app-store.sh install   # checks Python/curses, compiles sources
sudo python3 burrowlink.py       # or: bash app-store.sh run
sudo bash app-store.sh down      # emergency tunnel off-switch
```

State lives in `/root/burrowlink/state.json` (override with
`BURROWLINK_HOME`). Nothing starts at boot.

## Tests

```sh
python3 test_burrowlink.py   # unit tests (peers, confs, plan safety)
BURROWLINK_DRY_RUN=1 python3 test_pty.py   # fullscreen dry-run walkthrough
```

MIT license, copyright Greenisus1. Built with AI assistance from my design.

#!/usr/bin/env python3
"""Burrowlink - a small WireGuard server manager for your Pi.

Fullscreen curses UI to set up a WireGuard tunnel (wg0), bring it up and
down, and add or remove peers (phones/laptops) with ready-to-paste client
configs. Drives the OS wireguard tools directly - no NetworkManager.
Additive only: it never touches your existing Wi-Fi or ethernet setup.

Set BURROWLINK_DRY_RUN=1 to walk the whole UI printing the plan instead
of changing anything.

MIT license, copyright Greenisus1. Built with AI assistance from my design.
"""
import curses, json, os, re, subprocess, sys, time

VERSION = "1.0.0"
APP_DIR = os.environ.get("BURROWLINK_HOME", "/root/burrowlink")
STATE = os.path.join(APP_DIR, "state.json")
WG_CONF = "/etc/wireguard/wg0.conf"
SUBNET = "10.66.0"
PORT = 51820
DRY = os.environ.get("BURROWLINK_DRY_RUN") == "1"


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {"server_priv": "", "server_pub": "", "peers": []}


def save_state(st):
    os.makedirs(APP_DIR, exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)


def run(cmd):
    if DRY:
        return 0, ""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, ""


def wg_genkey():
    if DRY:
        return "DRYRUNprivatekey=", "DRYRUNpublickey="
    rc, out = run(["sh", "-c", "wg genkey"])
    priv = out.strip()
    rc, out = run(["sh", "-c", f"echo '{priv}' | wg pubkey"])
    return priv, out.strip()


def render_server_conf(st):
    lines = ["[Interface]",
             f"Address = {SUBNET}.1/24",
             f"ListenPort = {PORT}",
             f"PrivateKey = {st['server_priv']}", ""]
    for p in st["peers"]:
        lines += ["[Peer]",
                  f"# {p['name']}",
                  f"PublicKey = {p['pub']}",
                  f"AllowedIPs = {p['ip']}/32", ""]
    return "\n".join(lines)


def render_client_conf(st, peer, endpoint):
    return "\n".join([
        "[Interface]",
        f"PrivateKey = {peer['priv']}",
        f"Address = {peer['ip']}/24",
        "DNS = 1.1.1.1", "",
        "[Peer]",
        f"PublicKey = {st['server_pub']}",
        f"Endpoint = {endpoint}:{PORT}",
        "AllowedIPs = 0.0.0.0/0",
        "PersistentKeepalive = 25", ""])


def next_ip(st):
    used = {p["ip"] for p in st["peers"]} | {f"{SUBNET}.1"}
    for i in range(10, 255):
        cand = f"{SUBNET}.{i}"
        if cand not in used:
            return cand
    return None


def add_peer(st, name):
    ip = next_ip(st)
    if not ip:
        return None
    priv, pub = wg_genkey()
    peer = {"name": name, "priv": priv, "pub": pub, "ip": ip,
            "added": int(time.time())}
    st["peers"].append(peer)
    save_state(st)
    return peer


def remove_peer(st, idx):
    peer = st["peers"].pop(idx)
    save_state(st)
    return peer


def apply_conf(st):
    """Write wg0.conf and, if the tunnel is up, sync the live interface."""
    os.makedirs(APP_DIR, exist_ok=True)
    open(os.path.join(APP_DIR, "wg0.conf"), "w").write(render_server_conf(st))
    if DRY:
        return
    os.makedirs("/etc/wireguard", exist_ok=True)
    open(WG_CONF, "w").write(render_server_conf(st))
    os.chmod(WG_CONF, 0o600)
    if tunnel_up():
        run(["sh", "-c", f"wg-quick strip wg0 > /tmp/wg0.stripped && "
                         f"wg syncconf wg0 /tmp/wg0.stripped"])


def tunnel_up():
    if DRY:
        return False
    return run(["wg", "show", "wg0"])[0] == 0


def peer_stats():
    """(last_handshake_epoch, rx_bytes, tx_bytes) per public key."""
    stats = {}
    if DRY:
        return stats
    rc, out = run(["wg", "show", "wg0", "dump"])
    if rc:
        return stats
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 7:
            stats[parts[0]] = (int(parts[4]), int(parts[5]), int(parts[6]))
    return stats


def setup_plan(st):
    return [
        "apt-get update && apt-get install -y wireguard qrencode",
        "mkdir -p /etc/wireguard",
        f"write {WG_CONF} (mode 600)",
        "sysctl -w net.ipv4.ip_forward=1 (+ persist in /etc/sysctl.d)",
        f"wg-quick up wg0   # listens on UDP {PORT}",
    ]


def down_plan():
    return ["wg-quick down wg0", "sysctl -w net.ipv4.ip_forward=0"]


def do_setup(st):
    if DRY:
        return True, "dry run"
    rc, out = run(["sh", "-c", "command -v wg || (apt-get update -qq && "
                               "apt-get install -y -qq wireguard)"])
    if run(["sh", "-c", "command -v wg"])[0]:
        return False, "wireguard tools missing and apt install failed"
    if not st["server_priv"]:
        st["server_priv"], st["server_pub"] = wg_genkey()
        save_state(st)
    apply_conf(st)
    run(["sh", "-c", "sysctl -w net.ipv4.ip_forward=1 >/dev/null && "
                     "echo net.ipv4.ip_forward=1 > /etc/sysctl.d/90-burrowlink.conf"])
    rc, out = run(["wg-quick", "up", "wg0"])
    if rc and "already exists" not in out:
        return False, out.strip()[:120]
    return True, "up"


def do_down():
    if DRY:
        return True, "dry run"
    run(["wg-quick", "down", "wg0"])
    run(["sh", "-c", "sysctl -w net.ipv4.ip_forward=0 >/dev/null"])
    return True, "down"


def lan_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except Exception:
        return "<pi-ip>"
    finally:
        s.close()


# ---------- UI ----------

def header(scr, w, sub):
    scr.addnstr(0, 0, f" BURROWLINK v{VERSION} - {sub}".ljust(w - 1), w - 1,
                curses.A_REVERSE)


def keys(scr, h, w, s):
    scr.addnstr(h - 1, 0, s[:w - 1], w - 1, curses.A_REVERSE)


def prompt(scr, label):
    curses.echo()
    curses.curs_set(1)
    h, w = scr.getmaxyx()
    scr.addnstr(h - 3, 2, label + " ", w - 4, curses.A_BOLD)
    scr.refresh()
    try:
        v = scr.getstr(h - 3, 2 + len(label) + 1, 200).decode().strip()
    except Exception:
        v = ""
    curses.noecho()
    curses.curs_set(0)
    return v


def show_block(scr, title, text):
    lines = text.split("\n")
    top = 0
    while True:
        scr.erase()
        h, w = scr.getmaxyx()
        header(scr, w, title[:w - 20])
        body = h - 3
        top = max(0, min(top, len(lines) - body))
        for row, line in enumerate(lines[top:top + body]):
            scr.addnstr(2 + row, 2, line, w - 4)
        keys(scr, h, w, "[j/k] scroll  [q] back")
        scr.refresh()
        ch = scr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            top = max(0, top - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            top = min(max(0, len(lines) - body), top + 1)
        elif ch in (ord("q"), 27, 10, 13):
            return


def main(scr):
    curses.curs_set(0)
    st = load_state()
    sel, msg, armed_at = 0, "", 0.0
    while True:
        scr.erase()
        h, w = scr.getmaxyx()
        header(scr, w, "WireGuard VPN" + ("  [DRY RUN]" if DRY else ""))
        up = tunnel_up()
        scr.addnstr(2, 2, f"Tunnel:   {'UP' if up else 'down'}"
                          f"   port UDP {PORT}   subnet {SUBNET}.0/24", w - 4,
                    curses.A_BOLD if up else 0)
        scr.addnstr(3, 2, f"Endpoint: {lan_ip()}:{PORT}  "
                          "(router: forward UDP 51820 to this Pi for outside access)",
                    w - 4)
        scr.addnstr(4, 2, f"Server:   key {'set' if st['server_priv'] else 'not set'}"
                          f"   {len(st['peers'])} peers", w - 4)
        stats = peer_stats()
        for row, p in enumerate(st["peers"][:h - 9]):
            hs, rx, tx = stats.get(p["pub"], (0, 0, 0))
            seen = time.strftime("%H:%M", time.localtime(hs)) if hs else "never"
            line = f"{p['name']}  {p['ip']}  last handshake {seen}  rx {rx} tx {tx}"
            attr = curses.A_REVERSE if row == sel else 0
            scr.addnstr(6 + row, 4, line.ljust(w - 8)[:w - 8], w - 8, attr)
        if time.time() - armed_at < 8:
            scr.addnstr(h - 3, 2, "ARMED: press s again within 8s to install "
                                  "wireguard + bring the tunnel up.",
                        w - 4, curses.A_BOLD)
        if msg:
            scr.addnstr(h - 4, 2, msg, w - 4, curses.A_BOLD)
        keys(scr, h, w, "[s]etup/start  s[h]ut down  [a]dd peer  "
                        "[x] remove peer  [c]onfig view  [r]efresh  [q]uit")
        scr.refresh()
        ch = scr.getch()
        msg = ""
        c = chr(ch).lower() if 0 <= ch < 256 else ""
        if c == "q" or ch == 27:
            return
        elif ch in (curses.KEY_UP, ord("k")):
            sel = max(0, sel - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            sel = min(max(0, len(st["peers"]) - 1), sel + 1)
        elif c == "s":
            if up:
                msg = "Already up."
            elif time.time() - armed_at < 8 and armed_at:
                armed_at = 0.0
                if DRY:
                    show_block(scr, "setup plan (dry run)",
                               "\n".join(setup_plan(st)))
                else:
                    ok, info = do_setup(st)
                    msg = "Tunnel UP." if ok else "Setup failed: " + info
            else:
                armed_at = time.time()
        elif c == "h":
            armed_at = 0.0
            if DRY:
                show_block(scr, "shutdown plan (dry run)",
                           "\n".join(down_plan()))
            else:
                ok, info = do_down()
                msg = "Tunnel down." if ok else info
        elif c == "a":
            if not st["server_priv"] and not DRY:
                msg = "Run setup first (s)."
            else:
                name = prompt(scr, "Peer name (e.g. phone):")
                if name:
                    peer = add_peer(st, name)
                    if peer is None:
                        msg = "No IPs left."
                    else:
                        apply_conf(st)
                        show_block(scr, f"client config: {name}",
                                   render_client_conf(st, peer, lan_ip()) +
                                   "\nTip: apt install qrencode, then pipe "
                                   "this into qrencode -t ansiutf8")
        elif c == "x" and st["peers"]:
            peer = remove_peer(st, sel)
            sel = max(0, sel - 1)
            apply_conf(st)
            msg = f"Removed {peer['name']}."
        elif c == "c":
            show_block(scr, "server config (wg0.conf)",
                       render_server_conf(st))
        elif c == "r":
            pass


if __name__ == "__main__":
    if "--dump-plan" in sys.argv:
        st = load_state()
        print("\n".join(setup_plan(st)))
        print("--")
        print("\n".join(down_plan()))
        sys.exit(0)
    curses.wrapper(main)

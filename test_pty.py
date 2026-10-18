"""PTY walkthrough (dry-run): arm+confirm setup prints plan, add peer shows
client config, remove peer, quit. Nothing touches the system."""
import json, os, pty, re, select, sys, tempfile, time

home = tempfile.mkdtemp()
env = dict(os.environ, BURROWLINK_HOME=home, BURROWLINK_DRY_RUN="1",
           TERM="xterm-256color", LINES="30", COLUMNS="100")
pid, fd = pty.fork()
if pid == 0:
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")
    os.execvpe(sys.executable, [sys.executable, "burrowlink.py"], env)

out = b""
def pump(t):
    global out
    end = time.time() + t
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try: out += os.read(fd, 65536)
            except OSError: break

fail = []
pump(2.0)
if not re.search(rb"BURROWLINK v1\.0\.0", out): fail.append("title")
if not re.search(rb"DRY RUN", out): fail.append("dry marker")
if not re.search(rb"forward UDP 51820", out): fail.append("router hint")
os.write(fd, b"s"); pump(0.5)          # arm
os.write(fd, b"s"); pump(1.0)          # confirm -> plan view
if not re.search(rb"wg-quick up wg0", out): fail.append("setup plan")
os.write(fd, b"q"); pump(0.5)
os.write(fd, b"a"); pump(0.5)
os.write(fd, b"phone\n"); pump(1.0)    # add peer -> client config view
if not re.search(rb"Endpoint = .*51820", out): fail.append("client config")
if not re.search(rb"PublicKey", out): fail.append("client pubkey")
os.write(fd, b"q"); pump(0.5)
if not re.search(rb"phone  10\.66\.0\.10", out): fail.append("peer listed")
os.write(fd, b"x"); pump(0.8)          # remove
os.write(fd, b"h"); pump(0.8)          # shutdown plan
if not re.search(rb"wg-quick down wg0", out): fail.append("down plan")
os.write(fd, b"q"); pump(0.5)
os.write(fd, b"q"); pump(0.8)
wp, _ = os.waitpid(pid, os.WNOHANG)
if wp == 0:
    try: os.kill(pid, 9); os.waitpid(pid, 0)
    except ProcessLookupError: pass
    fail.append("did not quit")
if os.path.exists("/etc/wireguard/wg0.conf"): fail.append("TOUCHED SYSTEM")
st = json.load(open(os.path.join(home, "state.json")))
if any(p["name"] == "phone" for p in st["peers"]): fail.append("peer not removed")
if fail:
    print("PTY FAIL:", ", ".join(fail)); sys.exit(1)
print("PTY PASS")

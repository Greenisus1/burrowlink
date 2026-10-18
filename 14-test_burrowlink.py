import importlib.util, os, tempfile, unittest

os.environ["BURROWLINK_HOME"] = tempfile.mkdtemp()
os.environ["BURROWLINK_DRY_RUN"] = "1"
spec = importlib.util.spec_from_file_location(
    "burrowlink", os.path.join(os.path.dirname(__file__), "burrowlink.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def fresh_state():
    try:
        os.remove(b.STATE)
    except OSError:
        pass
    st = b.load_state()
    st["server_priv"], st["server_pub"] = "SPRIV", "SPUB"
    b.save_state(st)
    return st


class TestPeers(unittest.TestCase):
    def test_next_ip_skips_used(self):
        st = fresh_state()
        p1 = b.add_peer(st, "phone")
        p2 = b.add_peer(st, "laptop")
        self.assertEqual(p1["ip"], "10.66.0.10")
        self.assertEqual(p2["ip"], "10.66.0.11")
        b.remove_peer(st, 0)
        p3 = b.add_peer(st, "tablet")
        self.assertEqual(p3["ip"], "10.66.0.10")  # reused gap

    def test_remove(self):
        st = fresh_state()
        b.add_peer(st, "a")
        gone = b.remove_peer(st, 0)
        self.assertEqual(gone["name"], "a")
        self.assertEqual(st["peers"], [])


class TestConfs(unittest.TestCase):
    def test_server_conf(self):
        st = fresh_state()
        b.add_peer(st, "phone")
        c = b.render_server_conf(st)
        self.assertIn("Address = 10.66.0.1/24", c)
        self.assertIn("ListenPort = 51820", c)
        self.assertIn("PrivateKey = SPRIV", c)
        self.assertIn("# phone", c)
        self.assertIn("AllowedIPs = 10.66.0.10/32", c)

    def test_client_conf(self):
        st = fresh_state()
        peer = b.add_peer(st, "phone")
        c = b.render_client_conf(st, peer, "192.168.1.50")
        self.assertIn(f"PrivateKey = {peer['priv']}", c)
        self.assertIn("Address = 10.66.0.10/24", c)
        self.assertIn("PublicKey = SPUB", c)
        self.assertIn("Endpoint = 192.168.1.50:51820", c)
        self.assertIn("PersistentKeepalive = 25", c)
        self.assertNotIn("SPRIV", c)  # server private key never leaves

    def test_plans_safe(self):
        st = fresh_state()
        plan = "\n".join(b.setup_plan(st))
        self.assertIn("wg-quick up wg0", plan)
        self.assertNotIn("wpa_supplicant", plan)   # never touches client Wi-Fi
        self.assertNotIn("hostapd", plan)
        down = "\n".join(b.down_plan())
        self.assertIn("wg-quick down wg0", down)
        self.assertIn("ip_forward=0", down)

    def test_apply_conf_dry_local_only(self):
        st = fresh_state()
        b.add_peer(st, "phone")
        b.apply_conf(st)  # dry-run: writes only inside APP_DIR
        self.assertTrue(os.path.exists(os.path.join(b.APP_DIR, "wg0.conf")))
        self.assertFalse(os.path.exists("/etc/wireguard/wg0.conf"))


if __name__ == "__main__":
    unittest.main()

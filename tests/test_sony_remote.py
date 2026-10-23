"""tools/sony-remote.py against a fake BRAVIA on 127.0.0.1: button codes, inputs, power, mute, key and guards.

Run from the repository root: python3 -m unittest discover -s tests -v
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import importlib.util
import json
import threading
import urllib.error
import urllib.request
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sony_remote", ROOT / "tools" / "sony-remote.py")
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)

PSK = "0000"
SETTINGS_CODE = "TV-OWN-ACTIONMENU"
INPUTS = [{"uri": "extInput:hdmi?port=1", "title": "HDMI 1", "label": "Apple TV", "connection": True},
          {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "label": "", "connection": False},
          {"uri": "extInput:cec?type=audiosystem&port=3&logicalAddr=5", "title": "Sonos Beam",
           "label": "", "connection": True}]


class FakeTv(BaseHTTPRequestHandler):
    sent = []
    power = "active"
    mute = False
    field = None  # text in the TV's open keyboard field; None when no field is open

    def log_message(self, *args):
        pass

    def answer(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        if self.headers.get("X-Auth-PSK") != PSK:
            if self.path == "/sony/IRCC":
                return self.answer(403)
            return self.answer(200, json.dumps({"error": [403, "Forbidden"], "id": 1}).encode())
        if self.path == "/sony/IRCC":
            self.sent.append(body.split("<IRCCCode>")[1].split("</IRCCCode>")[0])
            return self.answer(200)
        call = json.loads(body)
        if call["method"] == "getRemoteControllerInfo":
            result = [{"bundled": True, "type": "IR_REMOTE_BUNDLE_TYPE_AEP_N"},
                      [{"name": "ActionMenu", "value": SETTINGS_CODE}]]
        elif call["method"] == "getCurrentExternalInputsStatus":
            result = [INPUTS]
        elif call["method"] == "setPlayContent":
            self.sent.append(call["params"][0]["uri"])
            result = []
        elif call["method"] == "getPowerStatus":
            result = [{"status": FakeTv.power}]
        elif call["method"] == "setPowerStatus":
            FakeTv.power = "active" if call["params"][0]["status"] else "standby"
            result = []
        elif call["method"] in ("getTextForm", "setTextForm"):
            if FakeTv.field is None:
                return self.answer(200, json.dumps({"error": [7, "Illegal State"], "id": 1}).encode())
            if call["method"] == "setTextForm":
                FakeTv.field = call["params"][0]
                result = [0]
            else:
                result = [{"text": FakeTv.field}]
        elif call["method"] == "getVolumeInformation":
            result = [[{"target": "speaker", "volume": 12, "mute": FakeTv.mute}]]
        else:
            return self.answer(200, json.dumps({"error": [12, "No Such Method"], "id": 1}).encode())
        self.answer(200, json.dumps({"result": result, "id": 1}).encode())


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class SonyRemoteTest(unittest.TestCase):
    def setUp(self):
        FakeTv.sent, FakeTv.power, FakeTv.mute, FakeTv.field = [], "active", False, None
        self.tv_server = serve(ThreadingHTTPServer(("127.0.0.1", 0), FakeTv))
        self.tv = remote.Tv(f"127.0.0.1:{self.tv_server.server_address[1]}", PSK)
        self.page = serve(ThreadingHTTPServer(("127.0.0.1", 0),
                                              remote.make_handler(self.tv, lan=False, command="cd ~/x && <run>")))
        self.url = f"http://127.0.0.1:{self.page.server_address[1]}"

    def tearDown(self):
        for server in (self.page, self.tv_server):
            server.shutdown()
            server.server_close()

    def request(self, path, method="GET", headers=None):
        req = urllib.request.Request(self.url + path, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def press(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=body, method="POST", headers={"X-Remote": "1"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def test_page(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("TV Remote", body)
        self.assertIn("<code>cd ~/x &amp;&amp; &lt;run&gt;</code>", body)

    def test_power_toggles(self):
        self.assertEqual(self.press("/key/power")[0], 204)
        self.assertEqual(FakeTv.power, "standby")
        self.assertEqual(self.press("/key/power")[0], 204)
        self.assertEqual(FakeTv.power, "active")

    def test_mute_state(self):
        self.assertEqual(json.loads(self.request("/state")[1]), {"muted": False})
        FakeTv.mute = True
        self.assertEqual(json.loads(self.request("/state")[1]), {"muted": True})

    def test_keys_use_the_tvs_codes_then_the_fallback(self):
        self.assertEqual(self.press("/key/settings")[0], 204)
        self.assertEqual(self.press("/key/up")[0], 204)
        self.assertEqual(FakeTv.sent, [SETTINGS_CODE, remote.FALLBACK_CODES["Up"]])

    def test_inputs_and_switch(self):
        status, body = self.request("/inputs")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), [
            {"uri": "extInput:hdmi?port=1", "name": "Apple TV", "connected": True},
            {"uri": "extInput:hdmi?port=2", "name": "HDMI 2", "connected": False}])
        self.assertEqual(self.press("/input?uri=extInput%3Ahdmi%3Fport%3D2")[0], 204)
        self.assertEqual(FakeTv.sent, ["extInput:hdmi?port=2"])

    def test_only_external_inputs(self):
        self.assertEqual(self.press("/input?uri=http%3A%2F%2Fexample.com")[0], 502)
        self.assertEqual(FakeTv.sent, [])

    def test_wrong_key_is_named(self):
        self.tv.psk = "1234"
        status, body = self.press("/key/ok")
        self.assertEqual(status, 502)
        self.assertIn("refused the key", body)
        self.assertIn("refused the key", self.request("/inputs")[1])

    def test_guards(self):
        self.assertEqual(self.request("/key/ok", "POST")[0], 403)
        self.assertEqual(self.request("/", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.press("/key/poweroff")[0], 404)
        self.assertEqual(FakeTv.sent, [])


    def test_typing(self):
        self.assertEqual(json.loads(self.request("/text")[1]), {"active": False, "text": None})
        status, body = self.press("/text", json.dumps({"text": "dune"}).encode())
        self.assertEqual(status, 502)
        self.assertIn("No text field is open", body)
        FakeTv.field = "du"
        self.assertEqual(json.loads(self.request("/text")[1]), {"active": True, "text": "du"})
        self.assertEqual(self.press("/text", json.dumps({"text": "dune"}).encode())[0], 204)
        self.assertEqual(FakeTv.field, "dune")
        self.assertEqual(self.press("/text", b'{"text": 5}')[0], 400)

    def test_start_command(self):
        args = type("Args", (), {"lan": True, "port": 9000})()
        command = remote.start_command("192.168.1.210", "0000", args)
        self.assertTrue(command.startswith("cd "))
        self.assertTrue(command.endswith(" && TV_HOST=192.168.1.210 TV_PSK=0000 "
                                         "python3 tools/sony-remote.py --lan --port 9000"))


if __name__ == "__main__":
    unittest.main()

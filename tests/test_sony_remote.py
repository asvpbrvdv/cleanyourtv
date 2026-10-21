"""tools/sony-remote.py against a fake BRAVIA on 127.0.0.1: button codes, inputs, key and guards.

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
          {"uri": "extInput:hdmi?port=2", "title": "HDMI 2", "label": "", "connection": False}]


class FakeTv(BaseHTTPRequestHandler):
    sent = []

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
        else:
            return self.answer(200, json.dumps({"error": [12, "No Such Method"], "id": 1}).encode())
        self.answer(200, json.dumps({"result": result, "id": 1}).encode())


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class SonyRemoteTest(unittest.TestCase):
    def setUp(self):
        FakeTv.sent = []
        self.tv_server = serve(ThreadingHTTPServer(("127.0.0.1", 0), FakeTv))
        self.tv = remote.Tv(f"127.0.0.1:{self.tv_server.server_address[1]}", PSK)
        self.page = serve(ThreadingHTTPServer(("127.0.0.1", 0), remote.make_handler(self.tv, lan=False)))
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

    def press(self, path):
        return self.request(path, "POST", {"X-Remote": "1"})

    def test_page(self):
        status, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("TV Remote", body)

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


if __name__ == "__main__":
    unittest.main()

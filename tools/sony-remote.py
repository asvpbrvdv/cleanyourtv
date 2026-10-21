#!/usr/bin/env python3
"""A small remote for Sony BRAVIA TVs in the browser, over Sony's IP control (no ADB needed).

On the TV, once: Settings > Network & Internet > Home network > IP control. Set Authentication to
"Normal and Pre-Shared Key", choose a Pre-Shared Key and switch Simple IP control on. Then:

    TV_HOST=192.168.1.50 TV_PSK=<key> python3 tools/sony-remote.py         opens http://127.0.0.1:8765
    ... python3 tools/sony-remote.py --lan                                  also serve phones on the Wi-Fi
    ... python3 tools/sony-remote.py --port 9000 --no-browser

Keys: arrows, Enter = OK, Esc or Backspace = Back, H = Home, S = Settings, I = Input, + / - = volume,
M = mute. Python 3 standard library only. The button codes come from the TV itself
(getRemoteControllerInfo), with Sony's published codes as a fallback, and the input list from
getCurrentExternalInputsStatus, so each HDMI port gets its own button.

The page only answers on 127.0.0.1 unless --lan is given: anyone who can reach it can press buttons
on the TV without knowing the key.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TIMEOUT_S = 4.0

# Sony's IRCC codes, used when the TV does not list its own. The TV's list wins.
FALLBACK_CODES = {
    "Up": "AAAAAQAAAAEAAAB0Aw==",
    "Down": "AAAAAQAAAAEAAAB1Aw==",
    "Left": "AAAAAQAAAAEAAAA0Aw==",
    "Right": "AAAAAQAAAAEAAAAzAw==",
    "Confirm": "AAAAAQAAAAEAAABlAw==",
    "Return": "AAAAAgAAAJcAAAAjAw==",
    "Home": "AAAAAQAAAAEAAABgAw==",
    "ActionMenu": "AAAAAgAAAMQAAABLAw==",
    "Input": "AAAAAQAAAAEAAAAlAw==",
    "VolumeUp": "AAAAAQAAAAEAAAASAw==",
    "VolumeDown": "AAAAAQAAAAEAAAATAw==",
    "Mute": "AAAAAQAAAAEAAAAUAw==",
}

# Page button -> IRCC names to try, in order. The gear button on Google TV BRAVIA remotes sends
# ActionMenu (quick settings); older sets call a similar key Options.
BUTTONS = {
    "up": ["Up"], "down": ["Down"], "left": ["Left"], "right": ["Right"],
    "ok": ["Confirm"], "back": ["Return"], "home": ["Home"],
    "settings": ["ActionMenu", "Options"], "input": ["Input"],
    "volup": ["VolumeUp"], "voldown": ["VolumeDown"], "mute": ["Mute"],
}

IRCC_BODY = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
             's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
             '<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1"><IRCCCode>{}</IRCCCode>'
             '</u:X_SendIRCC></s:Body></s:Envelope>')


class Tv:
    def __init__(self, host, psk):
        self.base = f"http://{host}"
        self.psk = psk
        self.codes = None

    def _post(self, path, body, content_type, extra=None):
        headers = {"Content-Type": content_type, "X-Auth-PSK": self.psk, **(extra or {})}
        req = urllib.request.Request(self.base + path, data=body.encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return resp.read().decode("utf-8", "replace")

    def call(self, service, method, params=None, version="1.0"):
        body = json.dumps({"method": method, "id": 1, "params": params or [], "version": version})
        reply = json.loads(self._post(f"/sony/{service}", body, "application/json"))
        if "error" in reply:
            if reply["error"][:1] == [403]:
                raise PermissionError(method)
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply.get("result", [])

    def load_codes(self):
        """The TV's own codes over Sony's defaults; kept once read, retried while the TV can't answer."""
        if self.codes is not None:
            return self.codes
        codes = dict(FALLBACK_CODES)
        try:
            result = self.call("system", "getRemoteControllerInfo")
            listed = result[1] if len(result) > 1 else []
            codes.update({c["name"]: c["value"] for c in listed if c.get("name") and c.get("value")})
            self.codes = codes
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError) as e:
            print(f"Could not read the TV's button codes, using Sony's defaults: {e}", file=sys.stderr)
        return codes

    def press(self, button):
        codes = self.load_codes()
        for name in BUTTONS[button]:
            if name in codes:
                self._post("/sony/IRCC", IRCC_BODY.format(codes[name]), 'text/xml; charset="utf-8"',
                           {"SOAPACTION": '"urn:schemas-sony-com:service:IRCC:1#X_SendIRCC"'})
                return
        raise RuntimeError(f"the TV has no code for {button}")

    def inputs(self):
        try:
            result = self.call("avContent", "getCurrentExternalInputsStatus", version="1.1")
        except RuntimeError:
            result = self.call("avContent", "getCurrentExternalInputsStatus")
        items = result[0] if result else []
        return [{"uri": i["uri"], "name": i.get("label") or i.get("title") or i["uri"],
                 "connected": bool(i.get("connection"))} for i in items if i.get("uri")]

    def switch(self, uri):
        if not uri.startswith("extInput:"):
            raise RuntimeError("only external inputs can be chosen here")
        self.call("avContent", "setPlayContent", [{"uri": uri}])


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV Remote</title>
<style>
:root{--bg:#0b0c0f;--pad:#1a1c22;--key:#262931;--key-hi:#353945;--text:#eef0f4;--dim:#8a8f9c;--accent:#cfffcf}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;
 background:var(--bg);color:var(--text);font:15px/1.3 -apple-system,BlinkMacSystemFont,"Inter",sans-serif}
main{width:100%;max-width:300px;padding:20px 16px}
.row{display:flex;gap:10px;justify-content:center;margin:10px 0}
button{appearance:none;border:0;border-radius:14px;background:var(--key);color:var(--text);
 font:inherit;padding:12px 0;flex:1;cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent}
button:hover{background:var(--key-hi)}
button:active{transform:scale(.96)}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;background:var(--pad);
 border-radius:50%;padding:18px;aspect-ratio:1;margin:16px 0}
.pad button{border-radius:50%;font-size:20px;padding:0}
.pad .ok{background:var(--key-hi);font-size:15px}
h2{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:18px 0 6px}
#inputs{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
#inputs button.off{color:var(--dim)}
#status{min-height:1.3em;font-size:13px;color:var(--dim);text-align:center;margin-top:14px}
#status.err{color:#ff8a8a}
</style></head><body><main>
<div class="row"><button data-k="input">Input</button><button data-k="home">Home</button><button data-k="settings">Settings</button></div>
<div class="pad">
 <span></span><button data-k="up" aria-label="Up">&#9650;</button><span></span>
 <button data-k="left" aria-label="Left">&#9664;</button><button class="ok" data-k="ok">OK</button><button data-k="right" aria-label="Right">&#9654;</button>
 <span></span><button data-k="down" aria-label="Down">&#9660;</button><span></span>
</div>
<div class="row"><button data-k="back">Back</button></div>
<div class="row"><button data-k="voldown" aria-label="Volume down">Vol &minus;</button><button data-k="mute">Mute</button><button data-k="volup" aria-label="Volume up">Vol +</button></div>
<h2>Inputs</h2><div id="inputs"><span style="color:var(--dim)">Loading&hellip;</span></div>
<div id="status"></div>
</main><script>
const status = document.getElementById("status");
function say(text, err) { status.textContent = text; status.className = err ? "err" : ""; }
async function post(path) {
  try {
    const r = await fetch(path, {method: "POST", headers: {"X-Remote": "1"}});
    if (!r.ok) say(await r.text(), true); else say("");
  } catch (e) { say("The remote stopped. Start it again in Terminal.", true); }
}
const press = k => post("/key/" + k);
document.querySelectorAll("[data-k]").forEach(b => b.addEventListener("click", () => press(b.dataset.k)));
const keys = {ArrowUp:"up", ArrowDown:"down", ArrowLeft:"left", ArrowRight:"right", Enter:"ok",
  Escape:"back", Backspace:"back", h:"home", s:"settings", i:"input", "+":"volup", "=":"volup",
  "-":"voldown", m:"mute"};
document.addEventListener("keydown", e => {
  const k = keys[e.key] || keys[e.key.toLowerCase()];
  if (!k || e.metaKey || e.ctrlKey || e.altKey) return;
  e.preventDefault(); press(k);
});
fetch("/inputs").then(async r => {
  const box = document.getElementById("inputs");
  if (!r.ok) { box.textContent = ""; say(await r.text(), true); return; }
  const list = await r.json();
  box.textContent = list.length ? "" : "No inputs reported.";
  for (const i of list) {
    const b = document.createElement("button");
    b.textContent = i.name; if (!i.connected) b.className = "off";
    b.addEventListener("click", () => post("/input?uri=" + encodeURIComponent(i.uri)));
    box.appendChild(b);
  }
}).catch(() => say("The remote stopped. Start it again in Terminal.", true));
</script></body></html>
"""


def make_handler(tv, lan):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body, content_type="text/plain; charset=utf-8"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            # A page on another site could aim requests at this port; it cannot add a custom header
            # without a preflight we never answer, and a rebound DNS name fails the Host check.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return lan or host in ("127.0.0.1", "localhost", "::1")

        def tv_error(self, e):
            if isinstance(e, PermissionError) or isinstance(e, urllib.error.HTTPError) and e.code == 403:
                return self.reply(502, "The TV refused the key. Check TV_PSK against the TV's Pre-Shared Key.")
            if isinstance(e, urllib.error.HTTPError):
                return self.reply(502, f"The TV answered HTTP {e.code}. Is Simple IP control switched on?")
            if isinstance(e, (urllib.error.URLError, OSError)):
                return self.reply(502, f"Can't reach the TV at {tv.base}. Is it on, with IP control switched on?")
            return self.reply(502, f"The TV said no: {e}")

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, "Forbidden")
            if self.path == "/":
                return self.reply(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/inputs":
                try:
                    return self.reply(200, json.dumps(tv.inputs()), "application/json")
                except Exception as e:
                    return self.tv_error(e)
            self.reply(404, "Not found")

        def do_POST(self):
            if not self.allowed() or self.headers.get("X-Remote") != "1":
                return self.reply(403, "Forbidden")
            try:
                if self.path.startswith("/key/") and self.path[5:] in BUTTONS:
                    tv.press(self.path[5:])
                elif self.path.startswith("/input?uri="):
                    tv.switch(urllib.parse.unquote(self.path[len("/input?uri="):]))
                else:
                    return self.reply(404, "Not found")
            except Exception as e:
                return self.tv_error(e)
            self.reply(204, "")

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Browser remote for Sony BRAVIA TVs over IP control.")
    ap.add_argument("--port", type=int, default=8765, help="local port for the page (default 8765)")
    ap.add_argument("--lan", action="store_true", help="serve other devices on the network too")
    ap.add_argument("--no-browser", action="store_true", help="don't open the page")
    args = ap.parse_args()
    host, psk = os.environ.get("TV_HOST"), os.environ.get("TV_PSK")
    if not host or not psk:
        sys.exit("Set TV_HOST and TV_PSK, e.g.  TV_HOST=192.168.1.50 TV_PSK=<key> python3 tools/sony-remote.py\n"
                 "(the key is the TV's Settings > Network & Internet > Home network > IP control > Pre-Shared Key)")
    tv = Tv(host, psk)
    server = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port), make_handler(tv, args.lan))
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Remote for {host} at {url}" + ("  (and on this computer's IP from your phone)" if args.lan else ""))
    print("Ctrl+C to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

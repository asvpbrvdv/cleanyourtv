#!/usr/bin/env python3
"""A small remote for Sony BRAVIA TVs in the browser, over Sony's IP control (no ADB needed).

On the TV, once: Settings > Network & Internet > Home network > IP control. Set Authentication to
"Normal and Pre-Shared Key", choose a Pre-Shared Key and switch Simple IP control on. Then:

    TV_HOST=192.168.1.50 TV_PSK=<key> python3 tools/sony-remote.py         opens http://127.0.0.1:8765
    ... python3 tools/sony-remote.py --lan                                  also serve phones on the Wi-Fi
    ... python3 tools/sony-remote.py --port 9000 --no-browser

Keys: arrows, Enter = OK, Esc or Backspace = Back, H = Home, S = Settings, + / - = volume, M = mute.
The keyboard button turns those letters into typing: what you type goes into the search or text field
open on the TV (appControl setTextForm), arrows still move, Enter is OK and Esc is Back.
Python 3 standard library only. The button codes come from the TV itself (getRemoteControllerInfo),
with Sony's published codes as a fallback, and the input list from getCurrentExternalInputsStatus,
so each HDMI port gets its own button. Power and the mute icon use the system and audio services.

The page only answers on 127.0.0.1 unless --lan is given: anyone who can reach it can press buttons
on the TV without knowing the key.
"""
import argparse
import html
import json
import os
import shlex
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
    "TvPower": "AAAAAQAAAAEAAAAVAw==",
    "VolumeUp": "AAAAAQAAAAEAAAASAw==",
    "VolumeDown": "AAAAAQAAAAEAAAATAw==",
    "Mute": "AAAAAQAAAAEAAAAUAw==",
}

# Page button -> IRCC names to try, in order. The gear button on Google TV BRAVIA remotes sends
# ActionMenu (quick settings); older sets call a similar key Options.
BUTTONS = {
    "up": ["Up"], "down": ["Down"], "left": ["Left"], "right": ["Right"],
    "ok": ["Confirm"], "back": ["Return"], "home": ["Home"],
    "settings": ["ActionMenu", "Options"],
    "volup": ["VolumeUp"], "voldown": ["VolumeDown"], "mute": ["Mute"], "power": ["TvPower", "Power"],
}

IRCC_BODY = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
             's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
             '<u:X_SendIRCC xmlns:u="urn:schemas-sony-com:service:IRCC:1"><IRCCCode>{}</IRCCCode>'
             '</u:X_SendIRCC></s:Body></s:Envelope>')


class TvError(RuntimeError):
    def __init__(self, method, error):
        super().__init__(f"{method}: {error}")
        self.code = error[0] if isinstance(error, list) and error else None


# appControl error when no on-screen keyboard is open on the TV.
NO_TEXT_FIELD = 7


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
            raise TvError(method, reply["error"])
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
        # HDMI-CEC devices (a soundbar, a player) are listed again as extInput:cec entries next to
        # their HDMI port, and choosing those does not switch: the port's own button does.
        return [{"uri": i["uri"], "name": i.get("label") or i.get("title") or i["uri"],
                 "connected": bool(i.get("connection"))}
                for i in items if i.get("uri") and not i["uri"].startswith("extInput:cec")]

    def power(self):
        """Standby when on, on when in standby; IRCC TvPower where the TV won't take setPowerStatus."""
        try:
            on = self.call("system", "getPowerStatus")[0].get("status") == "active"
            self.call("system", "setPowerStatus", [{"status": not on}])
        except RuntimeError:
            self.press("power")

    def muted(self):
        """True or False from the TV's volume information, None when it reports no mute state."""
        result = self.call("audio", "getVolumeInformation")
        states = [v["mute"] for v in (result[0] if result else []) if isinstance(v.get("mute"), bool)]
        return any(states) if states else None

    def text(self):
        """(open, text) for the TV's on-screen keyboard field; open is None when the TV can't say."""
        try:
            result = self.call("appControl", "getTextForm", [{"encKey": ""}], version="1.1")
        except TvError as e:
            return (False, None) if e.code == NO_TEXT_FIELD else (None, None)
        return True, (result[0].get("text", "") if result and isinstance(result[0], dict) else "")

    def type(self, text):
        """Replace the text in the TV's open keyboard field."""
        try:
            self.call("appControl", "setTextForm", [text])
        except TvError as e:
            if e.code == NO_TEXT_FIELD:
                raise RuntimeError("No text field is open on the TV. Select a search or text box first.")
            raise

    def switch(self, uri):
        if not uri.startswith("extInput:"):
            raise RuntimeError("only external inputs can be chosen here")
        self.call("avContent", "setPlayContent", [{"uri": uri}])


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV Remote</title>
<style>
:root{--bg:#0b0c0f;--pad:#1a1c22;--key:#262931;--key-hi:#353945;--text:#eef0f4;--dim:#8a8f9c;--accent:#cfffcf;
 --red:#e5484d;--red-hi:#f2555a;--green:#46c46e}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;
 background:var(--bg);color:var(--text);font:15px/1.3 -apple-system,BlinkMacSystemFont,"Inter",sans-serif}
/* The remote sits in the centre column whether or not the keyboard is open, so the keyboard button
   never moves: the keyboard fills the empty column to its left, or goes below it on narrow screens. */
.app{display:grid;grid-template-columns:1fr minmax(0,268px) 1fr;align-items:start;padding:20px 16px;width:100%}
main{grid-column:2;grid-row:1;width:100%}
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
svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:middle}
button.round{flex:0 0 44px;height:44px;padding:0;border-radius:50%}
button.power{background:var(--red);color:#fff}
button.power:hover{background:var(--red-hi)}
button.kbd.on{background:var(--text);color:var(--bg)}
button.mute.on{background:var(--red);color:#fff}
button.mute.on:hover{background:var(--red-hi)}
#copy{display:block;width:100%;margin:22px 0 0;padding:12px;text-align:left;background:none;
 border:1px solid var(--key);color:var(--dim)}
#copy:hover{background:var(--pad)}
#copy .label{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;letter-spacing:.04em;margin-bottom:6px}
#copy .label svg{width:15px;height:15px}
#copy code{display:block;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere;opacity:.85}
/* phone-style keyboard */
#keyboard{grid-column:1;grid-row:1;justify-self:end;width:100%;max-width:348px;padding-right:28px;margin-top:10px}
#keyboard[hidden]{display:none}
.field{display:flex;align-items:center;gap:8px;background:var(--pad);border-radius:12px;padding:10px 12px;min-height:44px}
.field .dot{flex:0 0 8px;height:8px;border-radius:50%;background:var(--dim)}
.field.live .dot{background:var(--green)}
#typed{flex:1;overflow:hidden;white-space:pre}
#typed .caret{display:inline-block;width:2px;height:1.1em;background:var(--text);vertical-align:-2px;animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.field.idle #typed{color:var(--dim)}
.keys{background:var(--pad);border-radius:16px;padding:8px 4px 6px;margin-top:10px}
.krow{display:flex;gap:5px;justify-content:center;margin:0 0 9px}
.krow button{flex:0 0 calc((100% - 45px)/10);padding:11px 0;border-radius:7px;font-size:16px;background:var(--key-hi)}
.krow button.mod{flex:1 1 0;background:var(--key);font-size:13px}
.krow button.space{flex:4 1 0}
.krow button.mod.on{background:var(--text);color:var(--bg)}
.krow.home{padding:0 5%}
.hint{font-size:12px;color:var(--dim);margin:8px 2px 0;line-height:1.45}
@media (max-width:900px){#keyboard{grid-column:1/-1;grid-row:2;justify-self:center;max-width:340px;padding-right:0;margin-top:24px}}
</style></head><body><div class="app">
<section id="keyboard" hidden aria-label="Keyboard">
 <div class="field idle" id="field"><span class="dot"></span><span id="typed"></span></div>
 <div class="keys" id="keys"></div>
 <p class="hint">Typing goes into the text field open on the TV. Arrows still move on the TV,
 Enter presses OK, Esc is Back.</p>
</section>
<main>
<div class="row"><button class="round power" data-k="power" aria-label="Power"><svg viewBox="0 0 24 24"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg></button><button data-k="home">Home</button><button data-k="settings">Settings</button><button class="round kbd" id="kbd" aria-label="Keyboard" aria-pressed="false"><svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M18 13h.01M10 13h4M7 16h10"/></svg></button></div>
<div class="pad">
 <span></span><button data-k="up" aria-label="Up">&#9650;</button><span></span>
 <button data-k="left" aria-label="Left">&#9664;</button><button class="ok" data-k="ok">OK</button><button data-k="right" aria-label="Right">&#9654;</button>
 <span></span><button data-k="down" aria-label="Down">&#9660;</button><span></span>
</div>
<div class="row"><button data-k="back">Back</button></div>
<div class="row"><button data-k="voldown" aria-label="Volume down">Vol &minus;</button><button class="mute" data-k="mute" aria-label="Mute"></button><button data-k="volup" aria-label="Volume up">Vol +</button></div>
<h2>Inputs</h2><div id="inputs"><span style="color:var(--dim)">Loading&hellip;</span></div>
<div id="status"></div>
<button id="copy" title="Click to copy"><span class="label">Copy and paste into Terminal<svg viewBox="0 0 24 24"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg></span>
<code>__COMMAND__</code></button>
</main></div><script>
const status = document.getElementById("status");
function say(text, err) { status.textContent = text; status.className = err ? "err" : ""; }
async function post(path, body) {
  try {
    const r = await fetch(path, {method: "POST", headers: {"X-Remote": "1"}, body});
    if (!r.ok) say(await r.text(), true); else say("");
    return r.ok;
  } catch (e) { say("The remote stopped. Start it again in Terminal.", true); return false; }
}
const SOUND = '<svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';
const MUTED = '<svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>';
const muteBtn = document.querySelector("button.mute");
function showMute(on) {
  muteBtn.innerHTML = on ? MUTED : SOUND; muteBtn.classList.toggle("on", on);
  muteBtn.setAttribute("aria-label", on ? "Unmute" : "Mute");
}
let muted = false; showMute(false);
// The TV's own answer wins; a TV that reports no mute state keeps the icon's own guess.
async function syncMute() {
  try { const r = await fetch("/state"); const s = await r.json(); if (s.muted !== null) showMute(muted = s.muted); } catch (e) {}
}
async function press(k) {
  if (k === "mute") showMute(muted = !muted);
  await post("/key/" + k);
  if (k === "mute" || k === "volup" || k === "voldown") setTimeout(syncMute, 400);
  if (typing && ["up", "down", "left", "right", "ok", "back"].includes(k)) setTimeout(pollField, 500);
}
syncMute(); window.addEventListener("focus", syncMute);
const copy = document.getElementById("copy"), label = copy.querySelector(".label").firstChild;
copy.addEventListener("click", async () => {
  const text = copy.querySelector("code").textContent;
  try { await navigator.clipboard.writeText(text); } catch (e) {
    const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t);
    t.select(); document.execCommand("copy"); t.remove();
  }
  label.textContent = "Copied"; setTimeout(() => label.textContent = "Copy and paste into Terminal", 1500);
});
document.querySelectorAll("[data-k]").forEach(b => b.addEventListener("click", () => press(b.dataset.k)));

// Keyboard mode. The TV's field is the truth: while nothing is typed, the page reads it about once a
// second (getTextForm), which is also how it notices that a search or text field has opened.
// Each keystroke sends the whole text (setTextForm replaces the field), one request at a time.
const kbd = document.getElementById("kbd"), panel = document.getElementById("keyboard");
const field = document.getElementById("field"), typed = document.getElementById("typed");
let typing = false, text = "", live = null, lastKey = 0, sending = false, sent = null, pollTimer = null;
function render() {
  field.classList.toggle("live", live === true); field.classList.toggle("idle", live !== true);
  typed.innerHTML = "";
  if (live === false) { typed.textContent = "No text field open on the TV"; return; }
  typed.textContent = text;
  const c = document.createElement("span"); c.className = "caret"; typed.appendChild(c);
  typed.scrollLeft = typed.scrollWidth;  // long searches keep their end in view
}
async function pollField() {
  if (!typing || sending || Date.now() - lastKey < 1500) return;
  try {
    const s = await (await fetch("/text")).json();
    if (Date.now() - lastKey < 1500 || sending) return;
    live = s.active;
    if (s.active && typeof s.text === "string") text = sent = s.text;
    render();
  } catch (e) {}
}
async function flush() {
  if (sending) return;
  sending = true;
  while (sent !== text) {
    const now = text;
    const ok = await post("/text", JSON.stringify({text: now}));
    if (!ok) { live = false; render(); break; }
    sent = now; live = true; render();
  }
  sending = false;
}
function type(s) { text += s; lastKey = Date.now(); render(); flush(); }
function erase() { text = Array.from(text).slice(0, -1).join(""); lastKey = Date.now(); render(); flush(); }
function setTyping(on) {
  typing = on; panel.hidden = !on; kbd.classList.toggle("on", on); kbd.setAttribute("aria-pressed", on);
  clearInterval(pollTimer);
  if (on) { live = null; render(); pollField(); pollTimer = setInterval(pollField, 1000); }
}
kbd.addEventListener("click", () => setTyping(!typing));

const LAYOUTS = {
  abc: ["qwertyuiop", "asdfghjkl", ["shift", ..."zxcvbnm", "del"], ["123", "space", "return"]],
  num: ["1234567890", "-/:;()$&@\\"", ["#+=", ..."._,?!'", "del"], ["ABC", "space", "return"]],
  sym: ["[]{}#%^*+=", "_\\\\|~<>€£¥•", ["123", ..."._,?!'", "del"], ["ABC", "space", "return"]],
};
const LABELS = {shift: "⇧", del: "⌫", space: "space", "return": "return"};
let layout = "abc", shift = false;
const keysBox = document.getElementById("keys");
function drawKeys() {
  keysBox.innerHTML = "";
  LAYOUTS[layout].forEach((row, i) => {
    const r = document.createElement("div"); r.className = "krow" + (i === 1 && layout === "abc" ? " home" : "");
    for (const k of Array.from(row)) {
      const b = document.createElement("button"); b.type = "button";
      const special = k.length > 1;
      b.className = special ? "mod" + (k === "space" ? " space" : "") + (k === "shift" && shift ? " on" : "") : "";
      b.textContent = LABELS[k] || (shift && !special ? k.toUpperCase() : k);
      b.addEventListener("click", () => tap(k));
      r.appendChild(b);
    }
    keysBox.appendChild(r);
  });
}
function tap(k) {
  if (k === "shift") { shift = !shift; return drawKeys(); }
  if (k === "123") { layout = "num"; return drawKeys(); }
  if (k === "ABC") { layout = "abc"; return drawKeys(); }
  if (k === "#+=") { layout = "sym"; return drawKeys(); }
  if (k === "del") return erase();
  if (k === "return") return press("ok");
  type(k === "space" ? " " : shift ? k.toUpperCase() : k);
  if (shift) { shift = false; drawKeys(); }
}
drawKeys();

const keys = {ArrowUp:"up", ArrowDown:"down", ArrowLeft:"left", ArrowRight:"right", Enter:"ok",
  Escape:"back", Backspace:"back", h:"home", s:"settings", "+":"volup", "=":"volup",
  "-":"voldown", m:"mute"};
const typingKeys = {ArrowUp:"up", ArrowDown:"down", ArrowLeft:"left", ArrowRight:"right", Enter:"ok", Escape:"back"};
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (typing) {
    if (typingKeys[e.key]) { e.preventDefault(); return press(typingKeys[e.key]); }
    if (e.key === "Backspace") { e.preventDefault(); return erase(); }
    if (e.key.length === 1) { e.preventDefault(); return type(e.key); }
    return;
  }
  const k = keys[e.key] || keys[e.key.toLowerCase()];
  if (!k) return;
  e.preventDefault(); press(k);
});
document.addEventListener("paste", e => {
  if (!typing) return;
  e.preventDefault(); type((e.clipboardData.getData("text") || "").replace(/\\s+/g, " "));
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


def make_handler(tv, lan, command=""):
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
            if isinstance(e, TvError):
                return self.reply(502, f"The TV said no: {e}")
            return self.reply(502, str(e))

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, "Forbidden")
            if self.path == "/":
                return self.reply(200, PAGE.replace("__COMMAND__", html.escape(command)), "text/html; charset=utf-8")
            if self.path == "/text":
                try:
                    active, text = tv.text()
                except Exception:
                    active, text = None, None
                return self.reply(200, json.dumps({"active": active, "text": text}), "application/json")
            if self.path == "/state":
                try:
                    return self.reply(200, json.dumps({"muted": tv.muted()}), "application/json")
                except Exception:
                    return self.reply(200, json.dumps({"muted": None}), "application/json")
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
                if self.path == "/key/power":
                    tv.power()
                elif self.path.startswith("/key/") and self.path[5:] in BUTTONS:
                    tv.press(self.path[5:])
                elif self.path == "/text":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > 4096:
                        return self.reply(413, "Too much text")
                    text = json.loads(self.rfile.read(length) or b"{}").get("text")
                    if not isinstance(text, str):
                        return self.reply(400, "Expected {\"text\": ...}")
                    tv.type(text)
                elif self.path.startswith("/input?uri="):
                    tv.switch(urllib.parse.unquote(self.path[len("/input?uri="):]))
                else:
                    return self.reply(404, "Not found")
            except Exception as e:
                return self.tv_error(e)
            self.reply(204, "")

    return Handler


def start_command(host, psk, args):
    """The line that starts this remote again, shown on the page to copy."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    home = os.path.expanduser("~")
    if repo.startswith(home + os.sep):
        repo = "~/" + shlex.quote(repo[len(home) + 1:])
    else:
        repo = shlex.quote(repo)
    flags = (" --lan" if args.lan else "") + (f" --port {args.port}" if args.port != 8765 else "")
    return (f"cd {repo} && TV_HOST={shlex.quote(host)} TV_PSK={shlex.quote(psk)} "
            f"python3 tools/sony-remote.py{flags}")


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
    server = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port),
                                 make_handler(tv, args.lan, start_command(host, psk, args)))
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

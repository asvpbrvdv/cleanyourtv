#!/usr/bin/env python3
"""A small remote for Sony BRAVIA TVs in the browser, over Sony's IP control (no ADB needed).

On the TV, once: Settings > Network & Internet > Home network > IP control. Set Authentication to
"Normal and Pre-Shared Key", choose a Pre-Shared Key and switch Simple IP control on. Then:

    TV_HOST=192.168.1.50 TV_PSK=<key> python3 tools/sony-remote.py         opens http://127.0.0.1:8765
    ... python3 tools/sony-remote.py --lan                                  also serve phones on the Wi-Fi
    ... python3 tools/sony-remote.py --port 9000 --no-browser
    ... python3 tools/sony-remote.py --make-app                             Mac: ~/Applications/TV Remote.app

The page is laid out for one hand on a phone: a touchpad (each short swipe is one arrow press, a tap is
OK, with a Buttons switch back to the arrow ring), a volume strip you drag to set the TV's level, then
the apps and inputs and Back, Home, Play/Pause and Type at the bottom. When the TV is in standby the
page shows only power and the apps and inputs, and choosing one turns the TV on first.

Keys: arrows, Enter = OK, Esc or Backspace = Back, H = Home, S = Settings, + / - = volume, M = mute,
P = play/pause.
The keyboard button turns those letters into typing: what you type goes into the search or text field
open on the TV (appControl setTextForm), arrows still move, Enter is OK and Esc is Back.
Python 3 standard library only. The button codes come from the TV itself (getRemoteControllerInfo),
with Sony's published codes as a fallback, and the input list from getCurrentExternalInputsStatus,
so each HDMI port gets its own button. Power and the mute icon use the system and audio services.
Above the inputs, buttons open your most used apps by name (appControl getApplicationList and
setActiveApp): YouTube and Pluto TV unless TV_APPS lists others, e.g. TV_APPS="YouTube,Pluto TV,Plex".
An app the TV doesn't have is left out.

--make-app writes a one-click Mac app with these settings: it reopens the page when the remote is
running and starts it in the background when it isn't, so closing the tab or Terminal costs nothing.

GET /health answers {"status": "ok"} (HTTP 200) when the TV takes a keyed call, else HTTP 503 with
the reason, for uptime monitors such as Uptime Kuma.

The page only answers on 127.0.0.1 unless --lan is given: anyone who can reach it can press buttons
on the TV without knowing the key.
"""
import argparse
import json
import os
import plistlib
import shlex
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
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
    "Play": "AAAAAgAAAJcAAAAaAw==",
    "Pause": "AAAAAgAAAJcAAAAZAw==",
}

# Page button -> IRCC names to try, in order. The gear button on Google TV BRAVIA remotes sends
# ActionMenu (quick settings); older sets call a similar key Options.
BUTTONS = {
    "up": ["Up"], "down": ["Down"], "left": ["Left"], "right": ["Right"],
    "ok": ["Confirm"], "back": ["Return"], "home": ["Home"],
    "settings": ["ActionMenu", "Options"],
    "volup": ["VolumeUp"], "voldown": ["VolumeDown"], "mute": ["Mute"], "power": ["TvPower", "Power"],
    "play": ["Play"], "pause": ["Pause"],
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

    def power_state(self):
        """"active" or "standby", or None when the TV can't say."""
        try:
            status = self.call("system", "getPowerStatus")[0].get("status")
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError, AttributeError):
            return None
        return status if status in ("active", "standby") else None

    def power_on(self):
        """On, and nothing else: unlike power(), never a toggle, so a late tap can't turn it off."""
        self.call("system", "setPowerStatus", [{"status": True}])

    def sound(self):
        """Mute and volume from the TV's volume information: the speaker's when listed, else the first
        output's. Each is None when the TV doesn't report it."""
        result = self.call("audio", "getVolumeInformation")
        outputs = [v for v in (result[0] if result else []) if isinstance(v, dict)]
        states = [v["mute"] for v in outputs if isinstance(v.get("mute"), bool)]
        levels = [v for v in outputs if isinstance(v.get("volume"), int) and not isinstance(v["volume"], bool)]
        main = next((v for v in levels if v.get("target") == "speaker"), levels[0] if levels else {})
        top = main.get("maxVolume")
        return {"muted": any(states) if states else None, "volume": main.get("volume"),
                "maxVolume": top if isinstance(top, int) and top > 0 else None, "target": main.get("target")}

    def muted(self):
        """True or False from the TV's volume information, None when it reports no mute state."""
        return self.sound()["muted"]

    def set_volume(self, level):
        """Set the volume to level, kept within what the TV says it allows (0 to 100 if it doesn't)."""
        now = self.sound()
        if now["volume"] is None:
            raise RuntimeError("The TV doesn't report its volume, so it can't be set to a level.")
        level = max(0, min(int(level), now["maxVolume"] or 100))
        self.call("audio", "setAudioVolume", [{"target": now["target"] or "", "volume": str(level)}])
        return level

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

    def app_list(self):
        """Every app the TV can open, as {title: uri}, read from the TV each time."""
        result = self.call("appControl", "getApplicationList")
        return {a["title"]: a["uri"] for a in (result[0] if result else [])
                if isinstance(a, dict) and a.get("title") and a.get("uri")}

    def apps(self, wanted):
        """The wanted apps the TV has, in the order asked, matched by title ignoring case."""
        listed = {t.casefold(): (t, u) for t, u in self.app_list().items()}
        found = [listed.get(w.casefold()) for w in wanted]
        return [{"name": t, "uri": u} for t, u in filter(None, found)]

    def launch(self, uri):
        # Only an app the TV itself lists, so the page can't be used to send it any other URI.
        if uri not in self.app_list().values():
            raise RuntimeError("the TV doesn't list that app")
        self.call("appControl", "setActiveApp", [{"uri": uri}])

    def switch(self, uri):
        if not uri.startswith("extInput:"):
            raise RuntimeError("only external inputs can be chosen here")
        self.call("avContent", "setPlayContent", [{"uri": uri}])


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TV Remote</title>
<link rel="icon" type="image/png" href="/icon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<script>
// Before first paint, so the page never flashes the other theme: the viewer's own choice, else the system's.
(function () {
  var t = null;
  try { t = localStorage.getItem("theme"); } catch (e) {}
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  document.documentElement.dataset.theme = t;
})();
</script>
<style>
:root{color-scheme:dark;--bg:#0b0c0f;--pad:#1a1c22;--key:#262931;--key-hi:#353945;--text:#eef0f4;--dim:#8a8f9c;
 --accent:#cfffcf;--red:#e5484d;--red-hi:#f2555a;--green:#46c46e;--err:#ff8a8a;--line:#262931;
 --letter:#353945;--mod:#262931;--ok:#353945;--ok-hi:#454a58;--shadow:none;--pad-a:#1d2027;--pad-b:#15171c}
:root[data-theme="light"]{color-scheme:light;--bg:#f2f3f6;--pad:#e2e5ea;--key:#ffffff;--key-hi:#eceef2;
 --text:#15181e;--dim:#6b7180;--red:#e0393f;--red-hi:#ec474d;--green:#239a4c;--err:#c8282e;--line:#d3d7de;
 --letter:#ffffff;--mod:#c5cad3;--ok:#ffffff;--ok-hi:#eceef2;--shadow:0 1px 2px rgba(21,24,30,.12);
 --pad-a:#e8ebef;--pad-b:#dde1e7}
*{box-sizing:border-box}
[hidden]{display:none!important}
/* Quick taps are button presses, not iOS double-tap zoom; pinch zoom still works. */
html,button{touch-action:manipulation}
body{margin:0;min-height:100vh;display:flex;justify-content:center;align-items:flex-start;
 background:var(--bg);color:var(--text);font:15px/1.3 -apple-system,BlinkMacSystemFont,"Inter",sans-serif}
/* The remote sits in the centre column whether or not the keyboard is open, so the keyboard button
   never moves: the keyboard fills the empty column to its left, or goes below it on narrow screens.
   Top to bottom by how often the thumb needs it: the touchpad in the middle, the apps and the everyday
   buttons at the bottom, where one hand reaches. */
.app{display:grid;grid-template-columns:1fr minmax(0,340px) 1fr;align-items:start;padding:16px;width:100%}
main{grid-column:2;grid-row:1;width:100%;display:flex;flex-direction:column;gap:12px}
button{appearance:none;border:0;border-radius:14px;background:var(--key);color:var(--text);
 font:inherit;padding:12px 0;cursor:pointer;user-select:none;-webkit-tap-highlight-color:transparent}
button{box-shadow:var(--shadow)}
button:hover{background:var(--key-hi)}
button:active{transform:scale(.96)}
button:focus-visible,#touch:focus-visible,#vol:focus-visible{outline:2px solid var(--text);outline-offset:2px}
svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;vertical-align:middle;flex:none}
.top{display:flex;align-items:center;gap:8px}
#tvstate{flex:1;display:flex;align-items:center;gap:8px;font-size:13px;color:var(--dim)}
#tvstate .dot{width:8px;height:8px;border-radius:50%;background:var(--dim)}
#tvstate.on .dot{background:var(--green)}
button.round{flex:0 0 40px;width:40px;height:40px;padding:0;border-radius:50%;display:grid;place-items:center}
button.power{background:var(--red);color:#fff}
button.power:hover{background:var(--red-hi)}
#theme{color:var(--dim)}
#theme:hover{color:var(--text)}
#theme svg{width:18px;height:18px}
/* Touchpad: each short swipe is one step on the TV, a tap is OK. */
#touch{position:relative;height:clamp(200px,40vh,320px);border-radius:24px;overflow:hidden;touch-action:none;
 cursor:crosshair;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;
 background:radial-gradient(circle at 50% 45%,var(--pad-a),var(--pad-b));border:1px solid var(--line)}
#touch canvas{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#touch .hint{position:absolute;inset:auto 0 14px;text-align:center;font-size:12px;color:var(--dim);pointer-events:none;padding:0 16px}
#flash{position:absolute;left:50%;top:44%;transform:translate(-50%,-50%);font-size:15px;font-weight:600;
 display:flex;flex-direction:column;align-items:center;gap:6px;pointer-events:none;opacity:0;transition:opacity .35s}
#flash.show{opacity:1;transition:none}
#flash svg{width:34px;height:34px;stroke-width:2.4}
.swap{position:absolute;top:8px;right:8px;z-index:1;padding:6px 10px;font-size:12px;color:var(--dim);
 background:transparent;box-shadow:inset 0 0 0 1px var(--line);border-radius:999px}
.swap:hover{color:var(--text);background:transparent}
/* The arrow ring, for anyone who'd rather press buttons. */
#ring{position:relative;height:clamp(200px,40vh,320px);border-radius:24px;background:var(--pad);display:grid;place-items:center}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;width:min(230px,80%);aspect-ratio:1}
.pad button{border-radius:50%;font-size:20px;padding:0}
.pad .ok{background:var(--ok);font-size:15px;font-weight:600}
.pad .ok:hover{background:var(--ok-hi)}
/* Volume: drag along the strip; it never jumps to where you touch. */
#vol{display:flex;align-items:center;gap:10px;background:var(--pad);border-radius:16px;padding:6px 14px 6px 6px;
 touch-action:none;cursor:ew-resize;user-select:none;-webkit-user-select:none}
#vol button.mute{width:40px;height:40px;padding:0;border-radius:12px;display:grid;place-items:center;flex:none}
button.mute.on{background:var(--red);color:#fff}
button.mute.on:hover{background:var(--red-hi)}
.track{flex:1;position:relative;height:6px;border-radius:3px;background:var(--line)}
#fill{position:absolute;inset:0 auto 0 0;width:0;border-radius:3px;background:var(--text)}
#vol.muted #fill{background:var(--dim)}
#vol .num{min-width:2.2em;text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
#vol .step{font-size:12px;color:var(--dim)}
h2{font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin:2px 2px -4px}
#watch{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
#watch .note{grid-column:1/-1;color:var(--dim);font-size:13px}
#watch button{padding:11px 4px;font-size:14px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* App buttons in their brand's two colours, the same in both themes. */
#watch button.brand{background:var(--brand-bg);color:var(--brand-fg)}
#watch button.brand:hover{background:var(--brand-bg);filter:brightness(.9)}
#watch button.input{font-weight:500}
#watch button.off{color:var(--dim)}
.thumb{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.thumb button{display:flex;flex-direction:column;align-items:center;gap:4px;padding:11px 0 9px;font-size:12px;color:var(--dim)}
.thumb button svg{color:var(--text)}
button.play{background:var(--text);color:var(--bg)}
button.play svg{color:var(--bg)}
button.play:hover{background:var(--text);opacity:.9}
button.kbd.on{box-shadow:inset 0 0 0 2px var(--text)}
#offview{display:flex;flex-direction:column;align-items:center;gap:14px;padding:32px 16px;border-radius:24px;background:var(--pad);text-align:center}
#offview p{margin:0;color:var(--dim);font-size:13px;max-width:28ch}
#wake{width:96px;height:96px;border-radius:50%;padding:0;display:grid;place-items:center;background:var(--red);color:#fff}
#wake:hover{background:var(--red-hi)}
#wake svg{width:40px;height:40px}
#status{min-height:1.3em;font-size:13px;color:var(--dim);text-align:center}
#status.err{color:var(--err)}
/* phone-style keyboard */
#keyboard{grid-column:1;grid-row:1;justify-self:end;width:100%;max-width:348px;padding-right:28px;margin-top:52px}
.field{display:flex;align-items:center;gap:8px;background:var(--pad);border-radius:12px;padding:10px 12px;min-height:44px}
.field .dot{flex:0 0 8px;height:8px;border-radius:50%;background:var(--dim)}
.field.live .dot{background:var(--green)}
#typed{flex:1;overflow:hidden;white-space:pre}
#typed .caret{display:inline-block;width:2px;height:1.1em;background:var(--text);vertical-align:-2px;animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}
.field.idle #typed{color:var(--dim)}
.keys{background:var(--pad);border-radius:16px;padding:8px 4px 6px;margin-top:10px}
.krow{display:flex;gap:5px;justify-content:center;margin:0 0 9px}
.krow button{flex:0 0 calc((100% - 45px)/10);padding:11px 0;border-radius:7px;font-size:16px;background:var(--letter)}
.krow button.mod{flex:1 1 0;background:var(--mod);font-size:13px}
.krow button:hover{background:var(--key-hi)}
.krow button.space{flex:4 1 0}
.krow button.mod.on{background:var(--text);color:var(--bg)}
.krow.home{padding:0 5%}
.hint-k{font-size:12px;color:var(--dim);margin:8px 2px 0;line-height:1.45}
@media (max-width:900px){#keyboard{grid-column:2;grid-row:2;justify-self:center;max-width:340px;padding-right:0;margin-top:16px}}
@media (prefers-reduced-motion:reduce){button:active{transform:none}#flash{transition:none}}
</style></head><body>
<div class="app">
<section id="keyboard" hidden aria-label="Keyboard">
 <div class="field idle" id="field"><span class="dot"></span><span id="typed"></span></div>
 <div class="keys" id="keys"></div>
 <p class="hint-k">Typing goes into the text field open on the TV. Arrows still move on the TV,
 Enter presses OK, Esc is Back.</p>
</section>
<main>
<div class="top">
 <div id="tvstate"><span class="dot"></span><span id="tvword">TV</span></div>
 <button class="round" id="theme" aria-label="Switch to light mode"></button>
 <button class="round" data-k="settings" aria-label="Settings"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button>
 <button class="round power" id="power" aria-label="Power"><svg viewBox="0 0 24 24"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg></button>
</div>
<div id="onview">
 <div id="touch" tabindex="0" aria-label="Touchpad: swipe to move, tap for OK">
  <canvas id="trace"></canvas>
  <button class="swap" id="toRing">Buttons</button>
  <div id="flash"></div>
  <div class="hint">Swipe to move &middot; tap for OK</div>
 </div>
 <div id="ring" hidden>
  <button class="swap" id="toTouch">Touchpad</button>
  <div class="pad">
   <span></span><button data-k="up" aria-label="Up">&#9650;</button><span></span>
   <button data-k="left" aria-label="Left">&#9664;</button><button class="ok" data-k="ok">OK</button><button data-k="right" aria-label="Right">&#9654;</button>
   <span></span><button data-k="down" aria-label="Down">&#9660;</button><span></span>
  </div>
 </div>
</div>
<div id="offview" hidden>
 <button id="wake" aria-label="Turn the TV on"><svg viewBox="0 0 24 24"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg></button>
 <p>The TV is off. Press power, or pick an app or input below to turn it on and go straight there.</p>
</div>
<div id="vol" tabindex="0" aria-label="Volume: drag left or right">
 <button class="mute" data-k="mute" aria-label="Mute"></button>
 <div class="track"><div id="fill"></div></div>
 <span class="num" id="num">&middot;</span>
</div>
<h2>Watch</h2>
<div id="watch"><span class="note">Loading&hellip;</span></div>
<div class="thumb" id="thumb">
 <button data-k="back"><svg viewBox="0 0 24 24"><path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/></svg>Back</button>
 <button data-k="home"><svg viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>Home</button>
 <button class="play" id="play" aria-label="Play or pause"><svg viewBox="0 0 24 24"><path d="M4 5v14l8-7z"/><path d="M16 5v14"/><path d="M20 5v14"/></svg>Play/Pause</button>
 <button class="kbd" id="kbd" aria-label="Keyboard" aria-pressed="false"><svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M6 13h.01M18 13h.01M10 13h4M7 16h10"/></svg>Type</button>
</div>
<div id="status"></div>
</main></div><script>
const $ = id => document.getElementById(id);
const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
const MOON = '<svg viewBox="0 0 24 24"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/></svg>';
const themeBtn = $("theme");
function showTheme(t) {
  document.documentElement.dataset.theme = t;
  themeBtn.innerHTML = t === "dark" ? SUN : MOON;
  themeBtn.setAttribute("aria-label", t === "dark" ? "Switch to light mode" : "Switch to dark mode");
}
showTheme(document.documentElement.dataset.theme);
themeBtn.addEventListener("click", () => {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  try { localStorage.setItem("theme", t); } catch (e) {}
  showTheme(t);
});
// Until the viewer picks one, follow the system as it changes (macOS Auto appearance).
matchMedia("(prefers-color-scheme: light)").addEventListener("change", e => {
  let chosen = null;
  try { chosen = localStorage.getItem("theme"); } catch (err) {}
  if (!chosen) showTheme(e.matches ? "light" : "dark");
});
const status = $("status");
function say(text, err) { status.textContent = text; status.className = err ? "err" : ""; }
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function post(path, body) {
  try {
    const r = await fetch(path, {method: "POST", headers: {"X-Remote": "1"}, body});
    if (!r.ok) say(await r.text(), true); else say("");
    return r.ok;
  } catch (e) { say("The remote stopped. Start it again in Terminal.", true); return false; }
}
// Key presses go to the TV one at a time and in order, so a fast swipe can't arrive shuffled.
// A backlog is dropped rather than replayed long after the finger has stopped.
const queue = []; let busy = false;
function send(path) {
  if (queue.length >= 6) return;
  queue.push(path); if (!busy) drain();
}
async function drain() {
  busy = true;
  while (queue.length) await post(queue.shift());
  busy = false;
}
const SOUND = '<svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>';
const MUTED = '<svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>';
const muteBtn = document.querySelector("button.mute");
function showMute(on) {
  muteBtn.innerHTML = on ? MUTED : SOUND; muteBtn.classList.toggle("on", on);
  muteBtn.setAttribute("aria-label", on ? "Unmute" : "Mute");
  $("vol").classList.toggle("muted", on);
}
let muted = false; showMute(false);

// The TV's state: power, volume and mute, read when the page opens, every few seconds while it's in
// view, and just after a change. The TV's own answer wins; what it doesn't report keeps the guess.
let level = null, maxLevel = 100, tvOff = false, volTouched = 0, dragging = false;
function showLevel() {
  $("num").textContent = level === null ? "" : level;
  $("fill").style.width = level === null ? "0" : Math.min(100, level / maxLevel * 100) + "%";
}
function showPower(power) {
  tvOff = power === "standby";
  $("tvstate").classList.toggle("on", power === "active");
  $("tvword").textContent = power === "active" ? "TV on" : tvOff ? "TV off" : "TV";
  $("onview").hidden = tvOff; $("offview").hidden = !tvOff;
  $("vol").hidden = tvOff; $("thumb").hidden = tvOff; $("power").hidden = tvOff;
}
async function syncState() {
  try {
    const s = await (await fetch("/state")).json();
    if (s.muted !== null) showMute(muted = s.muted);
    if (Number.isInteger(s.maxVolume) && s.maxVolume > 0) maxLevel = s.maxVolume;
    if (Number.isInteger(s.volume) && !dragging && Date.now() - volTouched > 2000) { level = s.volume; showLevel(); }
    showPower(s.power);
  } catch (e) {}
}
syncState(); window.addEventListener("focus", syncState);
setInterval(() => { if (!document.hidden) syncState(); }, 5000);

function press(k) {
  if (k === "mute") showMute(muted = !muted);
  if (k === "home") nextPlay = "pause";
  send("/key/" + k);
  if (k === "mute" || k === "volup" || k === "voldown") setTimeout(syncState, 500);
  if (typing && ["up", "down", "left", "right", "ok", "back"].includes(k)) setTimeout(pollField, 500);
}
document.querySelectorAll("[data-k]").forEach(b => b.addEventListener("click", () => press(b.dataset.k)));

// The TV takes Play and Pause as two keys, so the button sends them in turn: Pause first, since
// you're usually watching when you reach for it. A tap that doesn't take, the next one fixes.
let nextPlay = "pause";
$("play").addEventListener("click", () => { press(nextPlay); nextPlay = nextPlay === "pause" ? "play" : "pause"; });

// Power. Off, the page shrinks to the power button and the apps, and an app turns the TV on first.
$("power").addEventListener("click", async () => {
  await post("/key/power"); setTimeout(syncState, 1500); setTimeout(syncState, 4000);
});
$("wake").addEventListener("click", async () => {
  if (await post("/power/on")) { showPower("active"); setTimeout(syncState, 3000); }
});
async function go(path) {
  nextPlay = "pause";
  if (!tvOff) return post(path);
  say("Turning the TV on…");
  if (!await post("/power/on")) return;
  showPower("active");
  await sleep(3000);
  if (!await post(path)) { await sleep(2500); await post(path); }  // still waking up: once more
  syncState();
}

// Touchpad: every STEP pixels of travel is one press, in the direction of the larger move; a short
// touch that hardly moves is OK. A trail follows the finger and the step shows in the middle.
const touch = $("touch"), cv = $("trace"), ctx = cv.getContext("2d"), flash = $("flash");
const STEP = 40;
const ARROWS = {up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', left: '<path d="m15 6-6 6 6 6"/>',
  right: '<path d="m9 6 6 6-6 6"/>', ok: '<circle cx="12" cy="12" r="6"/>'};
let start = null, origin = null, lastDir = null, steps = 0, pts = [], fadeRaf = 0, flashTimer = 0;
function showStep(k, n) {
  flash.innerHTML = '<svg viewBox="0 0 24 24">' + ARROWS[k] + '</svg><span></span>';
  flash.lastChild.textContent = (k === "ok" ? "OK" : k[0].toUpperCase() + k.slice(1)) + (n > 1 ? " ×" + n : "");
  flash.classList.add("show"); clearTimeout(flashTimer);
  flashTimer = setTimeout(() => flash.classList.remove("show"), 150);
  if (navigator.vibrate) navigator.vibrate(8);
}
function step(k, n) { showStep(k, n); press(k); }
function sizeCanvas() {
  const r = touch.getBoundingClientRect(), d = window.devicePixelRatio || 1;
  cv.width = r.width * d; cv.height = r.height * d; ctx.setTransform(d, 0, 0, d, 0, 0);
}
function draw(alpha) {
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue("--text");
  ctx.lineCap = "round";
  for (let i = 1; i < pts.length; i++) {
    ctx.globalAlpha = alpha * (i / pts.length) * 0.5; ctx.lineWidth = 2 + 6 * (i / pts.length);
    ctx.beginPath(); ctx.moveTo(pts[i - 1].x, pts[i - 1].y); ctx.lineTo(pts[i].x, pts[i].y); ctx.stroke();
  }
  ctx.globalAlpha = 1;
}
function at(e) { const r = touch.getBoundingClientRect(); return {x: e.clientX - r.left, y: e.clientY - r.top}; }
touch.addEventListener("pointerdown", e => {
  if (e.target.closest(".swap")) return;
  sizeCanvas(); cancelAnimationFrame(fadeRaf);
  touch.setPointerCapture(e.pointerId);
  const p = at(e);
  start = {x: p.x, y: p.y, t: performance.now()}; origin = p; lastDir = null; steps = 0; pts = [p];
});
touch.addEventListener("pointermove", e => {
  if (!start) return;
  const p = at(e); pts.push(p); if (pts.length > 40) pts.shift(); draw(1);
  const dx = p.x - origin.x, dy = p.y - origin.y;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < STEP) return;
  const k = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
  steps = k === lastDir ? steps + 1 : 1; lastDir = k; origin = p;
  step(k, steps);
});
function lift(e) {
  if (!start) return;
  const p = at(e);
  if (!lastDir && Math.hypot(p.x - start.x, p.y - start.y) < 12 && performance.now() - start.t < 400) step("ok", 1);
  start = null;
  let a = 1; (function fade() { a -= 0.06; draw(Math.max(a, 0)); if (a > 0) fadeRaf = requestAnimationFrame(fade); })();
}
touch.addEventListener("pointerup", lift);
touch.addEventListener("pointercancel", lift);

// Touchpad or arrow buttons, remembered on this phone.
function usePad(ring) {
  $("touch").hidden = ring; $("ring").hidden = !ring;
  try { localStorage.setItem("pad", ring ? "buttons" : "touch"); } catch (e) {}
}
let padPref = null; try { padPref = localStorage.getItem("pad"); } catch (e) {}
usePad(padPref === "buttons");
$("toRing").addEventListener("click", () => usePad(true));
$("toTouch").addEventListener("click", () => usePad(false));

// Volume strip: drag sets the TV's level directly, one step every VSTEP pixels from where the finger
// started, sending only the newest level while one is on its way. A TV that doesn't report its
// level gets Volume up and down presses instead.
const vol = $("vol"), VSTEP = 12;
let vx = 0, vBase = 0, vDone = 0, want = null, sentLevel = null, vSending = false;
async function sendLevel() {
  if (vSending) return; vSending = true;
  while (want !== null && want !== sentLevel) {
    const v = want;
    if (!await post("/volume", JSON.stringify({level: v}))) break;
    sentLevel = v;
  }
  vSending = false;
}
function setLevel(v) {
  v = Math.max(0, Math.min(maxLevel, v));
  if (v === level) return;
  level = v; showLevel(); volTouched = Date.now();
  if (muted) showMute(muted = false);  // the TV unmutes when its volume changes
  want = v; sendLevel();
}
vol.addEventListener("pointerdown", e => {
  if (e.target.closest("button")) return;
  vol.setPointerCapture(e.pointerId); dragging = true; vx = e.clientX; vBase = level; vDone = 0;
});
vol.addEventListener("pointermove", e => {
  if (!dragging) return;
  const n = Math.trunc((e.clientX - vx) / VSTEP);
  if (n === vDone) return;
  if (vBase === null) { for (; vDone < n; vDone++) press("volup"); for (; vDone > n; vDone--) press("voldown"); return; }
  vDone = n; setLevel(vBase + n);
});
["pointerup", "pointercancel"].forEach(t => vol.addEventListener(t, () => { dragging = false; volTouched = Date.now(); }));
function volStep(d) { if (level === null) press(d > 0 ? "volup" : "voldown"); else setLevel(level + d); }
vol.addEventListener("keydown", e => {
  if (typing) return;
  const d = {ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1}[e.key];
  if (d) { e.preventDefault(); e.stopPropagation(); volStep(d); }
});

// Keyboard mode. The TV's field is the truth: while nothing is typed, the page reads it about once a
// second (getTextForm), which is also how it notices that a search or text field has opened.
// Each keystroke sends the whole text (setTextForm replaces the field), one request at a time.
const kbd = $("kbd"), panel = $("keyboard");
const field = $("field"), typed = $("typed");
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
  if (on) {
    live = null; render(); pollField(); pollTimer = setInterval(pollField, 1000);
    if (matchMedia("(max-width:900px)").matches) panel.scrollIntoView({behavior: "smooth", block: "nearest"});
  }
}
kbd.addEventListener("click", () => setTyping(!typing));

const LAYOUTS = {
  abc: ["qwertyuiop", "asdfghjkl", ["shift", ..."zxcvbnm", "del"], ["123", "space", "return"]],
  num: ["1234567890", "-/:;()$&@\\"", ["#+=", ..."._,?!'", "del"], ["ABC", "space", "return"]],
  sym: ["[]{}#%^*+=", "_\\\\|~<>€£¥•", ["123", ..."._,?!'", "del"], ["ABC", "space", "return"]],
};
const LABELS = {shift: "⇧", del: "⌫", space: "space", "return": "return"};
let layout = "abc", shift = false;
const keysBox = $("keys");
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
  if (e.key === "p" || e.key === "P") { e.preventDefault(); return $("play").click(); }
  // Enter and Space on a focused button press that button, not OK.
  if ((e.key === "Enter" || e.key === " ") && e.target.closest("button")) return;
  const k = keys[e.key] || keys[e.key.toLowerCase()];
  if (!k) return;
  e.preventDefault();
  if (["up", "down", "left", "right", "ok"].includes(k)) step(k, 1); else press(k);
});
document.addEventListener("paste", e => {
  if (!typing) return;
  e.preventDefault(); type((e.clipboardData.getData("text") || "").replace(/\\s+/g, " "));
});

// Apps first, then inputs, in one block near the thumb. Background and text colour per app, by its
// name on the TV (lower case).
const BRANDS = {"youtube": ["#ff0000", "#ffffff"], "pluto tv": ["#ffe500", "#000000"]};
const watch = $("watch");
function note(msg) { const n = document.createElement("span"); n.className = "note"; n.textContent = msg; return n; }
async function list(path) {
  try { const r = await fetch(path); return r.ok ? {items: await r.json()} : {error: await r.text()}; }
  catch (e) { return {error: "The remote stopped. Start it again in Terminal."}; }
}
Promise.all([list("/apps"), list("/inputs")]).then(([apps, inputs]) => {
  watch.innerHTML = "";
  for (const a of apps.items || []) {
    const b = document.createElement("button");
    b.textContent = a.name; b.title = a.name;
    const brand = BRANDS[a.name.toLowerCase()];
    if (brand) {
      b.classList.add("brand");
      b.style.setProperty("--brand-bg", brand[0]); b.style.setProperty("--brand-fg", brand[1]);
    }
    b.addEventListener("click", () => go("/app?uri=" + encodeURIComponent(a.uri)));
    watch.appendChild(b);
  }
  for (const i of inputs.items || []) {
    const b = document.createElement("button");
    b.textContent = i.name; b.title = i.name; b.className = "input" + (i.connected ? "" : " off");
    b.addEventListener("click", () => go("/input?uri=" + encodeURIComponent(i.uri)));
    watch.appendChild(b);
  }
  if (apps.items && !apps.items.length) watch.appendChild(note("None of your apps were found on the TV."));
  if (apps.error) watch.appendChild(note(apps.error));
  if (inputs.error) say(inputs.error, true);
});
</script></body></html>
"""


def tv_error_text(tv, e):
    """What went wrong talking to the TV, in words for the page and the health check."""
    if isinstance(e, PermissionError) or isinstance(e, urllib.error.HTTPError) and e.code == 403:
        return "The TV refused the key. Check TV_PSK against the TV's Pre-Shared Key."
    if isinstance(e, urllib.error.HTTPError):
        return f"The TV answered HTTP {e.code}. Is Simple IP control switched on?"
    if isinstance(e, (urllib.error.URLError, OSError)):
        return f"Can't reach the TV at {tv.base}. Is it on, with IP control switched on?"
    if isinstance(e, TvError):
        return f"The TV said no: {e}"
    return str(e)


DEFAULT_APPS = ["YouTube", "Pluto TV"]


def apps_wanted(setting):
    """TV_APPS as a list of app names; unset or blank means the defaults."""
    names = [n.strip() for n in (setting or "").split(",") if n.strip()]
    return names or DEFAULT_APPS


def make_handler(tv, lan, apps=DEFAULT_APPS):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, body, content_type="text/plain; charset=utf-8", cache="no-store"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            # A page on another site could aim requests at this port; it cannot add a custom header
            # without a preflight we never answer, and a rebound DNS name fails the Host check.
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return lan or host in ("127.0.0.1", "localhost", "::1")

        def tv_error(self, e):
            return self.reply(502, tv_error_text(tv, e))

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, "Forbidden")
            if self.path == "/":
                return self.reply(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/text":
                try:
                    active, text = tv.text()
                except Exception:
                    active, text = None, None
                return self.reply(200, json.dumps({"active": active, "text": text}), "application/json")
            if self.path == "/state":
                try:
                    sound = tv.sound()
                except Exception:
                    sound = {"muted": None, "volume": None, "maxVolume": None}
                state = {"muted": sound["muted"], "volume": sound["volume"], "maxVolume": sound["maxVolume"],
                         "power": tv.power_state()}
                return self.reply(200, json.dumps(state), "application/json")
            if self.path in ICONS:
                return self.reply(200, icon(self.path), "image/png", "max-age=86400")
            if self.path == "/health":
                # For uptime monitors: 200 only when the TV answers a call that needs the key.
                try:
                    tv.inputs()
                except Exception as e:
                    return self.reply(503, json.dumps({"status": "error", "error": tv_error_text(tv, e)}),
                                      "application/json")
                return self.reply(200, json.dumps({"status": "ok"}), "application/json")
            if self.path == "/apps":
                try:
                    return self.reply(200, json.dumps(tv.apps(apps)), "application/json")
                except Exception as e:
                    return self.tv_error(e)
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
                elif self.path == "/power/on":
                    tv.power_on()
                elif self.path == "/volume":
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > 256:
                        return self.reply(413, "Too long")
                    level = json.loads(self.rfile.read(length) or b"{}").get("level")
                    if not isinstance(level, int) or isinstance(level, bool):
                        return self.reply(400, "Expected {\"level\": a whole number}")
                    tv.set_volume(level)
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
                elif self.path.startswith("/app?uri="):
                    tv.launch(urllib.parse.unquote(self.path[len("/app?uri="):]))
                elif self.path.startswith("/input?uri="):
                    tv.switch(urllib.parse.unquote(self.path[len("/input?uri="):]))
                else:
                    return self.reply(404, "Not found")
            except Exception as e:
                return self.tv_error(e)
            self.reply(204, "")

    return Handler


APP_ID = "tv.cleanyour.remote"

APP_SCRIPT = """#!/bin/bash
# Made by tools/sony-remote.py --make-app. Opens the remote, starting it first when it isn't running.
url=http://127.0.0.1:{port}/
if /usr/bin/curl -fs -o /dev/null -m 1 "$url"; then exec /usr/bin/open "$url"; fi
log="$HOME/Library/Logs/TV Remote.log"
cd {repo} || {{
  /usr/bin/osascript -e 'display alert "TV Remote" message "The cleanyourtv folder has moved. Run tools/sony-remote.py --make-app again from its new place."'
  exit 1
}}
TV_HOST={host} TV_PSK={psk} nohup {python} tools/sony-remote.py --port {port}{lan} >"$log" 2>&1 &
for _ in $(seq 40); do
  sleep 0.25
  /usr/bin/curl -fs -o /dev/null -m 1 "$url" && exit 0
done
/usr/bin/osascript -e 'display alert "TV Remote" message "The remote did not start. What went wrong is in ~/Library/Logs/TV Remote.log."'
"""


def icon_png(size=512, bleed=False):
    """The app icon as PNG bytes: a dark rounded square, the grey D-pad ring and a white OK button.

    bleed fills the whole square with no transparent margin, for iOS, which rounds the corners itself
    and shows transparency as black; the ring and button grow to match the larger background."""
    c = size / 2
    k = 1 / 0.8 if bleed else 1

    def cover(d):  # distance outside a shape -> coverage, with a one-pixel soft edge
        return max(0.0, min(1.0, 0.5 - d))

    def blend(base, color, a):
        return tuple(round(b + (k - b) * a) for b, k in zip(base, color))

    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            # rounded square 0.8 of the canvas, corner radius 0.18
            half, rad = size * 0.4, size * 0.18
            qx, qy = max(abs(px - c) - (half - rad), 0), max(abs(py - c) - (half - rad), 0)
            a = 1.0 if bleed else cover((qx * qx + qy * qy) ** 0.5 - rad)
            rgb = (21, 24, 30)
            r = ((px - c) ** 2 + (py - c) ** 2) ** 0.5
            rgb = blend(rgb, (53, 57, 69), cover(r - size * 0.27 * k))
            rgb = blend(rgb, (21, 24, 30), cover(r - size * 0.17 * k))
            rgb = blend(rgb, (238, 240, 244), cover(r - size * 0.11 * k))
            row += bytes(rgb) + bytes([round(255 * a)])
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


# The page's icons, the Mac app's own, drawn on first request and kept: path -> (size, bleed).
ICONS = {"/icon.png": (192, False), "/favicon.ico": (64, False), "/apple-touch-icon.png": (180, True)}
_icons = {}


def icon(path):
    if path not in _icons:
        _icons[path] = icon_png(*ICONS[path])
    return _icons[path]


def make_app(host, psk, args, folder):
    """Write TV Remote.app into folder and return its path."""
    app = os.path.join(os.path.expanduser(folder), "TV Remote.app")
    if os.path.exists(app):
        try:
            with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
                ours = plistlib.load(f).get("CFBundleIdentifier") == APP_ID
        except (OSError, plistlib.InvalidFileException):
            ours = False
        if not ours:
            sys.exit(f"{app} exists and was not made by this script; move it away first.")
        shutil.rmtree(app)
    macos, resources = os.path.join(app, "Contents", "MacOS"), os.path.join(app, "Contents", "Resources")
    os.makedirs(macos)
    os.makedirs(resources)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(macos, "TV Remote")
    with open(script, "w") as f:
        f.write(APP_SCRIPT.format(port=args.port, repo=shlex.quote(repo), host=shlex.quote(host),
                                  psk=shlex.quote(psk), python=shlex.quote(sys.executable),
                                  lan=" --lan" if args.lan else ""))
    os.chmod(script, 0o755)
    info = {"CFBundleName": "TV Remote", "CFBundleDisplayName": "TV Remote", "CFBundleIdentifier": APP_ID,
            "CFBundleExecutable": "TV Remote", "CFBundlePackageType": "APPL", "CFBundleVersion": "1",
            "CFBundleShortVersionString": "1.0", "LSUIElement": True}
    png = os.path.join(resources, "AppIcon.png")
    with open(png, "wb") as f:
        f.write(icon_png())
    # sips (on every Mac) turns the PNG into the .icns Finder and the Dock want.
    if shutil.which("sips") and subprocess.run(
            ["sips", "-s", "format", "icns", png, "--out", os.path.join(resources, "AppIcon.icns")],
            capture_output=True).returncode == 0:
        info["CFBundleIconFile"] = "AppIcon"
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(info, f)
    return app


def main():
    ap = argparse.ArgumentParser(description="Browser remote for Sony BRAVIA TVs over IP control.")
    ap.add_argument("--port", type=int, default=8765, help="local port for the page (default 8765)")
    ap.add_argument("--lan", action="store_true", help="serve other devices on the network too")
    ap.add_argument("--no-browser", action="store_true", help="don't open the page")
    ap.add_argument("--make-app", nargs="?", const="~/Applications", metavar="FOLDER",
                    help="write a one-click TV Remote.app with these settings (default ~/Applications)")
    args = ap.parse_args()
    host, psk = os.environ.get("TV_HOST"), os.environ.get("TV_PSK")
    if not host or not psk:
        sys.exit("Set TV_HOST and TV_PSK, e.g.  TV_HOST=192.168.1.50 TV_PSK=<key> python3 tools/sony-remote.py\n"
                 "(the key is the TV's Settings > Network & Internet > Home network > IP control > Pre-Shared Key)")
    if args.make_app:
        app = make_app(host, psk, args, args.make_app)
        print(f"Made {app}\nOpen it from Launchpad or Spotlight (\"TV Remote\"), or drag it to the Dock.")
        return
    tv = Tv(host, psk)
    server = ThreadingHTTPServer(("0.0.0.0" if args.lan else "127.0.0.1", args.port),
                                 make_handler(tv, args.lan, apps_wanted(os.environ.get("TV_APPS"))))
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

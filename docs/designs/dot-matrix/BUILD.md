# Building the dot-matrix design

A brief for the Claude session on the ThinkPad that builds this design into the launcher. Read
[`CLAUDE.md`](../../../CLAUDE.md) first (owner, TV, ThinkPad folders), then [`README.md`](README.md) (the
decisions) and open [`sketch.html`](sketch.html) in a browser: it is the reference for every screen, in all
three modes. Sizes in the sketch are Android dp/sp: the TV is 1920×1080 at xhdpi, so 960×540 dp.

The owner doesn't code. Work through the steps below in order, one commit per step, pushed to `main`, with
the checks under **Every step** passing before the next one. Explain progress in plain words.

## Every step

1. `python3 -m unittest discover -s tests` passes.
2. `cd launcher && ./gradlew testReleaseUnitTest lintRelease assembleRelease` passes.
3. `stat -c %s launcher/app/build/outputs/apk/release/app-release.apk` is under 409,600 bytes (CI's
   limit). It was 406,983 before this work; after step 2 it should be near 380,000.
4. From step 3 on: install with `TV_HOST=192.168.1.210 launcher/build-and-install.sh` (debugging on; see
   CLAUDE.md if port 5555 refuses) and compare a TV screenshot with the sketch:
   `TV_HOST=192.168.1.210 tools/venv/bin/python tools/tv.py 'screencap -p /sdcard/s.png'`, then
   `... tools/tv.py --pull /sdcard/s.png /tmp/s.png`. Remind the owner to switch debugging off at the end.

Work in `~/tv-setup/cleanyourtv` only. Never touch `~/cleanyourtv` (the TV remote service).

## Step 1: English only

The owner chose English only. Remove:

- every `launcher/app/src/main/res/values-*/` folder (translations, and the `bools.xml` overrides for
  `de`, `pt`, `ru`, `iw`; the defaults in `values/bools.xml` stay),
- `res/layout-iw/` (the mirrored Hebrew Home) and `tests/test_hebrew_resources.py`,
- `res/xml/locales_config.xml` and `android:localeConfig` in `AndroidManifest.xml`,
- the language claims in `README.md` (the "Language follows the TV" bullet, the 19-languages stat) and
  `README.zh-CN.md`, if present.

Keep the `R.bool.rtl_*` code paths; they read the defaults (false).

## Step 2: fonts

Replace Inter with Doto (display) and Space Mono (text). Measured: about 34 KB in the APK against Inter's
60 KB. Prepare the files with fonttools in a throwaway venv, sources from the google/fonts repository:

```bash
python3 -m venv ~/font-tools && ~/font-tools/bin/pip install -q fonttools
mkdir -p ~/font-work && cd ~/font-work
G=https://raw.githubusercontent.com/google/fonts/main/ofl
curl -sSfLO "$G/doto/Doto%5BROND,wght%5D.ttf"
curl -sSfLO "$G/spacemono/SpaceMono-Regular.ttf"
curl -sSfLO "$G/spacemono/SpaceMono-Bold.ttf"
curl -sSfL -o OFL-doto.txt "$G/doto/OFL.txt"
curl -sSfL -o OFL-spacemono.txt "$G/spacemono/OFL.txt"
# Text font: the same characters the current Inter file covers.
~/font-tools/bin/python -c "from fontTools.ttLib import TTFont; print(','.join('U+%04X' % c for c in sorted(TTFont('$HOME/tv-setup/cleanyourtv/launcher/app/src/main/res/font/inter.ttf').getBestCmap())))" > unicodes.txt
for w in Regular Bold; do ~/font-tools/bin/pyftsubset SpaceMono-$w.ttf --unicodes-file=unicodes.txt --no-hinting --notdef-outline --output-file=space_mono_$(echo $w | tr A-Z a-z).ttf; done
# Display font: one static instance, square dots, weight 900; capitals, digits, punctuation, accented capitals.
~/font-tools/bin/fonttools varLib.instancer "Doto%5BROND,wght%5D.ttf" ROND=0 wght=900 -o doto-900.ttf
~/font-tools/bin/pyftsubset doto-900.ttf --unicodes="U+0020-0040,U+0041-005A,U+005B-0060,U+007B-007E,U+00B7,U+00C0-00DE,U+2013,U+2014,U+2019,U+2026" --no-hinting --notdef-outline --output-file=doto.ttf
```

Then in `res/font/`: add `doto.ttf`, `space_mono_regular.ttf`, `space_mono_bold.ttf` and a
`space_mono.xml` family (400 = regular, 700 = bold); delete `inter.ttf` and the four `inter_*.xml`
families. Point every `@font/inter*` (and `R.font.inter_medium` in `AppLibraryDialog.java`) at
`@font/space_mono`, except the display texts, which use `@font/doto` with `textAllCaps="true"` (Doto has no
lowercase): the Home clock, the shelf app name, the Clock screensaver's time, the race panel headline, the
Launcher settings title and its number choices. Replace `launcher/FONT-LICENSE-OFL.txt` with both OFL texts
(or two files) and update `LICENSE`, `README.md` and the typeface lines in `CLAUDE.md`. Characters missing
from a subset (non-Latin app names, `ʼ`, `✓`) fall back to Android's own font, which is fine.

## Step 3: Home

Match the sketch's Home and App grid screens (dark mode first).

- **Background:** colour from the mode, plus a faint dot grid: 1.1 dp dots every 12 dp, white at 7.5 %
  (dark/color) or black at 10 % (light). A small repeating bitmap shader, drawn once; a theme wallpaper, if
  enabled, still draws over it.
- **Top bar, left:** Inputs, Wi-Fi (network name), Settings and a new **Mode** segment (a half-filled circle
  icon and the current mode's name) as segments of one bar: 40 dp high, 3 dp padding, 1 dp outline, radius
  20, segments radius 17, Space Mono 12 sp, uppercase, letter-spacing 0.1. The focused segment fills with
  the ink colour and shows a 5 dp dot in the accent colour; **every segment reserves that dot's space** so
  widths never change. The optional reorder button becomes an icon-only segment. Down from the bar returns
  to the dock tile focus came from, as now.
- **Time and date, right:** one line, centred on the bar: time in Doto 12 sp, AM/PM Space Mono 11 sp at
  60 %, date Space Mono 12 sp at 60 %, letter-spacing 0.14, format `EEE  d MMM` uppercase (`MON  9 NOV`).
- **Greeting:** removed, with `updateGreeting`, the festive greeting and `greeting_name` (drop it from
  `config.xml`, `Config.java` and `themes/README.md`). Festival themes otherwise keep working.
- **Shelf above the dock:** the app name in Doto 64 sp, uppercase; under it `02 / 04 · DOCK` in Space Mono
  11 sp, letter-spacing 0.16, at 55 %, after a 7 dp accent dot (in colour mode an 18 dp bullet holding the
  slot number).
- **Dock:** no filled band (`DockDecoration`): a 1 dp **dashed** outline at 30 % ink, radius 26, 14 dp
  around the tiles. No ambient glow behind it in any mode.
- **Tiles:** unfocused banners in greyscale (ColorMatrix saturation 0; dark: ×0.75 brightness; light:
  contrast 0.92) with a faint 1 dp outline; the focused tile in full colour, scaled 1.08 with a 2 dp ink
  ring (accent ring in colour mode). The glass highlight becomes that ring; keep the spring.
- **Under the focused tile:** three 4 dp accent pips (dock), or for grid rows the app name in Space Mono 11
  sp uppercase after an accent dot (a lettered bullet in colour mode).

## Step 4: Inputs, Settings, screensaver

- **Inputs popup:** panel in the background colour, 1 dp outline at 30 %, radius 18, 6 dp padding; rows 42
  dp, Space Mono 12 sp uppercase; the port after the name in 10 sp at 60 % (`SWITCH 2  HDMI 4`); status
  right in 10 sp: a filled dot for connected, a hollow ring for no device. The focused row fills with the
  ink colour and its icon takes the accent colour. While open, the Inputs segment stays filled.
- **Launcher settings:** the sketch's two columns. Title `LAUNCHER SETTINGS` in Doto 34 sp; apps per row
  and rows below dock as number boxes (82×44 dp, radius 12, Doto 20 sp) with an accent dot under the current
  value; wallpaper, animations, advanced effects as rows (44 dp, radius 12) with `ON` / `OFF` and an accent
  dot when on; then Follow theme and Choose default home. Focused control fills with the ink colour.
- **Clock screensaver (`ClockDream`):** Doto 120 sp time, AM/PM 18 sp at 60 %, the date in Space Mono 16
  sp, letter-spacing 0.2, after a 6 dp accent dot; keep the existing once-a-minute drift, no glow.

## Step 5: modes

Three colour sets; nothing else changes between them.

| | Dark | Light | Color |
|---|---|---|---|
| Background | `#000000` | `#ECEBE6` | `#000000` |
| Ink (text, focus fill) | `#F2F2F2` | `#111111` | `#F2F2F2` |
| Text on focus fill | `#000000` | `#F2F2F2` | `#000000` |
| Secondary text | ink at 60 % | ink at 55 % | ink at 60 % |
| Accent | red `#D71921` | red `#D71921` | the focused item's line colour |

**Color** uses NYC Subway line colours as identifiers: dock slots 1–4 red `#EE352E`, green `#00933C`, blue
`#0039A6`, orange `#FF6319`; grid apps A, B, C… cycling yellow `#FCCC0A`, purple `#B933AD`, lime `#6CBE45`,
brown `#996633`, grey `#A7A9AC`, blue, green, orange; bar segments Inputs orange, Wi-Fi blue, Settings
grey, Mode purple; Inputs rows red, green, blue, orange, yellow in order; settings sections apps per row
yellow, rows below dock lime, switches purple, actions grey; screensaver red. Bullets are circles holding the
number or letter in bold; yellow and grey take black text, the rest white.

- **Choosing:** the Mode segment cycles Dark → Light → Color and redraws Home at once. Store it as an
  on-TV choice like the columns choice (cleared by Follow theme and by a theme push). A theme can set it
  with `"mode": "dark" | "light" | "color"` in `config.json`; built-in default `dark` in `config.xml`.
  Document the key in `themes/README.md`, and add a unit test for parsing it.
- Popups, Launcher settings and the screensaver follow the mode too.

## Not in this build

- Remembering the last HDMI-CEC device per port ("HDMI 4 · last: Steam Deck"). CEC names already show
  while a device is connected (needs BRAVIA Sync on and no custom name on the port).
- The glass design (`docs/designs/glass/`) and a switch between designs.

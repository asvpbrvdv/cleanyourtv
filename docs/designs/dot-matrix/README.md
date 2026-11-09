# Dot-matrix design (in progress)

The direction chosen for the launcher in November 2026, replacing the
[glass design](../glass/). [`sketch.html`](sketch.html) sketches every screen the launcher draws (Home, App grid, Inputs,
Settings, Screensaver) with a Dark / Light switch; open it in a browser and use the arrow keys.

## So far

- **Type:** [Doto](https://fonts.google.com/specimen/Doto) (dot matrix) for the time, the date and the app
  name; [Space Mono](https://fonts.google.com/specimen/Space+Mono) for labels. Both are free (SIL OFL).
- **Colour:** black, white and one red, `#D71921`, used only for what is selected. Light mode: paper
  white `#ECEBE6` with black ink and the same red.
- **Apps:** tiles in greyscale; the selected tile switches to full colour.
- **Background:** a faint dot grid. No colour glow, no gradient.
- **Dock:** a thin dashed outline instead of a filled band.
- **Header:** the button bar on the left; time and date in one small line on the right, the time the same
  size as the date.
- **Under the app name:** its place in the dock, e.g. `02 / 04 · DOCK`.
- **Top bar:** every segment keeps room for the red dot, so selecting one never changes its width.
- **App grid:** the selected app's name under its tile with a red dot; the dock keeps its pips.
- **Inputs:** Home dims and a panel drops from the bar; filled dot = device on, hollow = empty port.
- **Settings:** two columns; number choices as boxes with a red dot under the current one, switches as
  rows with a red dot when on.
- **Screensaver:** a large dotted clock and the date, drifting slowly so nothing burns in.
- **Modes:** Dark, Light and Color, switched from a fourth segment in the top bar (OK cycles them). Colour sets
  only, so no extra space. Color is the dark look with NYC Subway line colours used as identifiers, the way the
  subway uses them: each dock slot has a numbered bullet (1 red `#EE352E`, 2 green `#00933C`, 3 blue `#0039A6`,
  4 orange `#FF6319`), grid apps lettered ones (yellow `#FCCC0A`, purple `#B933AD`, lime `#6CBE45`, brown
  `#996633`, grey `#A7A9AC`, …), and the selected item lights up in its colour. Yellow and grey bullets take
  black text.
- **Inputs names:** a device that speaks HDMI-CEC is already listed under its own name ("Switch 2 · HDMI 4");
  on the Sony that needs BRAVIA Sync on and no custom name on the port. Remembering the last device seen on a
  port ("HDMI 4 · last: Steam Deck") would be a small addition.

## Size check

Measured by trimming the fonts the same way as Inter (compressed size inside the APK):

| Font | Characters | Size |
|---|---|---|
| Inter (current) | Latin, weights 200 to 500 | 60.5 KB |
| Doto, weight 800, round dots off | capitals, digits, punctuation, accented capitals | 3.6 KB |
| Space Mono Regular + Bold | the same Latin set as Inter, minus `ʼ` and `✓` (Android draws those from its own font) | 30 KB |

Replacing Inter with Doto and Space Mono saves about 26 KB, so the APK would land near 381 KB.

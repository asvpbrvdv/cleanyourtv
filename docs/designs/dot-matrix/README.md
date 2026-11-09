# Dot-matrix design (in progress)

The direction chosen for the launcher in November 2026, replacing the
[glass design](../glass/). [`sketch.html`](sketch.html) is a rough sketch of the home screen with a
Dark / Light switch; open it in a browser and use the arrow keys.

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

## Size check

Measured by trimming the fonts the same way as Inter (compressed size inside the APK):

| Font | Characters | Size |
|---|---|---|
| Inter (current) | Latin, weights 200 to 500 | 60.5 KB |
| Doto, weight 800, round dots off | capitals, digits, punctuation, accented capitals | 3.6 KB |
| Space Mono Regular + Bold | the same Latin set as Inter, minus `ʼ` and `✓` (Android draws those from its own font) | 30 KB |

Replacing Inter with Doto and Space Mono saves about 26 KB, so the APK would land near 381 KB.

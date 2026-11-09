# Glass design (kept for later)

A home-screen design worked out in a mockup in November 2026 and set aside in favour of the
[dot-matrix design](../dot-matrix/). None of it is built into the launcher. It is kept here so it can be
picked up again.

Open [`mockup.html`](mockup.html) in a browser to try it: click the screen, then use the arrow keys,
Enter and Esc. The settings panel next to it switches each decision below back to the current
launcher's look for comparison.

## Decisions

| Area | Decision | How it would be built |
|---|---|---|
| Top bar | Inputs, Wi-Fi and Settings as segments of one bar on the **left**; the selected segment turns white with dark text | Code: `res/layout/activity_main.xml`, a new bar background drawable |
| Bar look | **Tinted**: dark and see-through, `rgba(6,10,24,.42)` with a faint `rgba(255,255,255,.1)` edge (a frosted variant is in the mockup) | Code: the bar background drawable |
| Greeting | **Removed** everywhere, including the name and festive greetings | Code: `activity_main.xml`, `MainActivity.java` |
| Time and date | One small line on the **right**, level with the bar: `4:52 PM │ MON  9 NOV` | Code: `activity_main.xml` |
| Time | 14 dp, **Medium** (500), same size as the date | Code: `activity_main.xml` |
| Date | Three-letter day and month, `EEE  d MMM` | Code: `res/values/strings.xml` |
| App name above the dock | **Medium** (500) instead of Light | Code: `activity_main.xml` |
| Dock band | **Frosted glass**: a light see-through gradient with a bright edge, over the app's colour glow | Code: `DockDecoration.java` |
| Wallpaper | Soft blobs on the diagonal: Apple red `#FF453A` top left, Apple blue `#0A84FF` bottom right, navy `#0A1433` between (also the background colour) | Theme: a 1920×1080 `wallpaper.jpg` with light grain against banding, no rebuild |

## Notes

- Inter in the launcher goes up to weight 500 only (trimmed to keep the APK under 400 KB); a heavier time
  would need a larger font file.
- The launcher before either design is tagged `before-dot-matrix` in git.

# Notes for Claude

This is a personal copy of [Gathin23/cleanyourtv](https://github.com/Gathin23/cleanyourtv), set up for
one TV. The owner is comfortable with tech but doesn't code: explain in plain words, give one command
per code block, and say what each command does and what output to expect.

## Working on this repo

- Commit and push straight to `main`. The original code is backed up elsewhere, so no branch or pull
  request is needed unless the owner asks for one.
- `backup/` and `tools/adbkey/` stay local (see `.gitignore`). `backup/` holds the TV's serial number
  and is the only record of its original state: never commit it, move it or delete it.

## The TV

- Sony BRAVIA XR-65X90J (65", 2021). It reports itself as `BRAVIA 4K VH2` (`BRAVIA_VH2_UC`), Google TV,
  Android 12 (SDK 31). IP on the home Wi-Fi: `192.168.1.210`.
- The closest lists in `examples/` are `sony-bravia-4k-vh2` and `sony-kd-65x80j`.
- Debugging is off between updates. To connect: turn USB debugging on, then
  `TV_HOST=192.168.1.210 tools/venv/bin/python tools/tv.py --probe`. If that says "Connection refused",
  port 5555 is closed again (it closes on every TV restart). Turn on Wireless debugging and reopen it:
  `~/Android/Sdk/platform-tools/adb connect 192.168.1.210:<port shown on the TV>`, then
  `~/Android/Sdk/platform-tools/adb tcpip 5555`. The ThinkPad is already paired.
- After an update, remind the owner to switch USB debugging and Wireless debugging off.

## The ThinkPad (Ubuntu), where updates are run from

- **`~/tv-setup/cleanyourtv`** is this repo, with the launcher setup and `backup/`. Work here.
- **`~/cleanyourtv`** is a different checkout: the browser TV remote (`tools/sony-remote.py`), run as
  the `tv-remote` service from the `claude/quirky-bohr-1kj066` branch, and updated every 5 minutes by
  `/usr/local/sbin/tv-remote-update` (see `deploy/README.md` on that branch). Don't edit, unzip into or
  pull other branches into it: the updater stops if that checkout has local changes.
- Build tools: JDK 17, Android SDK in `~/Android/Sdk` (platform 34, build-tools 34.0.0),
  `launcher/local.properties` points at it, and the Python venv is `tools/venv`. To build without
  installing: `cd launcher && ./gradlew assembleRelease`.

## The launcher

- Design direction: the **dot-matrix** look in `docs/designs/dot-matrix/` (in progress). The glass design
  in `docs/designs/glass/` is set aside for later; no theme switcher between the two is planned. The launcher
  as it was before either design is the git tag `before-dot-matrix`.
- The typeface is Inter, not Outfit: `res/font/inter.ttf`, trimmed to Outfit's characters and weights
  200 to 500 so the APK stays small. CI fails the build at 400 KB (409,600 bytes); the release APK was
  406,983 bytes after the switch, so there is little room. If a change pushes it over, trim the font
  further (its kerning table is the largest part) before removing anything else.
- Look-and-feel changes that `config.json` covers (dock, columns, colours, wallpaper; see
  `themes/README.md`) go out with `tools/theme.sh` without a rebuild. Anything else needs
  `TV_HOST=192.168.1.210 launcher/build-and-install.sh`.

#!/usr/bin/env bash
# Keeps the TV remote on the ThinkPad up to date.
#
# Every 5 minutes (see tv-remote-update.timer) this checks the remote's branch
# on GitHub. If there's something new, it pulls it, runs the remote's tests,
# and restarts the tv-remote service only if they pass. If they fail, it goes
# back to the version that was running and skips that update until a newer
# one arrives.
#
# Installed as /usr/local/sbin/tv-remote-update and run by systemd as root
# (restarting a system service needs it). Git and the tests run as the
# owner of the checkout, never as root.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/key/cleanyourtv}"
BRANCH="${BRANCH:-claude/quirky-bohr-1kj066}"
SERVICE="${SERVICE:-tv-remote}"
STATE_DIR="${STATE_DIR:-/var/lib/tv-remote-update}"
OWNER="$(stat -c '%U' "$APP_DIR")"
OWNER_HOME="$(getent passwd "$OWNER" | cut -d: -f6)"

as_owner() { runuser -u "$OWNER" -- env HOME="$OWNER_HOME" "$@"; }
git_() { as_owner git -C "$APP_DIR" "$@"; }

mkdir -p "$STATE_DIR"
git_ fetch --quiet origin "$BRANCH"
old=$(git_ rev-parse HEAD)
new=$(git_ rev-parse "origin/$BRANCH")
[ "$old" = "$new" ] && exit 0

# An update that already failed its tests is skipped until a newer one arrives.
if [ "$(cat "$STATE_DIR/failed" 2>/dev/null)" = "$new" ]; then
  exit 0
fi

if ! git_ merge --ff-only --quiet "origin/$BRANCH"; then
  echo "Update skipped: $APP_DIR has local changes. Run 'git -C $APP_DIR status' to see them." >&2
  exit 1
fi

if ! out=$(cd "$APP_DIR" && as_owner python3 -m unittest tests.test_sony_remote 2>&1); then
  git_ reset --quiet --hard "$old"
  echo "$new" > "$STATE_DIR/failed"
  echo "Update to $(git_ log -1 --format='%h %s' "$new") failed its tests, so the remote stays on $(git_ log -1 --format=%h "$old"):" >&2
  tail -n 15 <<<"$out" >&2
  exit 1
fi

rm -f "$STATE_DIR/failed"
systemctl restart "$SERVICE"
echo "Updated to: $(git_ log -1 --format='%h %s') and restarted $SERVICE"

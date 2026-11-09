# TV remote: automatic updates on the ThinkPad

The ThinkPad runs `tools/sony-remote.py` from the `claude/quirky-bohr-1kj066`
branch as the `tv-remote` service. With the updater installed, it checks that
branch every 5 minutes. When there's a new version it pulls it, runs
`tests/test_sony_remote.py`, and restarts the remote only if the tests pass.
If they fail, the remote stays on the version that was working.

## Install (once)

```bash
git -C ~/cleanyourtv pull
sudo install -m 755 ~/cleanyourtv/deploy/tv-remote-update.sh /usr/local/sbin/tv-remote-update
sudo cp ~/cleanyourtv/deploy/tv-remote-update.service ~/cleanyourtv/deploy/tv-remote-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tv-remote-update.timer
```

The updater is copied to `/usr/local/sbin` rather than run from the checkout,
because it runs as root to restart the service: a change pushed to GitHub can
update the remote, but can't change what runs as root. To change the updater
itself, edit it here and run the `sudo install` line again.

## Check on it

```bash
systemctl list-timers tv-remote-update.timer
journalctl -u tv-remote-update -n 20 --no-pager
```

Run an update right away: `sudo systemctl start tv-remote-update`

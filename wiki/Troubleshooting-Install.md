# Troubleshooting — installer

## Bootstrap script exits with "command not found"

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/glloq/…/bootstrap.sh) --service
```

If `curl` is missing, install it first:

```bash
sudo apt update
sudo apt install -y curl
```

## "Could not fetch from PPA" warnings

Harmless. The Raspberry Pi OS image carries a few third-party PPAs that
sometimes 403 from `launchpad.net`. `apt` falls back to the main archive
and OmniPlot's required packages all live there.

## `uv` install hangs

The script downloads `uv` from `astral.sh`. If you're on a restricted
network, allow that domain or pre-install `uv` manually and re-run the
bootstrap script — the *"uv already installed"* branch is taken.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
```

## `npm ci` fails with "ENOSPC" / disk full

The frontend build needs ~600 MB of `node_modules` and ~150 MB of build
artefacts. A fresh Pi OS image leaves enough; an existing system with
many other apps might not.

```bash
df -h /
sudo apt clean
docker system prune -af   # if you run docker
```

## `npm ci` fails with "Cannot find module 'esbuild'"

You hit the platform-mismatch trap — `node_modules` was hydrated on a
different architecture (e.g. x86_64 macOS) and rsync'd to the Pi.

```bash
cd ~/rsp-pen-plotter/frontend
rm -rf node_modules
npm ci
```

## Service starts but `curl http://localhost:8000/health` hangs

Check the journal:

```bash
sudo journalctl -u omniplot -n 200 --no-pager
```

Common causes:

- `OMNIPLOT_REQUIRE_AUTH=1` set with no `OMNIPLOT_API_KEY` — the service
  refuses to start by design
- another process already binds `:8000` (e.g. an old `uvicorn` you
  forgot to kill) — `sudo lsof -i :8000` to find it
- the frontend `dist/` folder doesn't exist — re-run
  `./install.sh --no-system-deps` to rebuild it

## "Operation not permitted" on `/dev/ttyUSB0`

You're not in the `dialout` group yet. The installer adds you, but the
change only takes effect on a new login session.

```bash
groups            # check
sudo usermod -aG dialout $USER
# log out, log back in
```

## Service stops every ~5 minutes

Likely a converter that's leaking memory on a low-RAM Pi. Watch with:

```bash
sudo journalctl -u omniplot -f
free -m
```

If LibreOffice subprocesses are piling up:

```bash
pkill -f soffice
```

…and consider disabling the `DocumentConverter` registration by
removing it from `converters/defaults.py` if you don't need it.

## See also

- [Install on a Raspberry Pi](Install-on-a-Raspberry-Pi.md)
- [Environment variables](Environment-Variables.md)
- [Troubleshooting — connection](Troubleshooting-Connection.md)

# Install on a Raspberry Pi

OmniPlot is built to live on a Pi 4 next to the plotter, talk to the MCU over
USB and serve a web UI on the LAN. This page walks the appliance install
end-to-end.

> **TL;DR.** Flash Raspberry Pi OS Lite (64-bit), enable SSH, then on the
> first SSH session:
> ```bash
> bash <(curl -fsSL https://raw.githubusercontent.com/glloq/rsp-pen-plotter/main/bootstrap.sh) --service
> ```

## 1. Pick the Pi

| Model | Verdict |
| --- | --- |
| Pi 4 (4 GB or 8 GB) | **Recommended.** vpype + LibreOffice fit comfortably; A3 previews are smooth. |
| Pi 5 | Works, untested by the team. Should be at least as fast as a Pi 4. |
| Pi 3 B+ | Marginal. PDF / DOCX conversions are slow; A4 previews OK, A3 sluggish. |
| Pi Zero 2 W | Not supported. Browser previews timeout, LibreOffice is too heavy. |

The host doesn't need to run real-time motion — Klipper on the RP2040
handles that. The Pi just orchestrates.

## 2. Flash the OS

Raspberry Pi OS Lite (64-bit) is enough — OmniPlot ships its own dev server.
Headless desktop builds work too if you want to host the UI on a touch
screen attached to the Pi.

Use the Raspberry Pi Imager and set, under the cog menu:

- hostname (`plotter.local` makes the UI easy to reach)
- SSH enabled with a public key
- Wi-Fi credentials, if you're not running Ethernet

## 3. Run the installer

```bash
ssh pi@plotter.local
bash <(curl -fsSL https://raw.githubusercontent.com/glloq/rsp-pen-plotter/main/bootstrap.sh) --service
```

The installer is idempotent — re-run it any time. It will:

1. `apt install potrace ghostscript libreoffice-writer` (converters)
2. install Node.js 20 via NodeSource if missing
3. install `uv` (the Python toolchain) into `~/.local/bin`
4. `uv sync` the backend
5. `npm ci && npm run build` the frontend
6. write `/etc/systemd/system/omniplot.service`, add the user to `dialout`,
   enable and start the service

When it finishes, point a browser at `http://plotter.local:8000` (or the
Pi's IP). On the very first run the audit log, library and SQLite database
are created automatically.

## 4. Plug in the plotter

The MCU plugs into a Pi USB port. After `--service` the installer added the
user to the `dialout` group; you might need to log out and back in once for
that to take effect.

The serial device usually appears as `/dev/ttyACM0` (RP2040 / Klipper) or
`/dev/ttyUSB0` (CH340-based boards). The UI's *Plotter → Connect* panel
auto-suggests the available ports.

## 5. Optional hardening

If the Pi is on a shared LAN:

```bash
nano ~/rsp-pen-plotter/.env.service     # written by install-service.sh, mode 600
# add:
OMNIPLOT_API_KEY=<32+ random characters>
OMNIPLOT_REQUIRE_AUTH=1
OMNIPLOT_CORS_ORIGINS=http://plotter.local:8000
sudo systemctl restart omniplot
```

`OMNIPLOT_REQUIRE_AUTH=1` makes the service refuse to start with an empty
key — handy guard rail against accidental restarts. See
[Environment variables](Environment-Variables.md) for the full list.

## 6. Updating

The Settings → System panel surfaces "update available" toasts. Click it,
the Pi runs the equivalent of:

```bash
cd ~/rsp-pen-plotter
./update.sh
```

…which fetches `origin/main`, re-runs the converter / Node / `uv` setup,
rebuilds the frontend and restarts the systemd unit. The update endpoint
can be disabled (`OMNIPLOT_DISABLE_UPDATE=1`) on appliances that should
only be updated by hand.

When re-running `./install.sh` manually, two flags are useful on an
appliance: `--no-restart` skips the automatic restart of an installed
`omniplot.service`, and `--no-service-refresh` keeps an existing systemd
unit as-is instead of refreshing it.

## See also

- [Troubleshooting — installer](Troubleshooting-Install.md)
- [Troubleshooting — first connection](Troubleshooting-Connection.md)
- [Environment variables](Environment-Variables.md)
- [`getting_started.md`](../docs/getting_started.md) (full dev install)

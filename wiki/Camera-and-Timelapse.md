# Camera & timelapse

OmniPlot can watch the plotter through one or two network cameras and record a
**timelapse** of a print — manually, or automatically for the duration of every
job. The live feed and the recorder both live on the **Plotter** tab; the
camera configuration and the timelapse defaults live in the **Settings** modal.

## Configuring a camera

Open **Settings** (gear icon) → **System**. There are two camera slots; each
has an enable toggle, an optional label (defaults to *Camera 1* / *Camera 2*)
and a stream URL.

Any `http://` or `https://` source that serves JPEG works:

- **MJPEG streams** (`multipart/x-mixed-replace`) — a USB webcam exposed through
  `mjpg-streamer` or `ustreamer`, a Pi CSI camera through `ustreamer` /
  `libcamera`, or most IP cameras.
- **Snapshot endpoints** — any URL that returns a single `image/jpeg` per
  request.

The configuration is stored **in your browser** (localStorage key
`omniplot.cameras`), not on the server — each device that opens the UI keeps its
own camera setup. A legacy single-camera config is migrated into slot 1
automatically.

> **Tip — common URLs.** `ustreamer` typically exposes the stream at
> `http://<pi-ip>:8080/stream` and a snapshot at `http://<pi-ip>:8080/snapshot`.
> Either works; the stream is smoother to watch, the snapshot is lighter on the
> Pi during a long timelapse.

On the **Plotter** tab the live feed appears at the top of the panel. With two
cameras enabled, a switcher lets you flip between them. The stream is torn down
when you leave the Plotter tab so an idle camera doesn't keep streaming.

## Recording a timelapse

The timelapse controls sit beside the camera feed on the **Plotter** tab. Pick
a camera, set the **interval** (how often a frame is grabbed) and the playback
**FPS**, then press **Start**. While recording, the panel shows a live frame
count; press **Stop** to finish.

On stop, OmniPlot assembles the captured frames into an H.264 MP4
(`ffmpeg -c:v libx264 -pix_fmt yuv420p -movflags +faststart`) ready for
in-browser playback, and the clip joins the saved-recordings list. From there
you can play it, download the MP4, or delete it.

| Setting | Range | Default |
| --- | --- | --- |
| Interval | 0.5 – 3600 s | 5 s |
| Playback FPS | 1 – 60 | 24 |

Frames larger than 8 MB and recordings beyond 100 000 frames are rejected as a
safety cap. Only one recording runs at a time.

## Auto-record for a whole print

Tick **Record a timelapse during prints** (in **Settings → Timelapse**, or on
the Plotter panel). With it on, OmniPlot starts a recording when a print begins
streaming and stops it when the print ends — using the interval, FPS and camera
slot from your timelapse defaults. The clip is labelled with the source file
name.

Auto-record only ever stops a recording it started itself, so a manual
recording in progress is never interrupted by a job finishing.

The timelapse defaults (auto on/off, interval, FPS, camera slot) are stored in
the browser under `omniplot.timelapseSettings`.

## Requirements

- **`ffmpeg`** must be on the host's `PATH`. The Raspberry Pi installer
  (`install.sh`) installs it for you; on a manual setup, `apt install ffmpeg`.
- A reachable camera URL (see above).

Recordings are written under `OMNIPLOT_TIMELAPSE_DIR` (default
`backend/data/timelapses/`), one folder per recording holding the frames, the
`video.mp4` and a `meta.json`.

## See also

- [Environment variables](Environment-Variables.md) — `OMNIPLOT_TIMELAPSE_DIR`
- [`docs/api_reference.md`](../docs/api_reference.md) — Timelapse endpoints
- [Manual control & the plotter cockpit](Manual-Control.md)

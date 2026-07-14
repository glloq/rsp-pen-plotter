# Offset camera

A small camera at a fixed **measurement station** lets OmniPlot *measure* each
pen's tip position and work out the XY offset between pens automatically —
instead of typing offsets by hand. This page covers the hardware, wiring,
configuration and the calibration workflow.

> New to per-pen offsets? Read [Per-slot calibration](Per-Slot-Calibration.md)
> first — it explains *what* the XY offset is and the manual (no-camera) path.
> The offset camera just **measures** that offset for you.

---

## Two cameras, two jobs

OmniPlot keeps two camera roles completely separate. Both are **optional** and
each is only needed for its own function:

| Camera | Where it's set | Used for | Required when |
| --- | --- | --- | --- |
| **Offset camera** | Per machine, on the profile (`tip_calibration`) — Settings → Cameras → Offset camera | Tip-offset / scale measurement only | Automatic offset calibration |
| **Timelapse camera** | Settings → Cameras (client-side, up to two) | Plotter live view + timelapse | Recording a timelapse |

They never share a feed. The offset camera lives with the machine because the
station is bolted to it; the timelapse camera is a workshop/session
preference. In the offset config you can either point the offset camera at one
of the configured workshop cameras or give it its own URL.

---

## The measurement station

A good station makes detection reliable. Aim for:

- **A fixed spot** the head can present a pen to, at a known machine
  coordinate (X/Y, plus Z if the machine has a motorised Z axis).
- **A camera** pointed at that spot — a USB webcam (`mjpg-streamer` /
  `ustreamer`), a Pi CSI camera (`libcamera`/`ustreamer`), or any IP camera
  that exposes a snapshot or MJPEG URL.
- **Even lighting and a contrasting background.** The default detector finds
  the pen tip as the *darkest compact blob* against a bright field — good
  contrast and no shadows or clutter behind the tip are what make it accurate.
  For **light tips** (white gel, pastel, metallic pens) flip the **Tip type**
  setting to *light on dark* and use a dark background instead — the detector
  then looks for the brightest compact blob with the same logic.
- **A rigid mount.** If the camera or station can shift, the measured offsets
  drift with it.

### Camera lighting via a Raspberry Pi GPIO pin

The station light is driven by a **Raspberry Pi GPIO pin** (a relay or an LED
driver) — the host toggles the pin directly; it is *not* a plotter G-code
command. Wire your light/relay to one of the broken-out BCM pins and pick it in
the UI.

- **Pin** — choose a BCM pin from the dropdown (the list comes from the host;
  pins 2–27 on the 40-pin header).
- **Active high / low** — leave *active high* for a normal relay; tick it off
  for boards that switch on when the pin is driven LOW.
- **On / Off** buttons let you light the station while aiming the camera.
- **Turn light on during each measurement** switches the light on around each
  grab and back off afterwards.

> GPIO control needs the Pi GPIO libraries on the host (`lgpio`, or the legacy
> `RPi.GPIO`). Off a Pi the pin selection still saves, but the UI shows a
> warning and no pin is actually toggled.

---

## Configure it

Settings → **Cameras** tab → **Offset camera**. Works on any profile with
**more than one pen — with or without a magazine** (a manual / multi-holder
machine measures pens presented by hand; a carousel/rack can also fetch them
automatically). The panel is a short guided flow:

1. Turn on **per-pen tip offsets** (`apply_pen_offsets`). This is the opt-in
   switch — off by default, so nothing changes until you enable it.
2. Tick **Use a camera to measure offsets** to reveal the station config.
3. Fill in:
   - **① Offset camera** — pick a configured workshop camera or paste a
     snapshot/MJPEG URL. A **live preview** appears; once a detection zone is
     set it's drawn as a rectangle on the feed so you can aim it.
   - **mm per pixel** — the station's pixel scale. Don't guess it: use the
     [scale assistant](#mm-per-pixel-assistant) below.
   - **Reference slot** — the pen the others are measured against (its own
     offset is `0`).
   - **Detection zone (ROI)** *(optional)* — constrain detection to where the
     tip appears. **Drag a rectangle directly on the live preview** to set it
     (or type X/Y/W/H under Advanced). Leave blank for the whole frame.
   - **Station X/Y** *(optional)* and **Z** *(optional, motorised Z only)* —
     where the head presents a pen, for guided travel.
   - **Camera light** *(optional)* — the GPIO pin + polarity (see above).
   - **Tip type** — dark tip on a light background (default, most pens) or
     light tip on a dark background (white gel, pastel, metallic). Pick the
     station background that contrasts with the pen and match this setting;
     it applies to tip measurement *and* scale calibration.
   - **Dark threshold** *(Advanced)* — the luminance cutoff for "tip" (0–255).
     Raise it if the tip is faint; lower it if shadows are picked up. (With a
     *light* tip type the same knob works on the inverted image.)
   - **Frames to average** *(Advanced)* — grab several frames per measurement
     (1–20) and take the **median** tip, so noise and the odd bad frame are
     rejected. Higher is steadier but slower; leave at `1` for a clean,
     well-lit station. When >1, the result reports a repeatability figure
     (*±X mm*) and warns if the frames disagree too much.

Use **🔍 Test detection** (under the camera) to dry-run the detector and see
the confidence + marked frame **without writing any offset** — handy for
tuning the zone, threshold and lighting. A measurement below ~35% confidence
is reported but **not applied**, so a bad detection can't corrupt an offset.

Or set it straight in the profile YAML — see
[`docs/profile_format.md`](../docs/profile_format.md#tipcalibrationconfig-camera-offset-station-adr-0005):

```yaml
apply_pen_offsets: true
tip_calibration:
  camera_url: "http://localhost:8080/?action=snapshot"
  reference_slot: 0
  mm_per_pixel: 0.05
  tip_style: dark                         # or "light" (light tip on dark background)
  dark_threshold: 80
  samples: 1                              # frames to average per measurement
  station_position: { x: 20.0, y: 400.0 }
  station_z_mm: 5.0                       # optional, motorised Z only
  roi: { x: 200, y: 150, width: 240, height: 240 }   # optional
  light_gpio_pin: 17                      # optional Pi GPIO (BCM)
  light_active_high: true
```

### mm-per-pixel assistant

Rather than guessing the scale, let OmniPlot measure it:

1. Present a target of **known size** at the station — e.g. a 10 mm square or a
   coin of known diameter.
2. Enter its size in the **Known size (mm)** field and click **Measure scale**.
3. The detector measures the target's pixel extent and fills in
   `mm_per_pixel = known size ÷ measured pixels`. A preview shows the box it
   measured.

If the target isn't found, check framing, lighting, the **dark threshold**, and
the ROI.

---

## Calibration workflow

The quickest path is **🧭 Guided measurement**: it walks you through the pens
one at a time, reference first, showing the live feed and prompting you to
present each pen (or fetching it from the magazine), then advancing on a
successful measure. Each pen also carries a status badge — *Reference*,
*Measured*, *Manual* or *Not measured*.

Prefer to do it by hand? With offsets enabled and the station configured:

1. Present (or fetch) the **reference** pen and click **Measure**. Its offset
   is `0` by definition; this records the reference tip position.
2. Present each other pen and click **Measure**. Its `xy_offset_mm` is filled
   in automatically as the difference from the reference (tagged
   *camera-measured*).
3. After each measurement a **preview image** appears under the slot with the
   detected tip marked — confirm the right point was picked.
4. **Reset measurements** starts a fresh run (forgets the reference).

### Hands-free motion (connected plotter)

If the plotter is connected you can automate presenting each pen:

- **Load pen from magazine before measuring** fetches the slot's pen via the
  normal tool-change swap (host-driven / firmware magazines; a manual magazine
  still needs a hand swap).
- **Move head to station before measuring** drives the head to the station
  X/Y (and Z) automatically.

With both on, each **Measure** does **fetch → travel → grab** in one click.

---

## How it works

- The default **`dark_blob`** detector (Pillow + NumPy, no OpenCV) thresholds
  the frame and takes the centroid of the darkest compact region as the tip.
- Measurement is **relative**: each pen's offset is the *difference* between
  its tip position and the reference pen's, so the absolute station-to-bed
  registration cancels out — you never have to align the camera to the bed.
- The offset is applied as a pure translation of that pen's strokes during
  G-code generation; with every offset at `0` the output is byte-identical to
  the offset-free path.

Full design notes:
[`docs/adr/0005-camera-tip-offset.md`](../docs/adr/0005-camera-tip-offset.md)
and [`docs/camera_tip_offset.md`](../docs/camera_tip_offset.md).

---

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| *No tip detected* | Poor contrast or lighting; check the **Tip type** matches the pen (dark vs light); raise/lower the **dark threshold**; tighten the **ROI**; check the camera URL returns a frame |
| Wrong blob marked in the preview | Clutter in view — set an **ROI** around the tip, or improve the background |
| *Camera read failed* (502) | The camera URL is unreachable or not a JPEG/MJPEG stream |
| Light won't switch | Not running on a Pi, or the GPIO library is missing; check the GPIO availability warning; verify the pin and **active high/low** |
| Offsets look shifted by a constant | You re-measured pens without re-measuring the reference — **Reset measurements** and start from the reference |
| Measured offset jumps between tries | Noisy feed — raise **Frames to average** so each measure takes the median of several frames |
| *⚠ frames vary by N mm* warning | The averaged frames disagreed (unstable feed/lighting) — steady the mount, improve lighting, then re-measure |
| *⚠ large offset* warning | The detector likely locked onto the wrong blob — check the marked frame, tighten the **ROI**, and re-measure |
| Measure asks to load by hand | The profile changes pens manually; load the pen yourself, then Measure (auto-fetch needs a host/firmware magazine) |

---

## See also

- [Per-slot calibration](Per-Slot-Calibration.md) — the XY offset concept + manual entry
- [Pen magazine](Pen-Magazine.md)
- [Machine profiles](Machine-Profiles.md)
- [Profile format reference](../docs/profile_format.md)

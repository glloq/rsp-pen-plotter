# Host tool-change mechanisms

How the **host magazine** mode (`ToolingMode.HOST_MACRO`, UI mode "🤖 Magasin
host") changes pens. The host (the Pi) emits a plain-G-code sequence — moves,
servo `M280`, optional `G0 Z`, `G4` dwell — so **no firmware change** is needed
on the plotter.

A single step engine
(`HostMacroStrategy._compile_swap`) drives every mechanism; the
`HostSwapPlan.mechanism` field selects the editor preset, the labels, and (with
`lock_mode`) how the coupling is driven. Adding a mechanism is therefore mostly
a preset + a couple of metadata fields, not a new code path.

## The model

`HostSwapPlan` (see `backend/pen_plotter/domain/capability.py` and the mirror in
`frontend/src/domain/capability/schemas.ts`):

| field | meaning |
|---|---|
| `mechanism` | `"rack"` \| `"dock"` — which physical changer is bolted on (the **magazine type**). Default `"rack"` (back-compat). |
| `lock_mode` | `"command"` \| `"motion"` — the **action type**: how the pen/tool is grabbed & held. Applies to both mechanisms. |
| `steps` | the ordered high-level blocks (see below). |
| per-pen `position` | each slot/dock engagement point (X/Y), stored on the `PenSlot`. |
| `clearance_*` | the approach offset / insertion hop (axis, dir, mm). |
| `grab_command` / `drop_command` | the latch primitive (clamp close/open, or dock lock/unlock). |
| `head_up_command` / `head_down_command`, `safe_z_mm` / `engage_z_mm` | head height for racks (servo or real Z). |

Step kinds (`HostSwapStep.kind`): `head_up`, `head_down`, `move_to_old_slot`,
`move_to_new_slot`, `advance_to_slot`, `retract_from_slot`, `grab`, `release`,
`dwell`, `raw`. The compiler fills `move_*`/`advance`/`retract` from each pen's
calibrated position + the clearance vector; `grab`/`release` emit the latch
commands; `dwell` adds a host-side pause; `raw` is the escape hatch.

## Mechanism 1 — gripper rack (`mechanism: "rack"`)

A single tool-holder on the carriage carries one pen at a time. Pens are parked
in a linear rack. A clamp/gripper (servo) closes to take a pen and opens to drop
it. Engagement is **vertical**: the head lowers into a slot, the gripper acts,
the head lifts.

- **Action** (`lock_mode`): `command` → a servo gripper (`grab`/`release` emit
  `grab_command`/`drop_command`); `motion` → a friction / magnetic holder that
  needs no command (the grab is the advance/retract motion).
- `head_up`/`head_down` → magazine servo override or `G0 Z` (the rack often sits
  higher than the paper).
- `clearance` → how far to back out of a slot before travelling sideways so the
  head clears the neighbouring pens.

Default sequence: `head_up → move_to_old_slot → advance → release → retract →
move_to_new_slot → advance → grab → retract → head_down`.

## Mechanism 2 — kinematic dock (`mechanism: "dock"`)

Each pen+holder is a **whole tool** parked in a fixed dock (think
Jubilee / E3D tool-changer). The head couples to one tool at a time. Engagement
is **horizontal**: the head slides into the dock to seat the kinematic coupling
and slides back out — so the default dock sequence has **no `head_up`/`head_down`**,
and `clearance_mm` is the *dock entry depth* rather than a side clearance.

`grab`/`release` mean **lock**/**unlock** the coupling. Two locking modes:

- **`lock_mode: "motion"`** (default) — a magnetic / purely kinematic coupling.
  The lock *is* the advance/retract motion, so `grab`/`release` emit **no
  command**. The compiler suppresses them even if a stale command is left on the
  plan, and the Save validation does not require a latch command.
- **`lock_mode: "command"`** — a servo / motorised latch. `grab`/`release` emit
  `grab_command`/`drop_command`.

Default sequence: `move_to_old_slot → advance → release → retract →
move_to_new_slot → advance → grab → retract` (approach dock, slide in to seat,
unlock, back out leaving the tool; approach the next dock, slide in, lock, pull
the new tool out).

### Why this fits the existing engine

A dock swap is the same primitive shape as a rack swap with the vertical
head moves dropped and `grab`/`release` reinterpreted as lock/unlock. The only
behavioural addition in the compiler is suppressing the latch command for any
`motion` action (`strategies.py`); everything else is preset + labels + a
relaxed Save check.

## The editor (host mode)

The host editor presents a guided flow rather than a flat dump of fields:

1. **① Magazine type** — rack vs dock cards.
2. **② Action type** — `command` vs `motion` cards, labelled per mechanism
   (rack: *servo gripper* / *mechanical · magnetic hold*; dock: *motorised
   latch* / *magnetic · kinematic*). Maps to `lock_mode`.
3. **③ Positions** — per-slot X/Y + clearance / dock entry depth.
4. **④ Heights** — magazine servo angle and/or real Z axis.
5. **⑤ Sequence** — the generated, editable step list. Kept visible so power
   users can fine-tune; the advanced latch-command block (only for a `command`
   action) sits below it.

Picking a magazine type loads its preset sequence + a sensible default action
(rack → command, dock → motion). Switching the action to `command` re-seeds the
latch commands if empty; switching to `motion` hides them (no command needed).

## Extending further

Other host mechanisms (multi-actuator bank, host-driven carousel) would slot in
the same way: a new `mechanism` value, a preset sequence, and — only if a step
can't be expressed by the existing kinds — a new `HostSwapStep.kind`. Keep the
single compiler; avoid per-mechanism branches beyond the latch suppression
above.

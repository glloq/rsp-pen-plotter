"""Build immediate-control G-code from a machine profile.

Jog and homing commands depend only on the profile's dialect and speeds, so
they live here rather than in any plotter-specific code.
"""

from __future__ import annotations

from pen_plotter.models import MachineProfile


def jog_command(
    dx_mm: float, dy_mm: float, profile: MachineProfile, dz_mm: float = 0.0
) -> list[str]:
    """Build a relative jog move.

    Args:
        dx_mm: Relative X displacement in millimeters.
        dy_mm: Relative Y displacement in millimeters.
        profile: The target machine profile (for travel speed).
        dz_mm: Relative Z displacement in millimeters for a motorised Z
            axis. Added to the move only when non-zero so X/Y-only machines
            never see a spurious ``Z`` word.

    Returns:
        The G-code lines for a relative jog, restoring absolute mode.
    """
    feed = profile.travel_speed_mm_s * 60.0
    move = f"G1 X{dx_mm:.3f} Y{dy_mm:.3f}"
    if dz_mm:
        move += f" Z{dz_mm:.3f}"
    move += f" F{feed:.1f}"
    return ["G91", move, "G90"]


def goto_command(
    x_mm: float, y_mm: float, profile: MachineProfile, z_mm: float | None = None
) -> list[str]:
    """Build an absolute move to a workspace position.

    The pen is lifted first so the move never draws, and absolute mode is
    asserted in case a prior relative jog left the controller in G91.

    Args:
        x_mm: Absolute X target in millimeters.
        y_mm: Absolute Y target in millimeters.
        profile: The target machine profile (for travel speed and pen-up).
        z_mm: Optional absolute Z target for a motorised Z axis. Added to the
            move only when given so X/Y-only machines never see a ``Z`` word.

    Returns:
        The G-code lines for an absolute travel move.
    """
    feed = profile.travel_speed_mm_s * 60.0
    move = f"G1 X{x_mm:.3f} Y{y_mm:.3f}"
    if z_mm is not None:
        move += f" Z{z_mm:.3f}"
    move += f" F{feed:.1f}"
    return [
        "G90",
        profile.pen_up_command,
        move,
    ]


def home_command(profile: MachineProfile, axis: str | None = None) -> list[str]:
    """Build a homing command appropriate for the profile's dialect.

    Args:
        profile: The target machine profile.
        axis: Optional single axis to home (``"X"``, ``"Y"`` or ``"Z"``).
            ``None`` homes all axes (the default). Single-axis homing maps to
            ``$HX`` (GRBL) / ``G28 X`` (Marlin/Klipper); on a dialect without
            firmware homing it parks that axis at the workspace minimum (a
            ``Z`` request just raises the pen, the closest analogue).

    Returns:
        The G-code lines that home the requested axis (or the whole machine).
    """
    ax = (axis or "").strip().upper() or None
    if profile.gcode_dialect == "grbl":
        return [f"$H{ax}"] if ax in ("X", "Y", "Z") else ["$H"]
    if profile.gcode_dialect in ("marlin", "klipper"):
        return [f"G28 {ax}"] if ax in ("X", "Y", "Z") else ["G28 X Y"]
    # Fallback (ebb / custom): no firmware homing — park instead.
    lines = ["G90", profile.pen_up_command]
    if ax == "X":
        lines.append(f"G0 X{profile.workspace.x_min:.3f}")
    elif ax == "Y":
        lines.append(f"G0 Y{profile.workspace.y_min:.3f}")
    elif ax == "Z":
        pass  # pen already raised above — the closest thing to a "Z home"
    else:
        lines.append(f"G0 X{profile.workspace.x_min:.3f} Y{profile.workspace.y_min:.3f}")
    return lines

"""Build immediate-control G-code from a machine profile.

Jog and homing commands depend only on the profile's dialect and speeds, so
they live here rather than in any plotter-specific code.
"""

from __future__ import annotations

from pen_plotter.models import MachineProfile


def jog_command(dx_mm: float, dy_mm: float, profile: MachineProfile) -> list[str]:
    """Build a relative jog move.

    Args:
        dx_mm: Relative X displacement in millimeters.
        dy_mm: Relative Y displacement in millimeters.
        profile: The target machine profile (for travel speed).

    Returns:
        The G-code lines for a relative jog, restoring absolute mode.
    """
    feed = profile.travel_speed_mm_s * 60.0
    return [
        "G91",
        f"G1 X{dx_mm:.3f} Y{dy_mm:.3f} F{feed:.1f}",
        "G90",
    ]


def goto_command(x_mm: float, y_mm: float, profile: MachineProfile) -> list[str]:
    """Build an absolute move to a workspace position.

    The pen is lifted first so the move never draws, and absolute mode is
    asserted in case a prior relative jog left the controller in G91.

    Args:
        x_mm: Absolute X target in millimeters.
        y_mm: Absolute Y target in millimeters.
        profile: The target machine profile (for travel speed and pen-up).

    Returns:
        The G-code lines for an absolute travel move.
    """
    feed = profile.travel_speed_mm_s * 60.0
    return [
        "G90",
        profile.pen_up_command,
        f"G1 X{x_mm:.3f} Y{y_mm:.3f} F{feed:.1f}",
    ]


def home_command(profile: MachineProfile) -> list[str]:
    """Build a homing command appropriate for the profile's dialect.

    Args:
        profile: The target machine profile.

    Returns:
        The G-code lines that home the machine.
    """
    if profile.gcode_dialect == "grbl":
        return ["$H"]
    if profile.gcode_dialect in ("marlin", "klipper"):
        return ["G28 X Y"]
    return [
        "G90",
        profile.pen_up_command,
        f"G0 X{profile.workspace.x_min:.3f} Y{profile.workspace.y_min:.3f}",
    ]

from pathlib import Path

import yaml

from pen_plotter.models import MachineProfile

PROFILE_PATH = Path(__file__).parent.parent / "pen_plotter" / "profiles" / "custom_plotter.yaml"


def test_custom_plotter_profile_parses() -> None:
    data = yaml.safe_load(PROFILE_PATH.read_text())
    profile = MachineProfile.model_validate(data)
    assert profile.name == "Custom CoreXY A3"
    assert profile.workspace.x_max == 300.0
    assert profile.workspace.y_max == 420.0
    assert profile.pen_slot_count == 6
    assert profile.gcode_dialect == "grbl"

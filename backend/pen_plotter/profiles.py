"""Machine profile loading.

Reads YAML profile files from the ``profiles`` directory and validates them
against :class:`~pen_plotter.models.MachineProfile`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pen_plotter.models import MachineProfile

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


def load_profiles(directory: Path = PROFILES_DIR) -> list[MachineProfile]:
    """Load and validate every profile in a directory.

    Args:
        directory: Directory containing ``*.yaml`` profile files.

    Returns:
        Profiles sorted by name. Invalid or unreadable files are skipped.
    """
    profiles: list[MachineProfile] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            profiles.append(MachineProfile.model_validate(data))
        except (yaml.YAMLError, ValueError, OSError):
            continue
    return sorted(profiles, key=lambda profile: profile.name)


def get_profile(name: str, directory: Path = PROFILES_DIR) -> MachineProfile | None:
    """Return the profile with the given name, or ``None`` if not found.

    Args:
        name: The profile's ``name`` field.
        directory: Directory to search.

    Returns:
        The matching profile, or ``None``.
    """
    for profile in load_profiles(directory):
        if profile.name == name:
            return profile
    return None

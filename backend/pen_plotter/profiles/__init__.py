"""Machine profile loading, import, and export.

Profiles are read from the bundled package directory and from a writable user
directory (``OMNIPLOT_PROFILES_DIR``, default ``<backend>/data/profiles``).
User profiles override bundled ones with the same name, and imports are written
to the user directory so the installed package stays read-only.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from pen_plotter.models import MachineProfile

BUNDLED_DIR = Path(__file__).resolve().parent
USER_DIR = Path(
    os.environ.get("OMNIPLOT_PROFILES_DIR", BUNDLED_DIR.parent.parent / "data" / "profiles")
)

# Backwards-compatible alias used by tests and callers that pass an explicit dir.
PROFILES_DIR = BUNDLED_DIR


def _load_dir(directory: Path) -> dict[str, MachineProfile]:
    """Load valid profiles from a directory, keyed by name. Missing dir → empty."""
    found: dict[str, MachineProfile] = {}
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = MachineProfile.model_validate(yaml.safe_load(path.read_text()))
        except (yaml.YAMLError, ValueError, OSError):
            continue
        found[profile.name] = profile
    return found


def load_profiles(directory: Path | None = None) -> list[MachineProfile]:
    """Load and validate available profiles.

    Args:
        directory: If given, load only from this directory. Otherwise load the
            bundled profiles plus any user profiles (the latter take precedence).

    Returns:
        Profiles sorted by name.
    """
    if directory is not None:
        merged = _load_dir(directory)
    else:
        merged = _load_dir(BUNDLED_DIR)
        merged.update(_load_dir(USER_DIR))
    return sorted(merged.values(), key=lambda profile: profile.name)


def get_profile(name: str, directory: Path | None = None) -> MachineProfile | None:
    """Return the profile with the given name, or ``None`` if not found.

    Args:
        name: The profile's ``name`` field.
        directory: Optional directory to restrict the search to.

    Returns:
        The matching profile, or ``None``.
    """
    for profile in load_profiles(directory):
        if profile.name == name:
            return profile
    return None


def _slug(name: str) -> str:
    """Turn a profile name into a safe filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "profile"


def _user_file_for(name: str, directory: Path) -> Path | None:
    """Return the user-dir file whose stored profile name equals ``name``.

    Filenames are derived from a lossy slug, so distinct names can collide on
    the same stem. To map a name back to its file reliably we match on the
    profile's own ``name`` field rather than trusting the slug.
    """
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.yaml")):
        try:
            profile = MachineProfile.model_validate(yaml.safe_load(path.read_text()))
        except (yaml.YAMLError, ValueError, OSError):
            continue
        if profile.name == name:
            return path
    return None


def _free_path(name: str, directory: Path) -> Path:
    """Pick a writable path for a new profile, avoiding clobbering a different one.

    If the natural slug file is already taken by a profile with a *different*
    name, a numeric suffix is appended so the two profiles do not share a file.
    """
    stem = _slug(name)
    candidate = directory / f"{stem}.yaml"
    counter = 2
    while candidate.is_file():
        candidate = directory / f"{stem}_{counter}.yaml"
        counter += 1
    return candidate


def export_profile_yaml(profile: MachineProfile) -> str:
    """Serialize a profile to YAML."""
    return yaml.safe_dump(profile.model_dump(), sort_keys=False)


def save_profile(profile: MachineProfile, directory: Path = USER_DIR) -> Path:
    """Persist a profile to the user directory as YAML.

    Existing profiles are updated in place (matched by name); new profiles get
    a fresh filename that never overwrites a differently-named profile that
    happens to share a slug.

    Args:
        profile: The validated profile to save.
        directory: Target directory (created if needed).

    Returns:
        The path the profile was written to.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = _user_file_for(profile.name, directory) or _free_path(profile.name, directory)
    path.write_text(export_profile_yaml(profile))
    return path


def delete_profile(name: str, directory: Path = USER_DIR) -> bool:
    """Delete a user profile by its exact name.

    Only profiles stored in the user directory can be removed; bundled
    profiles are read-only.

    Returns:
        ``True`` if a user profile file was removed, ``False`` otherwise.
    """
    path = _user_file_for(name, directory)
    if path is not None:
        path.unlink()
        return True
    return False

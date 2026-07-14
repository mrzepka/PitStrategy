"""Overlay display settings -- which rows/columns/panels to show. Persisted
to a JSON file under %APPDATA% (not the working directory) since this is
meant to run as a standalone app launched by double-clicking a shortcut,
where the working directory isn't something the user controls.
"""
import os
from pathlib import Path

from pydantic import BaseModel, Field


def _settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home())) / "PitStrategy"
    base.mkdir(parents=True, exist_ok=True)
    return base / "settings.json"


class OverlaySettings(BaseModel):
    # Fuel-rate rows.
    show_last_lap: bool = True
    show_max_fuel: bool = True
    show_avg_fuel: bool = True
    show_quali_fuel: bool = True
    # Per-row figures (columns).
    show_col_laps_left: bool = True
    show_col_stint: bool = True
    show_col_finish: bool = True
    show_col_runout: bool = True
    # Other panels.
    show_fuel_gauge: bool = True
    show_fuel_targets: bool = True
    show_tires: bool = True
    show_relative: bool = True
    show_final_window: bool = True
    # Overlay zoom, set by dragging overlay.js's #resize-grip. Bounds match
    # overlay.js's MIN_SCALE/MAX_SCALE -- kept in sync by hand since this is
    # the only place outside JS that needs to know them.
    zoom: float = Field(default=1.0, ge=0.6, le=2.0)


def load_settings() -> OverlaySettings:
    path = _settings_path()
    if not path.exists():
        return OverlaySettings()
    try:
        return OverlaySettings.model_validate_json(path.read_text())
    except (OSError, ValueError):
        # Corrupt/unreadable file -- fall back to defaults rather than
        # crashing startup over a settings file.
        return OverlaySettings()


def save_settings(settings: OverlaySettings) -> None:
    _settings_path().write_text(settings.model_dump_json(indent=2))

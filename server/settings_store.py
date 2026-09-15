"""Overlay display settings -- which rows/columns/panels to show. Persisted
to a JSON file under %APPDATA% (not the working directory) since this is
meant to run as a standalone app launched by double-clicking a shortcut,
where the working directory isn't something the user controls.
"""
import os
from pathlib import Path
from typing import Literal

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
    # Auto pit fuel: the moment StrategyEngine detects the player's car
    # entering pit road, it sends (via iRacing's SDK pit-service broadcast)
    # enough fuel to finish the race at the selected rate -- reusing
    # whichever of the four "Fuel calculations (rows)" figures
    # auto_fuel_source names, rather than a manually-typed liters value.
    # Off by default -- this actually submits a real request to the sim,
    # not just a display feature, so it shouldn't ever fire without the
    # user explicitly opting in. auto_fuel_source is only ever set by
    # settings.js to one of the four rows currently checked *on* in the
    # "Fuel calculations (rows)" section above; settings.js defaults it to
    # the first checked row itself (rather than leaving it None) whenever
    # nothing valid is currently selected, and forces auto_fuel_enabled
    # back off if every row gets unchecked, so None here should only ever
    # be transient mid-request, never a steady state with auto_fuel_enabled
    # still True.
    auto_fuel_enabled: bool = False
    auto_fuel_source: Literal["last_lap", "max_fuel", "avg_fuel", "quali_fuel"] | None = None
    # Extra laps' worth of fuel (at auto_fuel_source's rate) requested on top
    # of the exact amount needed to finish -- a safety margin against the
    # rate estimate coming in a little light. Adjustable in 0.1-lap steps
    # (settings.js's step="0.1" number input) either direction; negative
    # deliberately requests less than the exact finish amount.
    auto_fuel_buffer_laps: float = Field(default=0.0, ge=-5.0, le=20.0)
    # Display-only -- every value stays in liters everywhere else (fuel.py's
    # tracking math, the SDK pit-fuel request, the websocket payload).
    # overlay.js converts liters -> US gallons at render time when this is
    # "gallons", purely for the text shown on screen.
    fuel_units: Literal["liters", "gallons"] = "liters"


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

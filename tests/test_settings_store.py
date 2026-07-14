import json

import pytest

from server.settings_store import OverlaySettings, _settings_path, load_settings, save_settings


@pytest.fixture(autouse=True)
def isolated_appdata(monkeypatch, tmp_path):
    # Every test in this file gets its own throwaway %APPDATA%, so none of
    # them ever touch the real user's settings.json.
    monkeypatch.setenv("APPDATA", str(tmp_path))


def test_load_settings_returns_defaults_when_file_missing():
    assert load_settings() == OverlaySettings()


def test_save_then_load_round_trips():
    original = OverlaySettings(show_tires=False, show_col_finish=False, show_relative=False)
    save_settings(original)
    assert load_settings() == original


def test_save_creates_parent_directory():
    path = _settings_path()
    save_settings(OverlaySettings())
    assert path.exists()


def test_load_settings_falls_back_to_defaults_on_corrupt_json():
    _settings_path().write_text("{not valid json")
    assert load_settings() == OverlaySettings()


def test_load_settings_ignores_unknown_fields():
    _settings_path().write_text(json.dumps({"show_tires": False, "some_future_field": "x"}))
    settings = load_settings()
    assert settings.show_tires is False
    assert settings.show_last_lap is True


def test_load_settings_fills_defaults_for_missing_fields():
    # A settings.json written by an older version of the app, before a new
    # field existed, shouldn't crash -- the new field should just fall back
    # to its default rather than the whole file being rejected.
    _settings_path().write_text(json.dumps({"show_tires": False}))
    settings = load_settings()
    assert settings.show_tires is False
    assert settings.show_relative is True


def test_zoom_round_trips():
    original = OverlaySettings(zoom=1.4)
    save_settings(original)
    assert load_settings().zoom == 1.4


def test_load_settings_falls_back_to_defaults_when_zoom_out_of_bounds():
    # zoom is clamped 0.6-2.0 (matching overlay.js's MIN_SCALE/MAX_SCALE) --
    # an out-of-range value fails pydantic validation entirely, same
    # corrupt-file-fallback path as invalid JSON, not silently clamped.
    _settings_path().write_text(json.dumps({"zoom": 5.0}))
    assert load_settings() == OverlaySettings()

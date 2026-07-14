from core.fuel import FuelTracker


def test_no_data_yet_returns_none():
    tracker = FuelTracker()
    snap = tracker.snapshot()
    assert snap.avg_fuel_per_lap is None
    assert snap.laps_remaining_on_fuel is None


def test_tracks_steady_fuel_usage():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)
    tracker.update(lap=2, fuel_level=55.0)
    tracker.update(lap=3, fuel_level=52.5)

    snap = tracker.snapshot()
    assert snap.avg_fuel_per_lap == 2.5
    assert snap.laps_remaining_on_fuel == 52.5 / 2.5


def test_refuel_is_discarded_as_outlier():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # used 2.5
    tracker.update(lap=2, fuel_level=65.0)  # refueled mid-lap -- should be discarded
    tracker.update(lap=3, fuel_level=62.5)  # used 2.5 again

    snap = tracker.snapshot()
    assert snap.avg_fuel_per_lap == 2.5


def test_history_len_bounds_the_rolling_window():
    tracker = FuelTracker(history_len=2)
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=58.0)  # used 2
    tracker.update(lap=2, fuel_level=54.0)  # used 4
    tracker.update(lap=3, fuel_level=50.0)  # used 4

    snap = tracker.snapshot()
    # only the last 2 samples (4, 4) should be averaged
    assert snap.avg_fuel_per_lap == 4.0


def test_tank_capacity_is_only_set_when_positive():
    tracker = FuelTracker()
    tracker.set_tank_capacity(None)
    tracker.set_tank_capacity(0)
    assert tracker.snapshot().tank_capacity is None
    tracker.set_tank_capacity(65.0)
    assert tracker.snapshot().tank_capacity == 65.0


def test_max_fuel_per_lap_survives_leaving_the_rolling_window():
    tracker = FuelTracker(history_len=2)
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=55.0)  # used 5 -- the session peak
    tracker.update(lap=2, fuel_level=52.5)  # used 2.5
    tracker.update(lap=3, fuel_level=50.0)  # used 2.5
    tracker.update(lap=4, fuel_level=47.5)  # used 2.5 -- lap 1's 5.0 has aged out of the rolling window

    snap = tracker.snapshot()
    assert snap.avg_fuel_per_lap == 2.5  # rolling average no longer sees the lap-1 spike
    assert snap.max_fuel_per_lap == 5.0  # but the session max still remembers it


def test_max_fuel_per_lap_ignores_refuel_outliers():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # used 2.5
    tracker.update(lap=2, fuel_level=65.0)  # refueled -- must not register as -7.5 max
    tracker.update(lap=3, fuel_level=62.0)  # used 3.0

    snap = tracker.snapshot()
    assert snap.max_fuel_per_lap == 3.0


def test_reset_clears_max_fuel_per_lap():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=55.0)
    assert tracker.snapshot().max_fuel_per_lap == 5.0
    tracker.reset()
    assert tracker.snapshot().max_fuel_per_lap is None


def test_fuel_limit_defaults_to_auto_detected_tank_capacity():
    tracker = FuelTracker()
    tracker.set_tank_capacity(65.0)
    snap = tracker.snapshot()
    assert snap.tank_capacity == 65.0
    assert snap.max_fuel_l == 65.0
    assert snap.fuel_pct_available == 100.0


def test_fuel_limit_manual_liters_only_does_not_need_a_known_tank_size():
    # No set_tank_capacity() call at all -- simulates not knowing the car's
    # actual tank, just a known usable-liters number.
    tracker = FuelTracker()
    tracker.set_fuel_limit(max_fuel_l=21.25)
    snap = tracker.snapshot()
    assert snap.tank_capacity == 21.25
    assert snap.fuel_pct_available == 100.0  # untouched, still a no-op


def test_fuel_limit_percentage_scales_auto_detected_tank():
    tracker = FuelTracker()
    tracker.set_tank_capacity(65.0)
    tracker.set_fuel_limit(pct_available=50.0)  # no override -- scales the detected 65L
    snap = tracker.snapshot()
    assert snap.tank_capacity == 32.5
    assert snap.max_fuel_l == 65.0


def test_fuel_limit_override_and_percentage_combine():
    tracker = FuelTracker()
    tracker.set_tank_capacity(65.0)  # should be superseded by the override below
    tracker.set_fuel_limit(max_fuel_l=85.0, pct_available=25.0)
    snap = tracker.snapshot()
    assert snap.max_fuel_l == 85.0
    assert snap.tank_capacity == 21.25


def test_fuel_limit_ignores_non_positive_values():
    tracker = FuelTracker()
    tracker.set_tank_capacity(65.0)
    tracker.set_fuel_limit(max_fuel_l=0, pct_available=-5)
    snap = tracker.snapshot()
    assert snap.max_fuel_l == 65.0  # override of 0 treated as "no override"
    assert snap.fuel_pct_available == 100.0  # negative pct treated as "no scaling"


def test_last_lap_fuel_per_lap_is_the_most_recent_sample_not_the_average():
    tracker = FuelTracker()
    assert tracker.snapshot().last_lap_fuel_per_lap is None  # no laps completed yet

    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # used 2.5
    assert tracker.snapshot().last_lap_fuel_per_lap == 2.5

    tracker.update(lap=2, fuel_level=54.0)  # used 3.5 -- a heavier lap
    snap = tracker.snapshot()
    assert snap.last_lap_fuel_per_lap == 3.5
    assert snap.avg_fuel_per_lap == 3.0  # (2.5 + 3.5) / 2 -- the two differ as expected


def test_last_lap_fuel_per_lap_ignores_refuel_outlier():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # used 2.5
    tracker.update(lap=2, fuel_level=65.0)  # refueled -- discarded, not recorded as "last lap"
    assert tracker.snapshot().last_lap_fuel_per_lap == 2.5


def test_clear_fuel_limit_reverts_to_auto_detected():
    tracker = FuelTracker()
    tracker.set_tank_capacity(65.0)
    tracker.set_fuel_limit(max_fuel_l=85.0, pct_available=25.0)
    assert tracker.snapshot().tank_capacity == 21.25

    tracker.clear_fuel_limit()
    snap = tracker.snapshot()
    assert snap.tank_capacity == 65.0
    assert snap.max_fuel_l == 65.0
    assert snap.fuel_pct_available == 100.0


def test_stint_start_fuel_level_is_none_with_no_data():
    tracker = FuelTracker()
    assert tracker.snapshot().stint_start_fuel_level is None


def test_stint_start_fuel_level_captured_on_first_sample():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    assert tracker.snapshot().stint_start_fuel_level == 60.0


def test_stint_start_fuel_level_stays_fixed_through_a_stint():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # normal lap -- not a refuel
    tracker.update(lap=2, fuel_level=55.0)  # normal lap -- not a refuel
    snap = tracker.snapshot()
    # Stays at the original 60.0 even though current_fuel_level has dropped.
    assert snap.stint_start_fuel_level == 60.0
    assert snap.current_fuel_level == 55.0


def test_stint_start_fuel_level_updates_on_refuel():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    tracker.update(lap=1, fuel_level=57.5)  # used 2.5
    tracker.update(lap=2, fuel_level=57.5)  # used 2.5

    tracker.update(lap=3, fuel_level=65.0)  # refueled -- new stint starts with 65.0
    assert tracker.snapshot().stint_start_fuel_level == 65.0

    tracker.update(lap=4, fuel_level=62.5)  # normal lap in the new stint
    assert tracker.snapshot().stint_start_fuel_level == 65.0  # still fixed at the new value


def test_stint_start_fuel_level_resets_on_reset():
    tracker = FuelTracker()
    tracker.update(lap=0, fuel_level=60.0)
    assert tracker.snapshot().stint_start_fuel_level == 60.0

    tracker.reset()
    assert tracker.snapshot().stint_start_fuel_level is None

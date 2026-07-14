from core.leader_pace import LeaderPaceTracker


def test_no_samples_yet():
    tracker = LeaderPaceTracker()
    state = tracker.snapshot()
    assert state.avg_lap_time_s is None
    assert state.samples == 0


def test_ignores_none_and_non_positive_values():
    tracker = LeaderPaceTracker()
    tracker.update(None)
    tracker.update(0)
    tracker.update(-5.0)
    state = tracker.snapshot()
    assert state.avg_lap_time_s is None
    assert state.samples == 0


def test_repeated_identical_value_only_counts_once():
    tracker = LeaderPaceTracker()
    tracker.update(90.0)
    tracker.update(90.0)  # same value across several ticks -- not a new lap
    tracker.update(90.0)
    state = tracker.snapshot()
    assert state.samples == 1
    assert state.avg_lap_time_s == 90.0


def test_averages_across_distinct_laps():
    tracker = LeaderPaceTracker()
    for lap_time in (90.0, 91.0, 89.0):
        tracker.update(lap_time)
    state = tracker.snapshot()
    assert state.samples == 3
    assert state.avg_lap_time_s == 90.0


def test_rolling_window_drops_oldest():
    tracker = LeaderPaceTracker(history_len=3)
    for lap_time in (100.0, 91.0, 90.0, 89.0):  # 100.0 should drop off the front
        tracker.update(lap_time)
    state = tracker.snapshot()
    assert state.samples == 3
    assert state.avg_lap_time_s == 90.0


def test_leader_change_keeps_averaging_new_values():
    # A position change at the front shouldn't break the tracker -- it just
    # keeps averaging whatever lap-time values it's fed.
    tracker = LeaderPaceTracker()
    tracker.update(90.0)
    tracker.update(88.0)  # new leader, different pace
    state = tracker.snapshot()
    assert state.samples == 2
    assert state.avg_lap_time_s == 89.0

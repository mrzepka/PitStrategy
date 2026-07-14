from core.session_baseline import SessionTransitionTracker, is_qualifying_session


def test_is_qualifying_session_matches_common_iracing_labels():
    assert is_qualifying_session("Lone Qualify")
    assert is_qualifying_session("Open Qualify")
    assert is_qualifying_session("qualify")
    assert not is_qualifying_session("Race")
    assert not is_qualifying_session("Practice")
    assert not is_qualifying_session("Warmup")
    assert not is_qualifying_session(None)
    assert not is_qualifying_session("")


def test_transition_tracker_ignores_first_observation():
    tracker = SessionTransitionTracker()
    assert tracker.check(0, "Lone Qualify") is None


def test_transition_tracker_fires_on_session_num_change():
    tracker = SessionTransitionTracker()
    tracker.check(0, "Lone Qualify")
    result = tracker.check(1, "Race")
    assert result == "Lone Qualify"


def test_transition_tracker_does_not_fire_while_session_num_unchanged():
    tracker = SessionTransitionTracker()
    tracker.check(0, "Lone Qualify")
    result = tracker.check(0, "Lone Qualify")
    assert result is None


def test_transition_tracker_only_reports_immediately_previous_session():
    tracker = SessionTransitionTracker()
    tracker.check(0, "Practice")
    tracker.check(1, "Lone Qualify")
    result = tracker.check(2, "Race")
    assert result == "Lone Qualify"


def test_transition_tracker_handles_none_session_num_gracefully():
    tracker = SessionTransitionTracker()
    tracker.check(None, None)
    result = tracker.check(None, None)
    assert result is None

from core.relative import RelativeTracker


def make_field():
    # player (idx 3) sits at position 4 in an 8-car field, positions 1..8.
    positions = [5, 3, 2, 4, 6, 1, 7, 8]  # car_idx -> position
    car_numbers = {i: f"#{i}" for i in range(8)}
    return positions, car_numbers


def test_nearest_ahead_and_behind_are_selected_and_ordered_nearest_first():
    positions, car_numbers = make_field()
    tracker = RelativeTracker()
    result = tracker.nearby_cars(
        player_car_idx=3,
        car_idx_position=positions,
        car_idx_last_lap_time=[0.0] * 8,
        car_numbers=car_numbers,
        my_last_lap_time=None,
    )
    # My position is 4. Ahead (positions 3,2,1) nearest-first -> pos3,2,1 = idx1,2,5.
    assert [c.position for c in result["ahead"]] == [3, 2, 1]
    assert [c.car_idx for c in result["ahead"]] == [1, 2, 5]
    # Behind (positions 5,6,7,8) nearest-first, only 3 shown -> pos5,6,7 = idx0,4,6.
    assert [c.position for c in result["behind"]] == [5, 6, 7]
    assert [c.car_idx for c in result["behind"]] == [0, 4, 6]


def test_gap_positions_sign():
    positions, car_numbers = make_field()
    tracker = RelativeTracker()
    result = tracker.nearby_cars(
        player_car_idx=3, car_idx_position=positions, car_idx_last_lap_time=[0.0] * 8,
        car_numbers=car_numbers, my_last_lap_time=None,
    )
    assert all(c.gap_positions < 0 for c in result["ahead"])
    assert all(c.gap_positions > 0 for c in result["behind"])


def test_fewer_than_count_cars_available_on_one_side():
    # Player in P1: nothing ahead, up to 3 behind.
    positions = [1, 2, 3, 4]
    tracker = RelativeTracker()
    result = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=positions, car_idx_last_lap_time=[0.0] * 4,
        car_numbers={}, my_last_lap_time=None,
    )
    assert result["ahead"] == []
    assert [c.position for c in result["behind"]] == [2, 3, 4]


def test_delta_to_my_last_lap_sign_and_missing_data():
    positions = [2, 1, 3]  # player idx0 = P2, idx1 = P1 (ahead), idx2 = P3 (behind)
    lap_times = [90.0, 88.0, 92.0]
    tracker = RelativeTracker()
    result = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=positions, car_idx_last_lap_time=lap_times,
        car_numbers={1: "17", 2: "44"}, my_last_lap_time=90.0,
    )
    ahead = result["ahead"][0]
    behind = result["behind"][0]
    assert ahead.last_lap_time == 88.0
    assert ahead.delta_to_my_last_lap == -2.0  # they're 2s faster than me
    assert behind.delta_to_my_last_lap == 2.0  # they're 2s slower than me

    # No my_last_lap_time available -> delta stays None even with valid rival times.
    result_no_my_time = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=positions, car_idx_last_lap_time=lap_times,
        car_numbers={1: "17", 2: "44"}, my_last_lap_time=None,
    )
    assert result_no_my_time["ahead"][0].delta_to_my_last_lap is None


def test_has_pitted_is_sticky():
    tracker = RelativeTracker()
    tracker.update_pit_status([False, True, False])
    tracker.update_pit_status([False, False, False])  # car 1 leaves pit road

    positions = [2, 1, 3]
    result = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=positions, car_idx_last_lap_time=[0.0] * 3,
        car_numbers={}, my_last_lap_time=None,
    )
    assert result["ahead"][0].has_pitted is True  # car_idx 1, still sticky
    assert result["behind"][0].has_pitted is False  # car_idx 2, never pitted


def test_reset_clears_sticky_pit_status():
    # A session transition (e.g. qualifying -> race) should clear a stop
    # made in the session that just ended -- has_pitted is only sticky
    # *within* a session, not across one.
    tracker = RelativeTracker()
    tracker.update_pit_status([False, True, False])
    tracker.reset()

    positions = [2, 1, 3]
    result = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=positions, car_idx_last_lap_time=[0.0] * 3,
        car_numbers={}, my_last_lap_time=None,
    )
    assert result["ahead"][0].has_pitted is False  # car_idx 1, cleared by reset()


def test_no_position_data_returns_empty():
    tracker = RelativeTracker()
    result = tracker.nearby_cars(
        player_car_idx=0, car_idx_position=[0, 0, 0], car_idx_last_lap_time=[0.0] * 3,
        car_numbers={}, my_last_lap_time=None,
    )
    assert result == {"ahead": [], "behind": []}

    result_none_idx = tracker.nearby_cars(
        player_car_idx=None, car_idx_position=[1, 2, 3], car_idx_last_lap_time=[0.0] * 3,
        car_numbers={}, my_last_lap_time=None,
    )
    assert result_none_idx == {"ahead": [], "behind": []}

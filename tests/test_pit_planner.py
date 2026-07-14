import pytest

from core.fuel import FuelState
from core.pit_planner import compute_live_strategy, current_stint_fuel_to_add, plan_race, upcoming_pit_windows
from core.tires import TireState


def make_states(fuel_laps=None, tire_laps=None):
    fuel = FuelState(avg_fuel_per_lap=2.5, current_fuel_level=10.0, laps_remaining_on_fuel=fuel_laps,
                      tank_capacity=65.0, samples=5)
    tires = TireState(worst_wear_remaining=0.3, avg_wear_per_lap=0.02, laps_remaining_on_tires=tire_laps,
                       samples=5)
    return fuel, tires


def test_collecting_data_when_no_trackers_have_data():
    fuel, tires = make_states(fuel_laps=None, tire_laps=None)
    result = compute_live_strategy(current_lap=5, fuel=fuel, tires=tires, laps_remaining_in_race=20)
    assert result.status == "collecting_data"


def test_fuel_is_binding_constraint():
    fuel, tires = make_states(fuel_laps=2.0, tire_laps=10.0)
    result = compute_live_strategy(current_lap=5, fuel=fuel, tires=tires, laps_remaining_in_race=20)
    assert result.binding_constraint == "fuel"
    assert result.pit_by_lap == 7  # 5 + floor(2.0)
    assert result.status == "yellow"


def test_red_status_when_stop_is_imminent():
    fuel, tires = make_states(fuel_laps=0.5, tire_laps=10.0)
    result = compute_live_strategy(current_lap=5, fuel=fuel, tires=tires, laps_remaining_in_race=20)
    assert result.status == "red"


def test_no_stop_needed_when_race_ends_first():
    fuel, tires = make_states(fuel_laps=10.0, tire_laps=10.0)
    result = compute_live_strategy(current_lap=30, fuel=fuel, tires=tires, laps_remaining_in_race=5)
    assert result.status == "no_stop_needed"
    assert result.pit_by_lap is None


def test_earliest_pit_lap_worked_example():
    # M_fuel = 65/2.5 = 26, M_tires = 1/0.02 = 50 -> fresh capacity M = 26.
    fuel, tires = make_states(fuel_laps=15.0, tire_laps=100.0)
    result = compute_live_strategy(current_lap=5, fuel=fuel, tires=tires, laps_remaining_in_race=90)
    assert result.pit_by_lap == 20
    assert result.earliest_pit_lap == 17


def test_earliest_pit_lap_none_without_fresh_capacity_data():
    fuel = FuelState(avg_fuel_per_lap=None, current_fuel_level=10.0, laps_remaining_on_fuel=None,
                      tank_capacity=None, samples=0)
    tires = TireState(worst_wear_remaining=0.7, avg_wear_per_lap=None, laps_remaining_on_tires=10.0,
                       samples=1)
    result = compute_live_strategy(current_lap=5, fuel=fuel, tires=tires, laps_remaining_in_race=90)
    assert result.pit_by_lap == 15  # 5 + floor(10.0), still computable from tires alone
    assert result.earliest_pit_lap is None


def test_plan_race_simple_laps_mode():
    plan = plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=100,
        fuel_safety_margin_l=0.0,
    )
    # 65L / 2.5L/lap = 26 laps/stint -> ceil(100/26) = 4 stints -> 3 stops
    assert plan.laps_per_stint == 26
    assert plan.num_stops == 3
    assert sum(s.laps for s in plan.stints) == 100
    assert plan.stints[-1].pit_in_lap is None
    assert plan.stints[-1].fuel_to_add is None
    assert all(s.pit_in_lap is not None for s in plan.stints[:-1])


def test_plan_race_mandatory_stops_forces_more_stints():
    plan = plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=1.0,  # laps_per_stint would be huge
        race_length_laps=50,
        mandatory_stops=3,
        fuel_safety_margin_l=0.0,
    )
    assert plan.num_stops == 3
    assert len(plan.stints) == 4
    assert sum(s.laps for s in plan.stints) == 50


def test_plan_race_fuel_pct_available_shrinks_usable_capacity():
    # 85L tank, but a rule caps usable fuel to 25% -> 21.25L effective.
    plan = plan_race(
        tank_capacity_l=85.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=50,
        fuel_safety_margin_l=0.0,
        fuel_pct_available=25.0,
    )
    # floor(21.25 / 2.5) = 8, not floor(85 / 2.5) = 34.
    assert plan.laps_per_stint == 8
    for stint in plan.stints[:-1]:
        assert stint.fuel_to_add <= 21.25


def test_plan_race_fuel_pct_available_100_is_a_no_op():
    kwargs = dict(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=100,
        fuel_safety_margin_l=0.0,
    )
    without_pct = plan_race(**kwargs)
    with_pct_100 = plan_race(**kwargs, fuel_pct_available=100.0)
    assert without_pct == with_pct_100


def test_plan_race_rejects_non_positive_fuel_pct_available():
    with pytest.raises(ValueError):
        plan_race(tank_capacity_l=65, expected_fuel_per_lap_l=2.5, race_length_laps=10, fuel_pct_available=0)


def test_plan_race_time_based_mode():
    plan = plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_minutes=30,
        expected_lap_time_s=90,
    )
    # 30*60/90 = 20 laps
    assert plan.race_length_laps == 20


def test_plan_race_time_based_accounts_for_pit_stop_time():
    plan = plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_minutes=60,
        expected_lap_time_s=90,
        pit_stop_time_loss_s=30,
        fuel_safety_margin_l=0.0,
    )
    # Pit-time-blind calc would give 40 laps (3600/90); accounting for the
    # single pit stop's 30s cost against the 3600s clock shaves a lap off.
    assert plan.race_length_laps == 39
    assert plan.num_stops == 1
    # The whole plan (green-flag laps + pit time) must fit inside the
    # actual time budget -- the pre-fix version would have exceeded it.
    assert plan.total_time_s <= 60 * 60


def test_plan_race_lap_based_mode_unaffected_by_pit_stop_time():
    # When race_length_laps is given directly, pit stop time must not
    # change how many laps are planned -- a lap-based race always runs the
    # same distance regardless of how many times you stop.
    plan_no_pit_loss = plan_race(
        tank_capacity_l=65.0, expected_fuel_per_lap_l=2.5, race_length_laps=40, fuel_safety_margin_l=0.0,
    )
    plan_with_pit_loss = plan_race(
        tank_capacity_l=65.0, expected_fuel_per_lap_l=2.5, race_length_laps=40,
        pit_stop_time_loss_s=30, expected_lap_time_s=90, fuel_safety_margin_l=0.0,
    )
    assert plan_no_pit_loss.race_length_laps == plan_with_pit_loss.race_length_laps == 40


def test_plan_race_total_time_includes_pit_loss():
    plan = plan_race(
        tank_capacity_l=10.0,
        expected_fuel_per_lap_l=2.5,  # laps_per_stint ~ 4 -> several stops
        race_length_laps=20,
        expected_lap_time_s=90,
        pit_stop_time_loss_s=30,
    )
    expected_base_time = 20 * 90
    assert plan.total_time_s == expected_base_time + plan.num_stops * 30


def test_plan_race_rejects_bad_input():
    with pytest.raises(ValueError):
        plan_race(tank_capacity_l=0, expected_fuel_per_lap_l=2.5, race_length_laps=10)
    with pytest.raises(ValueError):
        plan_race(tank_capacity_l=65, expected_fuel_per_lap_l=2.5)


def _make_plan():
    # 4 stints of 25 laps each (100 laps total), fuel_to_add = 62.8 for stints 1-3.
    return plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=100,
    )


def test_current_stint_fuel_to_add_mid_stint():
    plan = _make_plan()
    assert current_stint_fuel_to_add(plan, current_lap=10) == plan.stints[0].fuel_to_add


def test_current_stint_fuel_to_add_on_pit_lap_boundary():
    plan = _make_plan()
    # Lap 25 is the pit-in lap for stint 1 -- still the upcoming stop's amount.
    assert current_stint_fuel_to_add(plan, current_lap=25) == plan.stints[0].fuel_to_add
    # Lap 26 is into stint 2.
    assert current_stint_fuel_to_add(plan, current_lap=26) == plan.stints[1].fuel_to_add


def test_current_stint_fuel_to_add_none_in_final_stint():
    plan = _make_plan()
    assert current_stint_fuel_to_add(plan, current_lap=plan.race_length_laps) is None


def test_current_stint_fuel_to_add_none_past_race_end():
    plan = _make_plan()
    assert current_stint_fuel_to_add(plan, current_lap=plan.race_length_laps + 5) is None


def test_upcoming_pit_windows_all_stints_at_race_start():
    plan = _make_plan()
    windows = upcoming_pit_windows(plan, current_lap=10)
    assert windows == plan.stints  # nothing completed yet -- the whole plan


def test_upcoming_pit_windows_drops_completed_stints():
    plan = _make_plan()
    windows = upcoming_pit_windows(plan, current_lap=26)  # into stint 2
    assert [s.stint_number for s in windows] == [2, 3, 4]
    assert windows == plan.stints[1:]


def test_upcoming_pit_windows_final_stint_only():
    plan = _make_plan()
    windows = upcoming_pit_windows(plan, current_lap=plan.race_length_laps)
    assert [s.stint_number for s in windows] == [4]
    assert windows[0].pit_in_lap is None  # the final, no-stop stint


def test_upcoming_pit_windows_empty_past_race_end():
    plan = _make_plan()
    assert upcoming_pit_windows(plan, current_lap=plan.race_length_laps + 5) == []


def test_plan_race_pit_windows_worked_example():
    # Same 100-lap/65L/2.5L/no-margin setup as test_plan_race_simple_laps_mode:
    # laps_per_stint=26, 4 stints of 25 laps each (0/25/50/75/100 boundaries).
    plan = plan_race(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=100,
        fuel_safety_margin_l=0.0,
    )
    windows = [(s.earliest_pit_lap, s.latest_pit_lap) for s in plan.stints]
    assert windows == [(22, 26), (48, 51), (74, 76), (None, None)]
    # The nominal, evenly-spaced plan lap always falls inside its own window.
    for stint in plan.stints[:-1]:
        assert stint.earliest_pit_lap <= stint.pit_in_lap <= stint.latest_pit_lap


def _worked_example_kwargs():
    # Same 100-lap/65L/2.5L/no-margin fixture as test_plan_race_pit_windows_worked_example:
    # laps_per_stint=26, default 4 stints of 25 laps each (0/25/50/75/100 boundaries).
    return dict(
        tank_capacity_l=65.0,
        expected_fuel_per_lap_l=2.5,
        race_length_laps=100,
        fuel_safety_margin_l=0.0,
    )


def test_plan_race_fuel_override_no_override_is_unaffected():
    without = plan_race(**_worked_example_kwargs())
    with_none = plan_race(**_worked_example_kwargs(), fuel_override=None)
    assert without == with_none


def test_plan_race_fuel_override_clamps_to_physical_max():
    # Requesting far more fuel than needed clamps to the physical cap
    # (laps_per_stint=26), not an unbounded value.
    plan = plan_race(**_worked_example_kwargs(), fuel_override=(1, 1000.0))
    assert plan.stints[0].laps == 25  # stint 1 itself is untouched
    assert plan.stints[1].laps == 26  # stint 2 -- clamped to the 26-lap physical max
    assert sum(s.laps for s in plan.stints) == 100


def test_plan_race_fuel_override_clamps_to_minimum_one_lap():
    # Requesting ~0 fuel still yields a valid (1-lap) next stint, not zero.
    plan = plan_race(**_worked_example_kwargs(), fuel_override=(1, 0.0))
    assert plan.stints[1].laps == 1


def test_plan_race_fuel_override_can_increase_total_stops():
    default = plan_race(**_worked_example_kwargs())
    assert default.num_stops == 3

    # Requesting a splash-and-go amount forces a shorter stint 2, which
    # (unlike clamping to the "avoid an extra stop" window) is allowed to
    # ripple into needing an additional stop later in the race.
    adjusted = plan_race(**_worked_example_kwargs(), fuel_override=(1, 3.0))
    assert adjusted.stints[1].laps == 1  # floor(3.0 / 2.5) = 1
    assert adjusted.num_stops > default.num_stops
    assert sum(s.laps for s in adjusted.stints) == 100
    assert adjusted.stints[-1].pit_in_lap is None  # still exactly one final stint


def test_plan_race_fuel_override_rejects_out_of_range_stint():
    kwargs = _worked_example_kwargs()  # 4 default stints, so valid stint_number is 1-3
    with pytest.raises(ValueError):
        plan_race(**kwargs, fuel_override=(4, 50.0))  # the final stint has no fuel to add
    with pytest.raises(ValueError):
        plan_race(**kwargs, fuel_override=(0, 50.0))
    with pytest.raises(ValueError):
        plan_race(**kwargs, fuel_override=(10, 50.0))

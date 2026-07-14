"""Combines fuel + tire trackers into a live pit window, and a standalone
pre-race what-if planner (`plan_race`).
"""
import math
from dataclasses import dataclass, field

from core.fuel import FuelState
from core.tires import TireState

# Laps-until-stop thresholds for overlay color coding.
RED_THRESHOLD_LAPS = 1.0
YELLOW_THRESHOLD_LAPS = 3.0


@dataclass
class LiveStrategyResult:
    status: str  # "collecting_data" | "no_stop_needed" | "green" | "yellow" | "red"
    laps_until_stop: float | None
    pit_by_lap: int | None  # latest -- the existing must-pit-by deadline
    binding_constraint: str | None  # "fuel" | "tires" | None
    earliest_pit_lap: int | None = None  # earliest lap that doesn't force an extra stop later


def _fresh_stint_capacity(fuel: FuelState, tires: TireState) -> float | None:
    """Max laps a *fresh* stint (full tank, new tires) could cover, from the
    same rolling averages already tracked -- used to size the pit window,
    not the current (partially used) load."""
    candidates: list[float] = []
    if fuel.tank_capacity and fuel.avg_fuel_per_lap:
        candidates.append(fuel.tank_capacity / fuel.avg_fuel_per_lap)
    if tires.avg_wear_per_lap:
        candidates.append(1.0 / tires.avg_wear_per_lap)  # wear=1.0 is fresh
    return min(candidates) if candidates else None


def compute_live_strategy(
    current_lap: int,
    fuel: FuelState,
    tires: TireState,
    laps_remaining_in_race: float | None,
) -> LiveStrategyResult:
    candidates: list[tuple[str, float]] = []
    if fuel.laps_remaining_on_fuel is not None:
        candidates.append(("fuel", fuel.laps_remaining_on_fuel))
    if tires.laps_remaining_on_tires is not None:
        candidates.append(("tires", tires.laps_remaining_on_tires))

    if not candidates:
        return LiveStrategyResult("collecting_data", None, None, None)

    binding_constraint, laps_until_stop = min(candidates, key=lambda c: c[1])

    if laps_remaining_in_race is not None and laps_remaining_in_race <= laps_until_stop:
        return LiveStrategyResult("no_stop_needed", laps_until_stop, None, binding_constraint)

    pit_by_lap = current_lap + math.floor(laps_until_stop)
    if laps_until_stop <= RED_THRESHOLD_LAPS:
        status = "red"
    elif laps_until_stop <= YELLOW_THRESHOLD_LAPS:
        status = "yellow"
    else:
        status = "green"

    earliest_pit_lap = None
    fresh_stint_laps = _fresh_stint_capacity(fuel, tires)
    if laps_remaining_in_race is not None and fresh_stint_laps:
        stops_needed = 1 + math.ceil(max(0.0, laps_remaining_in_race - laps_until_stop) / fresh_stint_laps)
        earliest_relative = max(0.0, laps_remaining_in_race - (stops_needed - 1) * fresh_stint_laps)
        earliest_pit_lap = min(current_lap + math.floor(earliest_relative), pit_by_lap)

    return LiveStrategyResult(status, laps_until_stop, pit_by_lap, binding_constraint, earliest_pit_lap)


@dataclass
class Stint:
    stint_number: int
    laps: int
    pit_in_lap: int | None  # None for the final stint (runs to the flag)
    fuel_to_add: float | None  # None for the final stint
    earliest_pit_lap: int | None = None  # None for the final stint
    latest_pit_lap: int | None = None  # None for the final stint


@dataclass
class RacePlan:
    race_length_laps: int
    laps_per_stint: int
    num_stops: int
    stints: list[Stint] = field(default_factory=list)
    total_time_s: float | None = None


def plan_race(
    tank_capacity_l: float,
    expected_fuel_per_lap_l: float,
    race_length_laps: int | None = None,
    race_length_minutes: float | None = None,
    expected_lap_time_s: float | None = None,
    tire_life_laps: int | None = None,
    mandatory_stops: int = 0,
    pit_stop_time_loss_s: float | None = None,
    fuel_safety_margin_l: float = 0.3,
    fuel_pct_available: float = 100.0,
    fuel_override: tuple[int, float] | None = None,
) -> RacePlan:
    if tank_capacity_l <= 0:
        raise ValueError("tank_capacity_l must be > 0")
    if expected_fuel_per_lap_l <= 0:
        raise ValueError("expected_fuel_per_lap_l must be > 0")
    if mandatory_stops < 0:
        raise ValueError("mandatory_stops must be >= 0")
    if fuel_pct_available <= 0:
        raise ValueError("fuel_pct_available must be > 0")

    # e.g. a league rule capping usable fuel to some % of the tank -- 100
    # (the default) is a no-op, using the full tank_capacity_l as-is.
    effective_tank_capacity_l = tank_capacity_l * (fuel_pct_available / 100.0)

    usable_fuel_l = max(effective_tank_capacity_l - fuel_safety_margin_l, expected_fuel_per_lap_l)
    laps_per_stint = math.floor(usable_fuel_l / expected_fuel_per_lap_l)
    if tire_life_laps is not None and tire_life_laps > 0:
        laps_per_stint = min(laps_per_stint, tire_life_laps)
    laps_per_stint = max(laps_per_stint, 1)

    def stops_for(laps: int) -> int:
        return max(math.ceil(laps / laps_per_stint), mandatory_stops + 1) - 1

    if race_length_laps is None:
        if race_length_minutes is None or expected_lap_time_s is None:
            raise ValueError(
                "Provide either race_length_laps, or both race_length_minutes and expected_lap_time_s"
            )
        if expected_lap_time_s <= 0:
            raise ValueError("expected_lap_time_s must be > 0")
        time_budget_s = race_length_minutes * 60.0
        laps = math.ceil(time_budget_s / expected_lap_time_s)
        if pit_stop_time_loss_s is not None and pit_stop_time_loss_s > 0:
            # Time lost in the pits still counts against the race clock, so
            # it eats into how many laps fit -- and fewer laps can mean
            # fewer stops, which feeds back into the time available. Iterate
            # to a fixed point instead of just subtracting once.
            for _ in range(10):
                stops = stops_for(max(laps, 1))
                adjusted_budget_s = time_budget_s - stops * pit_stop_time_loss_s
                new_laps = max(math.floor(adjusted_budget_s / expected_lap_time_s), 1)
                if new_laps == laps:
                    break
                laps = new_laps
        race_length_laps = laps
    if race_length_laps <= 0:
        raise ValueError("race_length_laps must be > 0")

    num_stints = stops_for(race_length_laps) + 1

    # Distribute race_length_laps across num_stints as evenly as possible;
    # earlier stints absorb the +1 remainder laps.
    base = race_length_laps // num_stints
    remainder = race_length_laps % num_stints
    stint_lengths = [base + 1 if i < remainder else base for i in range(num_stints)]

    override_idx: int | None = None
    override_fuel_display: float | None = None
    if fuel_override is not None:
        override_stint_number, requested_fuel = fuel_override
        idx = override_stint_number - 1
        if idx < 0 or idx >= num_stints - 1:
            raise ValueError(
                f"fuel_override stint_number must be between 1 and {num_stints - 1} (not the final stint)"
            )

        # Stints before the override keep their lengths (that fuel/lap
        # choice already happened); the overridden stint's length is
        # clamped to what's physically possible -- not the narrower
        # "avoids an extra stop" window, since that window is by
        # definition the range that can't change the stop count, and the
        # whole point here is letting the stop count change.
        start_lap_next = sum(stint_lengths[: idx + 1])
        laps_remaining_from_next = race_length_laps - start_lap_next
        max_laps_next = min(laps_per_stint, laps_remaining_from_next)
        requested_laps = math.floor(max(requested_fuel - fuel_safety_margin_l, 0.0) / expected_fuel_per_lap_l)
        override_laps = max(1, min(requested_laps, max_laps_next))

        # Keep the exact amount the user typed as what's *shown* for this
        # stop, even though `override_laps` above had to be floored to a
        # whole lap to size the downstream stints -- otherwise the UI would
        # silently replace whatever they entered with the re-derived
        # lap-quantized value, which looked like the input being ignored.
        override_idx = idx
        override_fuel_display = round(min(max(requested_fuel, 0.0), effective_tank_capacity_l), 2)

        kept = stint_lengths[: idx + 1]
        remaining_after_override = race_length_laps - start_lap_next - override_laps

        if remaining_after_override <= 0:
            stint_lengths = kept + [override_laps]
        else:
            tail_num_stints = max(math.ceil(remaining_after_override / laps_per_stint), 1)
            tail_base = remaining_after_override // tail_num_stints
            tail_remainder = remaining_after_override % tail_num_stints
            tail_lengths = [
                tail_base + 1 if i < tail_remainder else tail_base for i in range(tail_num_stints)
            ]
            stint_lengths = kept + [override_laps] + tail_lengths

        num_stints = len(stint_lengths)

    stints: list[Stint] = []
    cumulative = 0
    for i, laps in enumerate(stint_lengths):
        start_lap = cumulative
        cumulative += laps
        is_last = i == num_stints - 1
        next_stint_laps = stint_lengths[i + 1] if not is_last else None
        if i == override_idx:
            fuel_to_add = override_fuel_display
        else:
            fuel_to_add = (
                round(
                    min(next_stint_laps * expected_fuel_per_lap_l + fuel_safety_margin_l, effective_tank_capacity_l),
                    2,
                )
                if next_stint_laps is not None
                else None
            )

        earliest_pit_lap = latest_pit_lap = None
        if not is_last:
            # stints remaining from here, including this one but excluding
            # the final (no-stop) stint -- equals stops remaining including
            # the one that ends this stint.
            stops_remaining_including_this_one = num_stints - 1 - i
            laps_remaining_from_here = race_length_laps - start_lap
            latest_pit_lap = min(start_lap + laps_per_stint, race_length_laps)
            earliest_pit_lap = min(
                start_lap
                + max(0, laps_remaining_from_here - stops_remaining_including_this_one * laps_per_stint),
                latest_pit_lap,
            )

        stints.append(
            Stint(
                stint_number=i + 1,
                laps=laps,
                pit_in_lap=cumulative if not is_last else None,
                fuel_to_add=fuel_to_add,
                earliest_pit_lap=earliest_pit_lap,
                latest_pit_lap=latest_pit_lap,
            )
        )

    total_time_s = None
    if expected_lap_time_s is not None and pit_stop_time_loss_s is not None:
        total_time_s = race_length_laps * expected_lap_time_s + (num_stints - 1) * pit_stop_time_loss_s

    return RacePlan(
        race_length_laps=race_length_laps,
        laps_per_stint=laps_per_stint,
        num_stops=num_stints - 1,
        stints=stints,
        total_time_s=total_time_s,
    )


def current_stint_fuel_to_add(plan: RacePlan, current_lap: int) -> float | None:
    """Fuel to add at the upcoming stop, based on which stint `current_lap`
    falls in. None once in the final stint (no more stops planned)."""
    for stint in plan.stints:
        end_lap = stint.pit_in_lap if stint.pit_in_lap is not None else plan.race_length_laps
        if current_lap <= end_lap:
            return stint.fuel_to_add
    return None


def upcoming_pit_windows(plan: RacePlan, current_lap: int) -> list[Stint]:
    """The current stint onward -- i.e. every stop not yet made, plus the
    final (no-stop) stint for context. Empty once past the end of the race.
    Completed earlier stints simply drop off the front as `current_lap`
    advances past them, so a UI list built from this naturally shrinks as
    you pit."""
    for i, stint in enumerate(plan.stints):
        end_lap = stint.pit_in_lap if stint.pit_in_lap is not None else plan.race_length_laps
        if current_lap <= end_lap:
            return plan.stints[i:]
    return []

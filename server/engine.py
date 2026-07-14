"""Ties a telemetry source to the fuel/tire trackers and the live pit-window
calculation, producing one JSON-serializable snapshot dict per tick for the
websocket to broadcast.
"""
import sys
import threading
import time
import traceback
from dataclasses import asdict
from typing import Protocol

from core.fuel import FuelTracker
from core.irsdk_client import TelemetryState
from core.leader_pace import LeaderPaceTracker
from core.pit_planner import compute_live_strategy
from core.relative import RelativeTracker
from core.session_baseline import SessionBaseline, SessionTransitionTracker, is_qualifying_session
from core.tires import TireTracker

COMPUTE_HZ = 5.0
_LAP_TIME_HISTORY = 5


class TelemetrySource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_state(self) -> TelemetryState: ...


class StrategyEngine:
    def __init__(self, source: TelemetrySource, compute_hz: float = COMPUTE_HZ):
        self._source = source
        self._interval = 1.0 / compute_hz
        self._fuel = FuelTracker()
        self._tires = TireTracker()
        self._relative = RelativeTracker()
        self._leader_pace = LeaderPaceTracker()
        self._lock = threading.Lock()
        self._latest: dict = {"connected": False}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._last_lap: int | None = None
        self._last_lap_time: float | None = None
        self._lap_time_samples: list[float] = []

        self._session_tracker = SessionTransitionTracker()
        self._qualifying_baseline: SessionBaseline | None = None

    def start(self) -> None:
        self._source.start()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._source.stop()

    def latest(self) -> dict:
        with self._lock:
            return dict(self._latest)

    def set_fuel_limit(self, max_fuel_l: float | None = None, pct_available: float | None = None) -> None:
        # FuelTracker guards this itself (its own lock) since it's written
        # here from the request-handling thread while _tick() reads it
        # concurrently from the background poll thread.
        self._fuel.set_fuel_limit(max_fuel_l, pct_available)

    def clear_fuel_limit(self) -> None:
        self._fuel.clear_fuel_limit()

    def fuel_limit_status(self) -> dict:
        return self._fuel.fuel_limit_status()

    def qualifying_baseline(self) -> SessionBaseline | None:
        with self._lock:
            return self._qualifying_baseline

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - never let a bad tick kill the loop
                # Printed (not just stored) so the packaged exe's
                # deliberately-visible console actually shows *why* the
                # overlay went to "disconnected" instead of leaving that as
                # a silent dead end -- overlay.js doesn't currently surface
                # data.error anywhere either.
                print(f"[PitStrategy] tick error: {exc}", file=sys.stderr)
                traceback.print_exc()
                with self._lock:
                    self._latest = {"connected": False, "error": str(exc)}
            time.sleep(self._interval)

    def _track_lap_time(self, lap: int) -> float | None:
        now = time.monotonic()
        if self._last_lap is None:
            self._last_lap = lap
            self._last_lap_time = now
            return None
        if lap != self._last_lap:
            elapsed = now - (self._last_lap_time or now)
            laps_advanced = max(lap - self._last_lap, 1)
            per_lap = elapsed / laps_advanced
            self._lap_time_samples.append(per_lap)
            self._lap_time_samples = self._lap_time_samples[-_LAP_TIME_HISTORY:]
            self._last_lap = lap
            self._last_lap_time = now
        if not self._lap_time_samples:
            return None
        return sum(self._lap_time_samples) / len(self._lap_time_samples)

    def _tick(self) -> None:
        state = self._source.get_state()
        if not state.connected:
            with self._lock:
                self._latest = {"connected": False}
            return

        # Check for a session change *before* this tick's data goes into the
        # trackers, so a qualifying baseline (if one gets captured) reflects
        # the session that just ended, not the new one's first sample --
        # and so the live trackers get reset instead of blending laps from
        # two different sessions into one rolling average.
        prev_session_type = self._session_tracker.check(state.session_num, state.session_type)
        if prev_session_type is not None:
            if is_qualifying_session(prev_session_type):
                fuel_snapshot = self._fuel.snapshot()
                lap_time_avg = (
                    sum(self._lap_time_samples) / len(self._lap_time_samples)
                    if self._lap_time_samples
                    else None
                )
                if fuel_snapshot.avg_fuel_per_lap and lap_time_avg:
                    with self._lock:
                        self._qualifying_baseline = SessionBaseline(
                            fuel_per_lap=fuel_snapshot.avg_fuel_per_lap,
                            lap_time_s=lap_time_avg,
                            fuel_samples=fuel_snapshot.samples,
                            lap_time_samples=len(self._lap_time_samples),
                            session_type=prev_session_type,
                            captured_at_lap=self._last_lap or 0,
                        )
            self._fuel.reset()
            self._tires.reset()
            self._relative.reset()
            self._last_lap = None
            self._last_lap_time = None
            self._lap_time_samples = []

        self._fuel.set_tank_capacity(state.tank_capacity)
        self._fuel.update(state.lap, state.fuel_level)
        self._tires.update(state.lap, state.wear, state.tire_temps)
        avg_lap_time_s = self._track_lap_time(state.lap)

        fuel_state = self._fuel.snapshot()
        tire_state = self._tires.snapshot()

        laps_remaining_in_race = state.laps_remain
        if laps_remaining_in_race is None and state.session_time_remain is not None and avg_lap_time_s:
            laps_remaining_in_race = state.session_time_remain / avg_lap_time_s

        strategy = compute_live_strategy(state.lap, fuel_state, tire_state, laps_remaining_in_race)

        self._relative.update_pit_status(state.car_idx_on_pit_road)
        my_last_lap_time = None
        if state.player_car_idx is not None and state.player_car_idx < len(state.car_idx_last_lap_time):
            candidate = state.car_idx_last_lap_time[state.player_car_idx]
            my_last_lap_time = candidate if candidate and candidate > 0 else None
        nearby = self._relative.nearby_cars(
            player_car_idx=state.player_car_idx,
            car_idx_position=state.car_idx_position,
            car_idx_last_lap_time=state.car_idx_last_lap_time,
            car_numbers=state.car_numbers,
            my_last_lap_time=my_last_lap_time,
        )

        total_fuel_to_finish = (
            laps_remaining_in_race * fuel_state.avg_fuel_per_lap
            if laps_remaining_in_race is not None and fuel_state.avg_fuel_per_lap
            else None
        )

        # Leader-pace-based fuel-to-finish: kept deliberately separate from
        # laps_remaining_in_race above (which also drives the live
        # pit-window/status-bar calculation) rather than replacing it there
        # -- the leader's pace is a better estimate of how many laps are
        # actually left in a time-certain race (the flag falls on *their*
        # lap, not the player's), but swapping it into the existing
        # variable would also change pit-window behavior that's already
        # been verified, which is a bigger blast radius than asked for.
        leader_idx = None
        for idx, pos in enumerate(state.car_idx_position):
            if pos and pos == 1:
                leader_idx = idx
                break
        leader_last_lap_time = None
        if leader_idx is not None and leader_idx < len(state.car_idx_last_lap_time):
            candidate = state.car_idx_last_lap_time[leader_idx]
            leader_last_lap_time = candidate if candidate and candidate > 0 else None
        self._leader_pace.update(leader_last_lap_time)
        leader_pace_state = self._leader_pace.snapshot()

        laps_remaining_leader_pace = (
            state.session_time_remain / leader_pace_state.avg_lap_time_s
            if state.session_time_remain is not None and leader_pace_state.avg_lap_time_s
            else None
        )
        fuel_needed_to_finish_leader_pace = (
            laps_remaining_leader_pace * fuel_state.avg_fuel_per_lap
            if laps_remaining_leader_pace is not None and fuel_state.avg_fuel_per_lap
            else None
        )
        fuel_margin_at_finish = (
            fuel_state.current_fuel_level - fuel_needed_to_finish_leader_pace
            if fuel_needed_to_finish_leader_pace is not None
            else None
        )

        with self._lock:
            self._latest = {
                "connected": True,
                "lap": state.lap,
                "avg_lap_time_s": avg_lap_time_s,
                "laps_remaining_in_race": laps_remaining_in_race,
                "total_fuel_to_finish": total_fuel_to_finish,
                "leader_avg_lap_time_s": leader_pace_state.avg_lap_time_s,
                "laps_remaining_leader_pace": laps_remaining_leader_pace,
                "fuel_needed_to_finish_leader_pace": fuel_needed_to_finish_leader_pace,
                "fuel_margin_at_finish": fuel_margin_at_finish,
                "fuel": asdict(fuel_state),
                "tires": asdict(tire_state),
                "strategy": asdict(strategy),
                "qualifying_baseline": asdict(self._qualifying_baseline) if self._qualifying_baseline is not None else None,
                "relative": {
                    "ahead": [asdict(c) for c in nearby["ahead"]],
                    "behind": [asdict(c) for c in nearby["behind"]],
                },
            }

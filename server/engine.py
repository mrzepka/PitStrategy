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

# Maps settings_store.py's OverlaySettings.auto_fuel_source values to the
# matching FuelState rate -- same four rates the "Fuel calculations (rows)"
# settings toggle the display of, so auto-fuel always sources from one of
# the numbers already on the HUD rather than a separately-typed value.
_AUTO_FUEL_RATE_FIELD = {
    "last_lap": "last_lap_fuel_per_lap",
    "max_fuel": "max_fuel_per_lap",
    "avg_fuel": "avg_fuel_per_lap",
}


class TelemetrySource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_state(self) -> TelemetryState: ...
    def send_pit_fuel(self, liters: float) -> bool: ...


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

        # Auto pit fuel: written from the request-handling thread via
        # set_overlay_settings() (mirroring set_fuel_limit()'s pattern),
        # read from the background poll thread in _tick(). Guarded by
        # _settings_lock rather than _lock since it's updated independently
        # of _latest and there's no need to serialize the two.
        self._settings_lock = threading.Lock()
        self._auto_fuel_enabled = False
        self._auto_fuel_source: str | None = None
        self._was_on_pit_road = False
        self._last_fuel_command: dict | None = None

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

    def set_overlay_settings(self, auto_fuel_enabled: bool, auto_fuel_source: str | None) -> None:
        with self._settings_lock:
            self._auto_fuel_enabled = auto_fuel_enabled
            self._auto_fuel_source = auto_fuel_source

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
            print(
                f"[PitStrategy] session transition: session_num={state.session_num} "
                f"prev_session_type={prev_session_type!r} new_session_type={state.session_type!r} "
                f"last_lap={self._last_lap!r}",
                file=sys.stderr,
            )
            if is_qualifying_session(prev_session_type):
                fuel_snapshot = self._fuel.snapshot()
                lap_time_avg = (
                    sum(self._lap_time_samples) / len(self._lap_time_samples)
                    if self._lap_time_samples
                    else None
                )
                print(
                    f"[PitStrategy] qualifying ({prev_session_type!r}) ended -- fuel snapshot: "
                    f"avg_fuel_per_lap={fuel_snapshot.avg_fuel_per_lap!r} "
                    f"max_fuel_per_lap={fuel_snapshot.max_fuel_per_lap!r} "
                    f"last_lap_fuel_per_lap={fuel_snapshot.last_lap_fuel_per_lap!r} "
                    f"samples={fuel_snapshot.samples} "
                    f"current_fuel_level={fuel_snapshot.current_fuel_level!r} "
                    f"tank_capacity={fuel_snapshot.tank_capacity!r} | "
                    f"lap_time_avg={lap_time_avg!r} "
                    f"lap_time_samples={self._lap_time_samples!r}",
                    file=sys.stderr,
                )
                if fuel_snapshot.max_fuel_per_lap and lap_time_avg:
                    if self._qualifying_baseline is not None:
                        print(
                            f"[PitStrategy] qualifying baseline REPLACED: "
                            f"old fuel_per_lap={self._qualifying_baseline.fuel_per_lap!r} "
                            f"(from {self._qualifying_baseline.session_type!r}) -> "
                            f"new fuel_per_lap={fuel_snapshot.max_fuel_per_lap!r}",
                            file=sys.stderr,
                        )
                    with self._lock:
                        self._qualifying_baseline = SessionBaseline(
                            # The worst-case (max) single-lap usage seen during
                            # qualifying, not the rolling average -- a fuel plan
                            # built on an average would come up short on exactly
                            # the lap(s) that used more than average.
                            fuel_per_lap=fuel_snapshot.max_fuel_per_lap,
                            lap_time_s=lap_time_avg,
                            fuel_samples=fuel_snapshot.samples,
                            lap_time_samples=len(self._lap_time_samples),
                            session_type=prev_session_type,
                            captured_at_lap=self._last_lap or 0,
                        )
                    print(
                        f"[PitStrategy] qualifying baseline captured: {self._qualifying_baseline!r}",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[PitStrategy] qualifying baseline NOT captured -- need both "
                        f"max_fuel_per_lap and lap_time_avg to be truthy "
                        f"(max_fuel_per_lap={fuel_snapshot.max_fuel_per_lap!r}, "
                        f"lap_time_avg={lap_time_avg!r})",
                        file=sys.stderr,
                    )
            self._fuel.reset()
            self._tires.reset()
            self._relative.reset()
            self._last_lap = None
            self._last_lap_time = None
            self._lap_time_samples = []
            self._was_on_pit_road = False

        player_on_pit_road = False
        if (
            state.player_car_idx is not None
            and state.player_car_idx < len(state.car_idx_on_pit_road)
        ):
            player_on_pit_road = bool(state.car_idx_on_pit_road[state.player_car_idx])
        entered_pit_road = player_on_pit_road and not self._was_on_pit_road
        self._was_on_pit_road = player_on_pit_road
        with self._settings_lock:
            auto_fuel_enabled = self._auto_fuel_enabled
            auto_fuel_source = self._auto_fuel_source
        if entered_pit_road:
            # Logged unconditionally -- pit-road entry itself is detected
            # regardless of whether the auto-fuel feature is turned on, so
            # this line is the only way to confirm CarIdxOnPitRoad detection
            # is actually working (e.g. before ever enabling the feature).
            # The actual send happens further down, once fuel_state and
            # laps_remaining_leader_pace (needed to size the request) exist.
            print(
                f"[PitStrategy] pit road entry detected at lap={state.lap} "
                f"(auto_fuel_enabled={auto_fuel_enabled}, auto_fuel_source={auto_fuel_source!r})",
                file=sys.stderr,
            )

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

        if entered_pit_road and auto_fuel_enabled and auto_fuel_source:
            if auto_fuel_source == "quali_fuel":
                rate = self._qualifying_baseline.fuel_per_lap if self._qualifying_baseline is not None else None
            else:
                rate = getattr(fuel_state, _AUTO_FUEL_RATE_FIELD[auto_fuel_source])

            if not rate or rate <= 0 or laps_remaining_leader_pace is None or not fuel_state.tank_capacity:
                print(
                    f"[PitStrategy] auto pit fuel: skipped -- missing data for source={auto_fuel_source!r} "
                    f"(rate={rate!r}, laps_remaining_leader_pace={laps_remaining_leader_pace!r}, "
                    f"tank_capacity={fuel_state.tank_capacity!r})",
                    file=sys.stderr,
                )
            else:
                # Enough to have exactly what's needed to finish at this
                # rate, not a full tank -- mirrors the "Finish" column's own
                # math (current fuel vs. laps-remaining-at-leader-pace * rate),
                # just solved for "how much more to add" instead of "what's
                # the margin." Clamped so this never asks for more than the
                # tank can physically hold.
                fuel_needed = laps_remaining_leader_pace * rate
                amount = fuel_needed - fuel_state.current_fuel_level
                amount = max(0.0, min(amount, fuel_state.tank_capacity - fuel_state.current_fuel_level))
                if amount <= 0.05:
                    print(
                        f"[PitStrategy] auto pit fuel: skipped -- already enough fuel to finish at "
                        f"source={auto_fuel_source!r} rate={rate:.3f} L/lap (needed={fuel_needed:.2f}L, "
                        f"current={fuel_state.current_fuel_level:.2f}L)",
                        file=sys.stderr,
                    )
                else:
                    sent = self._source.send_pit_fuel(amount)
                    print(
                        f"[PitStrategy] auto pit fuel: requested {amount:.1f}L to finish at "
                        f"source={auto_fuel_source!r} rate={rate:.3f} L/lap (sent={sent})",
                        file=sys.stderr,
                    )
                    with self._lock:
                        self._last_fuel_command = {"amount_l": amount, "source": auto_fuel_source, "sent": sent}

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
                "last_fuel_command": self._last_fuel_command,
                "relative": {
                    "ahead": [asdict(c) for c in nearby["ahead"]],
                    "behind": [asdict(c) for c in nearby["behind"]],
                },
            }

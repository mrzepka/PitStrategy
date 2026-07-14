"""Telemetry sources for the strategy server.

`IRSDKTelemetrySource` wraps pyirsdk the same way iRacingTelemetry's
core/live.py does (poll -> freeze_var_buffer_latest -> read -> unfreeze),
just on a plain background thread instead of a Qt timer since this project
has no GUI event loop. `DemoTelemetrySource` generates synthetic data with
the same shape so the whole pipeline (server, websocket, browser overlay)
can be exercised without iRacing running -- pyirsdk's test_file replay mode
is only a static single-tick snapshot, not useful for that.
"""
import random
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field

from core.tires import TEMP_CHANNELS, WEAR_CHANNELS

DEFAULT_POLL_HZ = 10.0
_RECONNECT_INTERVAL_S = 2.0


@dataclass
class TelemetryState:
    connected: bool = False
    lap: int = 0
    fuel_level: float = 0.0
    wear: dict[str, float] = field(default_factory=dict)
    tire_temps: dict[str, float] = field(default_factory=dict)
    session_time_remain: float | None = None
    laps_remain: float | None = None
    tank_capacity: float | None = None
    car_idx_position: list[int] = field(default_factory=list)
    car_idx_last_lap_time: list[float] = field(default_factory=list)
    car_idx_on_pit_road: list[bool] = field(default_factory=list)
    player_car_idx: int | None = None
    car_numbers: dict[int, str] = field(default_factory=dict)
    session_num: int | None = None
    session_type: str | None = None  # e.g. "Lone Qualify", "Race", "Practice" -- iRacing's own free-text label


class IRSDKTelemetrySource:
    """Live connection to iRacing via pyirsdk."""

    def __init__(self, poll_hz: float = DEFAULT_POLL_HZ):
        import irsdk  # deferred import: only needed for the live source

        self._ir = irsdk.IRSDK()
        self._poll_interval = 1.0 / poll_hz
        self._lock = threading.Lock()
        self._state = TelemetryState()
        self._last_connect_attempt = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._ir.is_initialized:
            self._ir.shutdown()

    def get_state(self) -> TelemetryState:
        with self._lock:
            return TelemetryState(
                connected=self._state.connected,
                lap=self._state.lap,
                fuel_level=self._state.fuel_level,
                wear=dict(self._state.wear),
                tire_temps=dict(self._state.tire_temps),
                session_time_remain=self._state.session_time_remain,
                laps_remain=self._state.laps_remain,
                tank_capacity=self._state.tank_capacity,
                car_idx_position=list(self._state.car_idx_position),
                car_idx_last_lap_time=list(self._state.car_idx_last_lap_time),
                car_idx_on_pit_road=list(self._state.car_idx_on_pit_road),
                player_car_idx=self._state.player_car_idx,
                car_numbers=dict(self._state.car_numbers),
                session_num=self._state.session_num,
                session_type=self._state.session_type,
            )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as exc:  # noqa: BLE001 - never let a bad poll kill the loop
                # Printed so a real cause (e.g. a wrong SDK channel name)
                # shows up somewhere instead of just "disconnected" with no
                # trail -- the packaged exe deliberately keeps a visible
                # console specifically so this kind of thing is diagnosable.
                print(f"[PitStrategy] telemetry poll error: {exc}", file=sys.stderr)
                traceback.print_exc()
                with self._lock:
                    self._state.connected = False
            time.sleep(self._poll_interval)

    def _poll(self) -> None:
        if not self._ir.is_initialized:
            now = time.monotonic()
            if now - self._last_connect_attempt < _RECONNECT_INTERVAL_S:
                return
            self._last_connect_attempt = now
            self._ir.startup()
            return

        if not self._ir.is_connected:
            with self._lock:
                self._state.connected = False
            return

        self._ir.freeze_var_buffer_latest()
        try:
            lap = self._ir["Lap"]
            fuel_level = self._ir["FuelLevel"]
            wear = {name: self._ir[name] for name in WEAR_CHANNELS}
            tire_temps = {name: self._ir[name] for name in TEMP_CHANNELS}
            session_time_remain = self._ir["SessionTimeRemain"]
            laps_remain = self._ir["SessionLapsRemainEx"]
            tank_capacity = self._read_tank_capacity()
            car_idx_position = list(self._ir["CarIdxPosition"] or [])
            car_idx_last_lap_time = list(self._ir["CarIdxLastLapTime"] or [])
            car_idx_on_pit_road = list(self._ir["CarIdxOnPitRoad"] or [])
            player_car_idx = self._ir["PlayerCarIdx"]
            car_numbers = self._read_car_numbers()
            session_num = self._ir["SessionNum"]
            session_type = self._read_session_type(session_num)
        finally:
            self._ir.unfreeze_var_buffer_latest()

        with self._lock:
            self._state = TelemetryState(
                connected=True,
                lap=lap or 0,
                fuel_level=fuel_level or 0.0,
                wear=wear,
                tire_temps=tire_temps,
                session_time_remain=session_time_remain,
                laps_remain=laps_remain,
                tank_capacity=tank_capacity if tank_capacity else self._state.tank_capacity,
                car_idx_position=car_idx_position,
                car_idx_last_lap_time=car_idx_last_lap_time,
                car_idx_on_pit_road=car_idx_on_pit_road,
                player_car_idx=player_car_idx,
                car_numbers=car_numbers if car_numbers else self._state.car_numbers,
                session_num=session_num,
                session_type=session_type,
            )

    def _read_tank_capacity(self) -> float | None:
        try:
            driver_info = self._ir["DriverInfo"]
            return float(driver_info["DriverCarFuelMaxLtr"])
        except Exception:
            return None

    def _read_car_numbers(self) -> dict[int, str]:
        try:
            drivers = self._ir["DriverInfo"]["Drivers"]
            return {int(d["CarIdx"]): str(d.get("CarNumber", "?")) for d in drivers}
        except Exception:
            return {}

    def _read_session_type(self, session_num: int | None) -> str | None:
        try:
            sessions = self._ir["SessionInfo"]["Sessions"]
            return str(sessions[session_num]["SessionType"])
        except Exception:
            return None

    def send_pit_fuel(self, liters: float) -> bool:
        """Sets the pit stall's requested fuel-add amount via iRacing's SDK
        pit-service broadcast (the same mechanism the in-car pit menu uses)
        -- not a chat command. Requires being connected; still requires
        actually driving into the pit stall for it to take effect."""
        if not self._ir.is_initialized or not self._ir.is_connected:
            return False
        import irsdk  # deferred import, same reasoning as __init__'s

        try:
            self._ir.pit_command(irsdk.PitCommandMode.fuel, round(liters))
            return True
        except Exception:
            return False


class DemoTelemetrySource:
    """Synthetic telemetry: fuel drains, tires wear, laps tick over, and a
    pit stop happens automatically every ~12 laps so the overlay's
    refuel/tire-change outlier handling gets exercised too.
    """

    def __init__(self, lap_time_s: float = 6.0, poll_hz: float = DEFAULT_POLL_HZ):
        self._lap_time_s = lap_time_s
        self._poll_interval = 1.0 / poll_hz
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._lap = 0
        self._fuel = 60.0
        self._tank_capacity = 65.0
        self._fuel_per_lap = 2.4
        self._wear = {name: 1.0 for name in WEAR_CHANNELS}
        self._wear_per_lap = 0.012
        self._tire_temps = {name: 75.0 for name in TEMP_CHANNELS}
        self._start_time = time.monotonic()
        self._last_lap_tick = self._start_time
        self._last_poll_time = self._start_time
        # Picked fresh each lap (see _run()) and drained smoothly across
        # it, tick by tick, instead of removed as one lump at the lap
        # boundary -- so FuelLevel (and anything derived from it, like
        # "laps remaining") changes continuously with usage the way real
        # iRacing telemetry does, not just once per lap.
        self._current_lap_fuel_rate = self._fuel_per_lap
        self._total_laps = 40
        # Brief synthetic window during which the player's own car reports
        # as being on pit road, so the auto-pit-fuel feature (which fires on
        # the rising edge of that signal) has something to exercise in
        # --demo -- set for a few seconds around the same every-12-laps
        # refuel event that already simulates a pit stop.
        self._player_pit_road_until = 0.0
        self.last_commanded_fuel: float | None = None

        # Scripted session transition: starts in a qualifying-type session
        # for a handful of laps, then moves on to the race, so the
        # qualifying-baseline capture path (StrategyEngine's
        # SessionTransitionTracker) has something to exercise in --demo
        # without needing a real iRacing session change.
        self._session_num = 0
        self._session_type = "Lone Qualify"
        self._qualifying_laps = 6

        # Synthetic field: player at position 4 of 8, with a couple of
        # rivals scripted to pit partway through so `has_pitted` gets
        # exercised without needing a real session.
        self._player_car_idx = 0
        self._car_positions = {0: 4, 1: 1, 2: 2, 3: 3, 4: 5, 5: 6, 6: 7, 7: 8}
        self._car_numbers = {0: "00", 1: "17", 2: "44", 3: "9", 4: "22", 5: "5", 6: "88", 7: "3"}
        self._car_lap_time_offsets = {0: 0.0, 1: -0.4, 2: 0.1, 3: -0.1, 4: 0.3, 5: -0.2, 6: 0.5, 7: 0.2}
        self._car_last_lap_time = {
            idx: self._lap_time_s + offset for idx, offset in self._car_lap_time_offsets.items()
        }

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def get_state(self) -> TelemetryState:
        with self._lock:
            num_cars = len(self._car_positions)
            car_idx_position = [0] * num_cars
            car_idx_last_lap_time = [0.0] * num_cars
            for idx, pos in self._car_positions.items():
                car_idx_position[idx] = pos
            for idx, lap_time in self._car_last_lap_time.items():
                car_idx_last_lap_time[idx] = lap_time
            car_idx_on_pit_road = [False] * num_cars
            if self._lap == 5:
                car_idx_on_pit_road[2] = True  # a car ahead pits
            if self._lap == 7:
                car_idx_on_pit_road[5] = True  # a car behind pits
            if time.monotonic() < self._player_pit_road_until:
                car_idx_on_pit_road[self._player_car_idx] = True

            return TelemetryState(
                connected=True,
                lap=self._lap,
                fuel_level=round(self._fuel, 3),
                wear=dict(self._wear),
                tire_temps=dict(self._tire_temps),
                session_time_remain=(self._total_laps - self._lap) * self._lap_time_s,
                laps_remain=self._total_laps - self._lap,
                tank_capacity=self._tank_capacity,
                car_idx_position=car_idx_position,
                car_idx_last_lap_time=car_idx_last_lap_time,
                car_idx_on_pit_road=car_idx_on_pit_road,
                player_car_idx=self._player_car_idx,
                car_numbers=dict(self._car_numbers),
                session_num=self._session_num,
                session_type=self._session_type,
            )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            elapsed = now - self._last_poll_time
            self._last_poll_time = now

            with self._lock:
                # Continuous drain proportional to real time elapsed this
                # poll -- not a lump decrement at the lap boundary -- so
                # FuelLevel changes every tick like real telemetry does,
                # instead of staying flat for a whole lap and then jumping.
                drain = self._current_lap_fuel_rate * (elapsed / self._lap_time_s)
                self._fuel = max(self._fuel - drain, 0.0)

            if now - self._last_lap_tick >= self._lap_time_s:
                self._last_lap_tick = now
                with self._lock:
                    self._lap += 1

                    if self._session_num == 0 and self._lap >= self._qualifying_laps:
                        # Quali's over -- move to the race with a fresh lap
                        # count, full tank, and new tires, same as a real
                        # session change would give you on the grid.
                        self._session_num = 1
                        self._session_type = "Race"
                        self._lap = 0
                        self._fuel = self._tank_capacity
                        for name in self._wear:
                            self._wear[name] = 1.0
                        for name in self._tire_temps:
                            self._tire_temps[name] = 75.0

                    # Picked now, for the lap that's just starting -- keeps
                    # the lap-to-lap consumption variance the old lump-sum
                    # version had, while the actual removal happens
                    # gradually above, tick by tick, over that whole lap.
                    self._current_lap_fuel_rate = self._fuel_per_lap * random.uniform(0.9, 1.1)

                    for name in self._wear:
                        # Independent per-channel jitter (rather than one
                        # shared multiplier) so the "worst" corner/tread
                        # actually shifts around lap to lap, like real data.
                        self._wear[name] = max(self._wear[name] - self._wear_per_lap * random.uniform(0.8, 1.2), 0.0)
                    for name in self._tire_temps:
                        self._tire_temps[name] = max(
                            40.0, min(self._tire_temps[name] + random.uniform(-2.0, 3.0), 110.0)
                        )

                    # self._lap > 0 excludes the lap==0 the quali->race
                    # transition just reset us to a few lines up -- without
                    # it, this fires a second, redundant "pit stop" (and now
                    # a false player-on-pit-road signal) right at session
                    # start instead of only at real in-race intervals.
                    if self._lap > 0 and self._lap % 12 == 0:
                        self._fuel = self._tank_capacity
                        for name in self._wear:
                            self._wear[name] = 1.0
                        for name in self._tire_temps:
                            self._tire_temps[name] = 75.0  # fresh tires, back to a baseline temp
                        # A few seconds of "on pit road" around this same
                        # refuel event -- see __init__'s comment.
                        self._player_pit_road_until = now + 3.0

                    for idx, offset in self._car_lap_time_offsets.items():
                        self._car_last_lap_time[idx] = round(
                            self._lap_time_s + offset + random.uniform(-0.05, 0.05), 3
                        )

                    if self._lap >= self._total_laps:
                        self._lap = 0
            time.sleep(self._poll_interval)

    def send_pit_fuel(self, liters: float) -> bool:
        """No real sim to write to -- just records the request so the demo
        path exercises the same code path as the live source."""
        with self._lock:
            self.last_commanded_fuel = liters
        return True

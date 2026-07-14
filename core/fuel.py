"""Rolling fuel-usage tracking for the live pit-strategy overlay.

Feed it a (lap, fuel_level) sample on every telemetry tick via `update()`.
It only records a per-lap usage sample when the lap number advances, and
discards any sample where fuel went *up* (a refuel happened) instead of
letting it corrupt the rolling average.
"""
import sys
import threading
from collections import deque
from dataclasses import dataclass


@dataclass
class FuelState:
    avg_fuel_per_lap: float | None  # rolling average over the last `history_len` laps
    current_fuel_level: float
    laps_remaining_on_fuel: float | None
    tank_capacity: float | None  # effective usable capacity (after any % cap)
    samples: int
    max_fuel_per_lap: float | None = None  # highest single-lap usage seen this session
    max_fuel_l: float | None = None  # raw override-or-detected tank size, before the % cap
    fuel_pct_available: float = 100.0
    last_lap_fuel_per_lap: float | None = None  # most recent single-lap usage (not the rolling average)


class FuelTracker:
    def __init__(self, history_len: int = 5):
        self._history_len = history_len
        self._usage: deque[float] = deque(maxlen=history_len)
        self._tank_capacity: float | None = None
        self._last_lap: int | None = None
        self._fuel_at_lap_start: float | None = None
        self._current_fuel: float = 0.0
        self._max_fuel_per_lap: float | None = None

        # Manual fuel-limit override, e.g. a league rule capping usable fuel
        # below the car's physical tank. Guarded by its own lock since,
        # unlike the rest of this tracker's state, it can be set from a
        # request-handling thread (the /api/fuel-limit endpoint) while the
        # engine's background poll thread concurrently reads it via
        # effective_tank_capacity / snapshot().
        self._limit_lock = threading.Lock()
        self._fuel_limit_override: float | None = None
        self._fuel_pct_available: float = 100.0

    def set_tank_capacity(self, capacity: float | None) -> None:
        """Liters, typically pulled from session DriverInfo.DriverCarFuelMaxLtr."""
        if capacity and capacity > 0:
            self._tank_capacity = capacity

    def set_fuel_limit(self, max_fuel_l: float | None = None, pct_available: float | None = None) -> None:
        """Manual override for usable fuel. Both args are independently
        optional: set `max_fuel_l` alone for a flat manual cap in liters
        (e.g. you don't know the car's actual tank size), `pct_available`
        alone to scale whichever tank size is currently in effect, or both
        together for "known tank size x rule %"."""
        with self._limit_lock:
            if max_fuel_l is not None:
                self._fuel_limit_override = max_fuel_l if max_fuel_l > 0 else None
            if pct_available is not None:
                self._fuel_pct_available = pct_available if pct_available > 0 else 100.0

    def clear_fuel_limit(self) -> None:
        with self._limit_lock:
            self._fuel_limit_override = None
            self._fuel_pct_available = 100.0

    @property
    def effective_tank_capacity(self) -> float | None:
        with self._limit_lock:
            override, pct = self._fuel_limit_override, self._fuel_pct_available
        base = override if override is not None else self._tank_capacity
        return base * (pct / 100.0) if base is not None else None

    def fuel_limit_status(self) -> dict:
        """Current effective-capacity numbers, computed fresh (not from a
        cached snapshot) so callers setting/clearing the override get an
        immediately up-to-date answer instead of waiting for the next
        background tick to refresh a cached value."""
        with self._limit_lock:
            override, pct = self._fuel_limit_override, self._fuel_pct_available
        max_fuel_l = override if override is not None else self._tank_capacity
        tank_capacity = max_fuel_l * (pct / 100.0) if max_fuel_l is not None else None
        return {"tank_capacity": tank_capacity, "max_fuel_l": max_fuel_l, "fuel_pct_available": pct}

    def reset(self) -> None:
        self._usage.clear()
        self._last_lap = None
        self._fuel_at_lap_start = None
        self._max_fuel_per_lap = None

    def update(self, lap: int, fuel_level: float) -> None:
        self._current_fuel = fuel_level

        if self._last_lap is None:
            self._last_lap = lap
            self._fuel_at_lap_start = fuel_level
            print(
                f"[PitStrategy] fuel: tracking (re)started at lap={lap} "
                f"fuel_level={fuel_level:.3f}L -- if this lap wasn't actually just starting "
                f"(e.g. mid-lap, or an out-lap that doesn't increment `lap`), the very next "
                f"sample's usage will be inflated by whatever was burned before this point",
                file=sys.stderr,
            )
            return

        if lap == self._last_lap:
            return

        # Lap advanced (possibly by more than 1 if a tick was missed).
        if self._fuel_at_lap_start is not None:
            delta = self._fuel_at_lap_start - fuel_level
            laps_advanced = max(lap - self._last_lap, 1)
            per_lap = delta / laps_advanced
            if delta > 0:
                # Only trust usage that actually decreased fuel (a refuel
                # mid-lap would otherwise show as negative/zero usage and
                # drag the average down).
                self._usage.append(per_lap)
                if self._max_fuel_per_lap is None or per_lap > self._max_fuel_per_lap:
                    self._max_fuel_per_lap = per_lap
                print(
                    f"[PitStrategy] fuel: lap {self._last_lap}->{lap} "
                    f"usage={per_lap:.3f} L/lap (fuel {self._fuel_at_lap_start:.3f}L -> "
                    f"{fuel_level:.3f}L over {laps_advanced} lap(s)) -- accepted, "
                    f"rolling avg now {self.avg_fuel_per_lap}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[PitStrategy] fuel: lap {self._last_lap}->{lap} "
                    f"fuel {self._fuel_at_lap_start:.3f}L -> {fuel_level:.3f}L "
                    f"(delta={delta:.3f}L, went up or flat) -- discarded as a refuel/outlier",
                    file=sys.stderr,
                )

        self._last_lap = lap
        self._fuel_at_lap_start = fuel_level

    @property
    def avg_fuel_per_lap(self) -> float | None:
        if not self._usage:
            return None
        return sum(self._usage) / len(self._usage)

    @property
    def last_lap_fuel_per_lap(self) -> float | None:
        return self._usage[-1] if self._usage else None

    def snapshot(self) -> FuelState:
        avg = self.avg_fuel_per_lap
        with self._limit_lock:
            override, pct = self._fuel_limit_override, self._fuel_pct_available
        max_fuel_l = override if override is not None else self._tank_capacity
        effective_capacity = max_fuel_l * (pct / 100.0) if max_fuel_l is not None else None
        laps_remaining = (self._current_fuel / avg) if avg else None
        return FuelState(
            avg_fuel_per_lap=avg,
            current_fuel_level=self._current_fuel,
            laps_remaining_on_fuel=laps_remaining,
            tank_capacity=effective_capacity,
            samples=len(self._usage),
            max_fuel_per_lap=self._max_fuel_per_lap,
            max_fuel_l=max_fuel_l,
            fuel_pct_available=pct,
            last_lap_fuel_per_lap=self.last_lap_fuel_per_lap,
        )

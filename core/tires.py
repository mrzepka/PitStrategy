"""Rolling tire-wear tracking for the live pit-strategy overlay.

iRacing reports wear per tread position per corner as a 0..1 fraction
*remaining* (1.0 = new, 0.0 = fully worn): LFwearL/M/R, RFwearL/M/R,
LRwearL/M/R, RRwearL/M/R. We track the single worst (minimum) channel at
each tick -- whichever corner/tread is closest to the cliff is what
determines when you have to pit, regardless of which physical corner it is
-- along with which corner/tread that is and its last carcass temperature
reading (LFtempCL/CM/CR etc.), since knowing *which* tire and how hot it's
running is more actionable than a wear-rate number that's noisy until
you've completed at least one real stint.
"""
from collections import deque
from dataclasses import dataclass

CORNERS = ("LF", "RF", "LR", "RR")
TREADS = ("L", "M", "R")

WEAR_CHANNELS = [f"{corner}wear{tread}" for corner in CORNERS for tread in TREADS]
TEMP_CHANNELS = [f"{corner}tempC{tread}" for corner in CORNERS for tread in TREADS]


def _wear_channel(corner: str, tread: str) -> str:
    return f"{corner}wear{tread}"


def _temp_channel(corner: str, tread: str) -> str:
    return f"{corner}tempC{tread}"


@dataclass
class TireState:
    worst_wear_remaining: float | None
    avg_wear_per_lap: float | None
    laps_remaining_on_tires: float | None
    samples: int
    worst_tire_position: str | None = None  # e.g. "RF-M"
    worst_tire_temp: float | None = None  # last reading at that same position


class TireTracker:
    def __init__(self, history_len: int = 5):
        self._history_len = history_len
        self._wear_rate: deque[float] = deque(maxlen=history_len)
        self._last_lap: int | None = None
        self._worst_at_lap_start: float | None = None
        self._current_worst: float | None = None
        self._worst_position: str | None = None
        self._worst_temp: float | None = None

    def reset(self) -> None:
        self._wear_rate.clear()
        self._last_lap = None
        self._worst_at_lap_start = None

    def update(self, lap: int, wear_values: dict[str, float], temps: dict[str, float] | None = None) -> None:
        if not wear_values:
            return

        worst = None
        worst_corner = worst_tread = None
        for corner in CORNERS:
            for tread in TREADS:
                value = wear_values.get(_wear_channel(corner, tread))
                if value is None:
                    continue
                if worst is None or value < worst:
                    worst = value
                    worst_corner, worst_tread = corner, tread
        if worst is None:
            return

        self._current_worst = worst
        self._worst_position = f"{worst_corner}-{worst_tread}"
        if temps:
            temp = temps.get(_temp_channel(worst_corner, worst_tread))
            if temp is not None:
                self._worst_temp = temp

        if self._last_lap is None:
            self._last_lap = lap
            self._worst_at_lap_start = worst
            return

        if lap == self._last_lap:
            return

        if self._worst_at_lap_start is not None:
            delta = self._worst_at_lap_start - worst
            laps_advanced = max(lap - self._last_lap, 1)
            per_lap = delta / laps_advanced
            if delta > 0:
                # A negative/zero delta means tires were changed (wear went
                # back up) -- don't let that skew the wear-rate average.
                self._wear_rate.append(per_lap)

        self._last_lap = lap
        self._worst_at_lap_start = worst

    @property
    def avg_wear_per_lap(self) -> float | None:
        if not self._wear_rate:
            return None
        return sum(self._wear_rate) / len(self._wear_rate)

    def snapshot(self) -> TireState:
        avg = self.avg_wear_per_lap
        laps_remaining = (self._current_worst / avg) if avg and self._current_worst is not None else None
        return TireState(
            worst_wear_remaining=self._current_worst,
            avg_wear_per_lap=avg,
            laps_remaining_on_tires=laps_remaining,
            samples=len(self._wear_rate),
            worst_tire_position=self._worst_position,
            worst_tire_temp=self._worst_temp,
        )

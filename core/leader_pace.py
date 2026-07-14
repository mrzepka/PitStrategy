"""Tracks a rolling average of the race *leader's* lap times, independent of
who's actually in P1 at any given moment.

This exists specifically for estimating "laps remaining" in a time-certain
race: the checkered flag falls when the leader completes the lap during
which the session clock expires, not when the player does -- so the
player's own pace (especially mid-pit-stop, or stuck in traffic) is a
biased proxy for how many laps are actually left. iRacing's own
`SessionLapsRemainEx` does something similar internally, but this gives the
overlay its own transparent, independently-computed version to drive a
fuel-to-finish comparison from.
"""
from collections import deque
from dataclasses import dataclass


@dataclass
class LeaderPaceState:
    avg_lap_time_s: float | None
    samples: int


class LeaderPaceTracker:
    def __init__(self, history_len: int = 5):
        self._lap_times: deque[float] = deque(maxlen=history_len)
        self._last_seen: float | None = None

    def update(self, leader_last_lap_time: float | None) -> None:
        """Call every tick with the current P1 car's last-lap-time reading
        (e.g. `car_idx_last_lap_time[leader_idx]`). iRacing holds that value
        steady between the leader's own laps, so only a *changed* value
        means a new lap was actually completed -- a naive per-tick append
        would otherwise count the same lap many times over."""
        if not leader_last_lap_time or leader_last_lap_time <= 0:
            return
        if leader_last_lap_time != self._last_seen:
            self._lap_times.append(leader_last_lap_time)
            self._last_seen = leader_last_lap_time

    def snapshot(self) -> LeaderPaceState:
        if not self._lap_times:
            return LeaderPaceState(avg_lap_time_s=None, samples=0)
        avg = sum(self._lap_times) / len(self._lap_times)
        return LeaderPaceState(avg_lap_time_s=avg, samples=len(self._lap_times))

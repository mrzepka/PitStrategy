"""Detects when a qualifying-type session ends, so `StrategyEngine` can
snapshot the live fuel/lap-time rolling averages as a baseline for the
pre-race planner -- instead of the driver having to guess numbers by hand.

iRacing reports session type as a free-text string per session slot
("Practice", "Open Qualify", "Lone Qualify", "Race", "Warmup", "Offline
Testing", ...), not a fixed enum, so qualifying-ness is decided by a
substring match. What actually marks "qualifying just ended" is
`SessionNum` (the currently active session slot) changing to a different
value -- that's iRacing's own signal for "we moved on to the next session
on the schedule," and is far more reliable than trying to infer it from lap
resets or fuel jumps.
"""
from dataclasses import dataclass


def is_qualifying_session(session_type: str | None) -> bool:
    return bool(session_type) and "qualify" in session_type.lower()


@dataclass
class SessionBaseline:
    fuel_per_lap: float
    lap_time_s: float
    fuel_samples: int
    lap_time_samples: int
    session_type: str
    captured_at_lap: int


class SessionTransitionTracker:
    """Call `check(session_num, session_type)` once per tick, before feeding
    that tick's data into the live trackers. Returns the *previous*
    session_type string if `session_num` just changed (a real transition),
    else None. Never fires on the very first observation, since there's
    nothing to transition from yet."""

    def __init__(self):
        self._last_session_num: int | None = None
        self._last_session_type: str | None = None

    def check(self, session_num: int | None, session_type: str | None) -> str | None:
        transitioned_from = None
        if (
            session_num is not None
            and self._last_session_num is not None
            and session_num != self._last_session_num
        ):
            transitioned_from = self._last_session_type
        self._last_session_num = session_num
        self._last_session_type = session_type
        return transitioned_from

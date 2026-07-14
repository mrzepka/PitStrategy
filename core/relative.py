"""Tracks the cars nearest the player by race position, for undercut/overcut
comparisons: gap, their last lap time vs. the player's, and whether they've
already made a pit stop this session.
"""
from dataclasses import dataclass


@dataclass
class RivalCar:
    car_idx: int
    car_number: str
    position: int
    gap_positions: int  # negative = ahead, positive = behind
    last_lap_time: float | None
    delta_to_my_last_lap: float | None  # positive = they're slower than me
    has_pitted: bool


class RelativeTracker:
    def __init__(self):
        self._has_pitted: dict[int, bool] = {}

    def update_pit_status(self, car_idx_on_pit_road: list[bool]) -> None:
        for idx, on_pit_road in enumerate(car_idx_on_pit_road):
            if on_pit_road:
                self._has_pitted[idx] = True

    def nearby_cars(
        self,
        player_car_idx: int | None,
        car_idx_position: list[int],
        car_idx_last_lap_time: list[float],
        car_numbers: dict[int, str],
        my_last_lap_time: float | None,
        count: int = 3,
    ) -> dict[str, list[RivalCar]]:
        if player_car_idx is None or player_car_idx >= len(car_idx_position):
            return {"ahead": [], "behind": []}

        my_position = car_idx_position[player_car_idx]
        if not my_position or my_position <= 0:
            return {"ahead": [], "behind": []}

        ranked = sorted(
            (
                (idx, pos)
                for idx, pos in enumerate(car_idx_position)
                if pos and pos > 0 and idx != player_car_idx
            ),
            key=lambda item: item[1],
        )

        ahead = [item for item in ranked if item[1] < my_position][-count:]
        ahead.reverse()  # nearest-first (closest position to the player first)
        behind = [item for item in ranked if item[1] > my_position][:count]

        def build(idx: int, pos: int) -> RivalCar:
            lap_time = car_idx_last_lap_time[idx] if idx < len(car_idx_last_lap_time) else None
            if not lap_time or lap_time <= 0:
                lap_time = None
            delta = (lap_time - my_last_lap_time) if (lap_time is not None and my_last_lap_time) else None
            return RivalCar(
                car_idx=idx,
                car_number=car_numbers.get(idx, "?"),
                position=pos,
                gap_positions=pos - my_position,
                last_lap_time=lap_time,
                delta_to_my_last_lap=delta,
                has_pitted=self._has_pitted.get(idx, False),
            )

        return {
            "ahead": [build(idx, pos) for idx, pos in ahead],
            "behind": [build(idx, pos) for idx, pos in behind],
        }

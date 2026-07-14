import pytest

from core.tires import TireTracker, _tread_side_label


def wear(value):
    return {
        "LFwearL": value, "LFwearM": value, "LFwearR": value,
        "RFwearL": value, "RFwearM": value, "RFwearR": value,
        "LRwearL": value, "LRwearM": value, "LRwearR": value,
        "RRwearL": value, "RRwearM": value, "RRwearR": value,
    }


def temps(value):
    return {
        "LFtempCL": value, "LFtempCM": value, "LFtempCR": value,
        "RFtempCL": value, "RFtempCM": value, "RFtempCR": value,
        "LRtempCL": value, "LRtempCM": value, "LRtempCR": value,
        "RRtempCL": value, "RRtempCM": value, "RRtempCR": value,
    }


def test_no_data_yet_returns_none():
    tracker = TireTracker()
    snap = tracker.snapshot()
    assert snap.avg_wear_per_lap is None
    assert snap.laps_remaining_on_tires is None


def test_tracks_worst_corner_and_wear_rate():
    tracker = TireTracker()
    v = wear(1.0)
    tracker.update(lap=0, wear_values=v)
    v2 = wear(1.0)
    v2["RRwearR"] = 0.95  # RR is wearing fastest
    tracker.update(lap=1, wear_values=v2)
    v3 = dict(v2)
    v3["RRwearR"] = 0.90
    tracker.update(lap=2, wear_values=v3)

    snap = tracker.snapshot()
    assert snap.worst_wear_remaining == 0.90
    assert round(snap.avg_wear_per_lap, 4) == 0.05
    assert round(snap.laps_remaining_on_tires, 2) == round(0.90 / 0.05, 2)


def test_worst_tire_position_and_temp_reported():
    tracker = TireTracker()
    v = wear(1.0)
    v["RRwearR"] = 0.90  # RR-R is the worst from the start -- R on a right-side corner is the outboard edge
    tracker.update(lap=0, wear_values=v, temps=temps(85.0))

    snap = tracker.snapshot()
    assert snap.worst_tire_position == "RR-O"
    assert snap.worst_tire_temp == 85.0


def test_worst_tire_position_updates_when_the_worst_corner_changes():
    tracker = TireTracker()
    v1 = wear(1.0)
    v1["LFwearM"] = 0.80  # LF-M starts as the worst -- M is the same regardless of side
    t1 = temps(70.0)
    t1["LFtempCM"] = 95.0
    tracker.update(lap=0, wear_values=v1, temps=t1)
    assert tracker.snapshot().worst_tire_position == "LF-M"
    assert tracker.snapshot().worst_tire_temp == 95.0

    v2 = wear(1.0)
    v2["LFwearM"] = 0.80
    v2["RRwearL"] = 0.70  # RR-L overtakes as the new worst -- L on a right-side corner is the inboard edge
    t2 = temps(70.0)
    t2["LFtempCM"] = 95.0
    t2["RRtempCL"] = 102.0
    tracker.update(lap=1, wear_values=v2, temps=t2)

    snap = tracker.snapshot()
    assert snap.worst_tire_position == "RR-I"
    assert snap.worst_tire_temp == 102.0


def test_worst_tire_temp_none_without_temps_data():
    tracker = TireTracker()
    tracker.update(lap=0, wear_values=wear(1.0))  # no temps passed at all
    snap = tracker.snapshot()
    assert snap.worst_tire_position == "LF-O"  # L on a left-side corner is the outboard edge -- still identified from wear alone
    assert snap.worst_tire_temp is None


@pytest.mark.parametrize(
    "corner,tread,expected",
    [
        # Left-side corners: L is outboard (away from centerline), R is inboard.
        ("LF", "L", "O"), ("LF", "M", "M"), ("LF", "R", "I"),
        ("LR", "L", "O"), ("LR", "M", "M"), ("LR", "R", "I"),
        # Right-side corners: mirrored -- L is inboard, R is outboard.
        ("RF", "L", "I"), ("RF", "M", "M"), ("RF", "R", "O"),
        ("RR", "L", "I"), ("RR", "M", "M"), ("RR", "R", "O"),
    ],
)
def test_tread_side_label_mirrors_by_car_side(corner, tread, expected):
    assert _tread_side_label(corner, tread) == expected


def test_tire_change_is_discarded_as_outlier():
    tracker = TireTracker()
    tracker.update(lap=0, wear_values=wear(1.0))
    tracker.update(lap=1, wear_values=wear(0.9))  # wore 0.1
    tracker.update(lap=2, wear_values=wear(1.0))  # tires changed -- discard
    tracker.update(lap=3, wear_values=wear(0.9))  # wore 0.1 again

    snap = tracker.snapshot()
    assert round(snap.avg_wear_per_lap, 4) == 0.1

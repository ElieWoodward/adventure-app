"""Tests for planner.py. None of these use the internet."""

import random

import config
import planner

CENTER = {"lat": 37.7650, "lon": -122.2416}  # Alameda, CA (zip 94501)
MONDAY, SATURDAY, SUNDAY = 0, 5, 6


def make_place(pid, label, groups, lat_offset, hours=None):
    """A fake place `lat_offset` degrees north of CENTER (0.01 degrees is about 0.69 miles)."""
    return {
        "id": f"node/{pid}", "name": f"{label} {pid}", "label": label, "groups": groups,
        "lat": CENTER["lat"] + lat_offset, "lon": CENTER["lon"],
        "address": "", "opening_hours": hours,
    }


def full_town():
    """Enough fake places to fill every slot."""
    return [
        make_place(1, "Park", ["outdoor"], 0.001),
        make_place(2, "Restaurant", ["lunch", "dinner"], 0.002),
        make_place(3, "Museum", ["activity"], 0.003),
        make_place(4, "Ice Cream", ["treat"], 0.004),
        make_place(5, "Bowling", ["activity"], 0.005),
        make_place(6, "Restaurant", ["lunch", "dinner"], 0.006),
        make_place(7, "Garden", ["outdoor"], 0.007),
    ]


# --- distance ------------------------------------------------------------------
def test_haversine_same_point_is_zero():
    assert planner.haversine_miles(37.0, -122.0, 37.0, -122.0) == 0


def test_haversine_known_distance():
    # San Francisco to Los Angeles is about 347 miles in a straight line.
    miles = planner.haversine_miles(37.7749, -122.4194, 34.0522, -118.2437)
    assert 340 < miles < 355


def test_one_degree_of_latitude_is_about_69_miles():
    assert abs(planner.haversine_miles(0, 0, 1, 0) - 69.1) < 0.5


# --- time window ----------------------------------------------------------------
def test_slots_stay_inside_the_day():
    start, end = planner.to_minutes(config.DAY_START), planner.to_minutes(config.DAY_END)
    for slot in config.TIME_SLOTS:
        assert start <= planner.to_minutes(slot["start"]) < planner.to_minutes(slot["end"]) <= end


def test_slots_are_in_order_without_overlap():
    for earlier, later in zip(config.TIME_SLOTS, config.TIME_SLOTS[1:]):
        assert planner.to_minutes(earlier["end"]) <= planner.to_minutes(later["start"])


def test_day_runs_10am_to_8pm():
    assert config.DAY_START == "10:00" and config.DAY_END == "20:00"
    assert config.TIME_SLOTS[0]["start"] == "10:00"
    assert config.TIME_SLOTS[-1]["end"] == "20:00"


def test_pretty_time():
    assert planner.pretty_time("10:00") == "10:00 AM"
    assert planner.pretty_time("12:00") == "12:00 PM"
    assert planner.pretty_time("15:30") == "3:30 PM"


# --- opening hours ---------------------------------------------------------------
def test_unknown_hours_are_kept():
    assert planner.is_open(None, MONDAY, "10:00", "12:00") is None
    assert planner.is_open("sunrise-sunset", MONDAY, "10:00", "12:00") is None
    assert planner.is_open("garbage!!", MONDAY, "10:00", "12:00") is None


def test_open_all_the_time():
    assert planner.is_open("24/7", SUNDAY, "18:00", "20:00") is True


def test_closed_on_a_day_off():
    hours = "Tu-Su 10:00-17:00; Mo off"
    assert planner.is_open(hours, MONDAY, "13:00", "15:30") is False
    assert planner.is_open(hours, SATURDAY, "13:00", "15:30") is True


def test_closed_during_the_slot():
    # A lunch-only place is closed at dinner time.
    assert planner.is_open("Mo-Su 11:00-14:00", MONDAY, "18:00", "20:00") is False
    assert planner.is_open("Mo-Su 11:00-14:00", MONDAY, "12:00", "13:00") is True


def test_days_not_listed_are_closed():
    assert planner.is_open("Mo-Fr 09:00-17:00", SUNDAY, "10:00", "12:00") is False


def test_common_real_world_spellings():
    assert planner.is_open("Tu-Th 11:00-13:00, 17:00-20:30", MONDAY, "18:00", "20:00") is False
    assert planner.is_open("Tu-Th 11:00-13:00, 17:00-20:30", 1, "18:00", "20:00") is True
    assert planner.is_open("Mo-Sa 17:00-21:30; Su Off", SUNDAY, "18:00", "20:00") is False


def test_split_hours_and_past_midnight():
    assert planner.is_open("Mo-Su 11:00-14:00,17:00-22:00", MONDAY, "18:00", "20:00") is True
    assert planner.is_open("Fr-Sa 18:00-02:00", SATURDAY, "18:00", "20:00") is True


# --- building the plan ------------------------------------------------------------
def test_full_plan_has_six_stops_in_slot_order():
    stops = planner.build_plan(full_town(), CENTER, 5, MONDAY, random.Random(1))
    assert [s["slot"] for s in stops] == [slot["name"] for slot in config.TIME_SLOTS]


def test_no_place_is_repeated():
    for seed in range(20):
        stops = planner.build_plan(full_town(), CENTER, 5, MONDAY, random.Random(seed))
        ids = [s["place"]["id"] for s in stops]
        assert len(ids) == len(set(ids))


def test_stops_match_their_slot_type():
    stops = planner.build_plan(full_town(), CENTER, 5, MONDAY, random.Random(2))
    by_slot = {s["slot"]: s["place"] for s in stops}
    assert "outdoor" in by_slot["Morning"]["groups"]
    assert "lunch" in by_slot["Lunch"]["groups"]
    assert "activity" in by_slot["Afternoon"]["groups"]
    assert "treat" in by_slot["Treat"]["groups"]
    assert "dinner" in by_slot["Dinner"]["groups"]


def test_late_afternoon_avoids_repeating_the_activity_type():
    for seed in range(20):
        stops = planner.build_plan(full_town(), CENTER, 5, MONDAY, random.Random(seed))
        by_slot = {s["slot"]: s["place"]["label"] for s in stops}
        assert by_slot["Late afternoon"] not in (by_slot["Afternoon"], by_slot["Morning"])


def test_missing_slot_is_skipped():
    town = [p for p in full_town() if p["label"] != "Ice Cream"]
    stops = planner.build_plan(town, CENTER, 5, MONDAY, random.Random(3))
    assert "Treat" not in [s["slot"] for s in stops]
    assert len(stops) == 5


def test_places_outside_the_range_are_never_used():
    # The only ice cream shop is about 35 miles away, outside the 5-mile range.
    town = [p for p in full_town() if p["label"] != "Ice Cream"]
    town.append(make_place(99, "Ice Cream", ["treat"], 0.5))
    stops = planner.build_plan(town, CENTER, 5, MONDAY, random.Random(4))
    assert all(s["place"]["id"] != "node/99" for s in stops)


def test_closed_places_are_skipped():
    town = full_town()
    for p in town:
        if p["label"] == "Museum":
            p["opening_hours"] = "Tu-Su 10:00-17:00; Mo off"
    stops = planner.build_plan(town, CENTER, 5, MONDAY, random.Random(5))
    assert all(s["place"]["label"] != "Museum" for s in stops)


def test_prefers_nearby_stop_over_far_one():
    near = make_place(1, "Park", ["outdoor"], 0.01)   # about 0.7 miles
    far = make_place(2, "Garden", ["outdoor"], 0.10)  # about 6.9 miles
    for seed in range(20):
        place, miles = planner.choose_next([near, far], CENTER, set(), random.Random(seed))
        assert place is near
        assert miles < config.PREFERRED_HOP_MILES


def test_relaxes_distance_when_nothing_is_close():
    far = make_place(2, "Garden", ["outdoor"], 0.10)  # about 6.9 miles, the only option
    place, miles = planner.choose_next([far], CENTER, set(), random.Random(0))
    assert place is far
    assert 6 < miles < 8


def test_no_candidates_returns_none():
    assert planner.choose_next([], CENTER, set(), random.Random(0)) == (None, None)


def test_randomness_gives_different_plans():
    # Several parks close together: different random seeds should not all pick the same one.
    town = [make_place(i, "Park", ["outdoor"], 0.001 * i) for i in range(1, 11)]
    picks = {
        planner.build_plan(town, CENTER, 5, MONDAY, random.Random(seed))[0]["place"]["id"]
        for seed in range(20)
    }
    assert len(picks) > 1


def test_picks_from_about_ten_nearest_for_variety():
    # 15 parks all within 2 miles: picks should spread over the nearest 10, never beyond.
    parks = [make_place(i, "Park", ["outdoor"], 0.001 * i) for i in range(1, 16)]
    picked = {planner.choose_next(parks, CENTER, set(), random.Random(seed))[0]["id"] for seed in range(300)}
    nearest_ten = {p["id"] for p in parks[:config.NEAREST_CHOICES]}
    assert config.NEAREST_CHOICES >= 8
    assert picked == nearest_ten

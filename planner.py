"""
The plan-building logic. Nothing in this file talks to the internet,
so it is easy to test with made-up places.

A "place" is a plain dict like:
    {"id": "node/123", "name": "Lincoln Park", "label": "Park",
     "groups": ["outdoor"], "lat": 37.76, "lon": -122.24,
     "address": "1 Main St", "opening_hours": "Mo-Su 08:00-20:00"}
"""

import math
import re

import config

EARTH_RADIUS_MILES = 3958.8


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------
def haversine_miles(lat1, lon1, lat2, lon2):
    """Straight-line distance in miles between two points on Earth."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def distance_between(a, b):
    """Distance in miles between two things that have "lat" and "lon"."""
    return haversine_miles(a["lat"], a["lon"], b["lat"], b["lon"])


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def to_minutes(hhmm):
    """'13:30' -> 810 (minutes after midnight)."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def pretty_time(hhmm):
    """'13:30' -> '1:30 PM'."""
    total = to_minutes(hhmm)
    hours, minutes = divmod(total, 60)
    suffix = "AM" if hours < 12 else "PM"
    hours = hours % 12 or 12
    return f"{hours}:{minutes:02d} {suffix}"


# ---------------------------------------------------------------------------
# Opening hours (a deliberately simple parser for the common OSM formats)
# ---------------------------------------------------------------------------
DAY_NAMES = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]  # Monday = 0, like Python
DAYS_PATTERN = r"[A-Z][a-z](?:-[A-Z][a-z])?(?:,[A-Z][a-z](?:-[A-Z][a-z])?)*"
TIMES_PATTERN = r"\d{1,2}:\d{2}-\d{1,2}:\d{2}(?:,\d{1,2}:\d{2}-\d{1,2}:\d{2})*"
RULE_RE = re.compile(rf"^(?:({DAYS_PATTERN})\s+)?({TIMES_PATTERN}|[Oo]ff|[Cc]losed)$")


def _parse_days(text):
    """'Mo-We,Sa' -> {0, 1, 2, 5}. Raises ValueError on unknown day names."""
    days = set()
    for part in text.split(","):
        if "-" in part:
            first, last = (DAY_NAMES.index(d) for d in part.split("-"))
            day = first
            days.add(day)
            while day != last:             # handles wrap-around like "Fr-Mo"
                day = (day + 1) % 7
                days.add(day)
        else:
            days.add(DAY_NAMES.index(part))
    return days


def parse_opening_hours(text):
    """
    Turn an OSM opening_hours string into {weekday: [(start_min, end_min), ...]}.
    Returns None if the format is anything we don't understand.

    Understands things like:
        "24/7"
        "Mo-Fr 09:00-17:00; Sa 10:00-14:00"
        "Tu-Su 11:00-14:00,17:00-22:00; Mo off"
    """
    if not text:
        return None
    text = re.sub(r",\s+", ",", text.strip())   # "11:00-14:00, 17:00-22:00" -> no spaces
    if text == "24/7":
        return {day: [(0, 24 * 60)] for day in range(7)}

    schedule = {day: [] for day in range(7)}   # days never mentioned = closed
    understood_any_rule = False
    for rule in text.split(";"):
        rule = rule.strip()
        if not rule or rule.startswith(("PH", "SH")):
            continue                            # ignore holiday rules
        match = RULE_RE.match(rule)
        if not match:
            return None                         # something fancy: give up safely
        try:
            days = _parse_days(match.group(1)) if match.group(1) else set(range(7))
        except ValueError:
            return None
        intervals = []
        if match.group(2).lower() not in ("off", "closed"):
            for span in match.group(2).split(","):
                start, end = (to_minutes(t) for t in span.split("-"))
                if end <= start:                # e.g. 18:00-02:00 goes past midnight
                    end += 24 * 60
                intervals.append((start, end))
        for day in days:
            schedule[day] = intervals           # later rules override earlier ones
        understood_any_rule = True
    return schedule if understood_any_rule else None


def is_open(opening_hours_text, weekday, start_hhmm, end_hhmm):
    """
    True  = open for a decent part of the time slot,
    False = clearly closed,
    None  = we don't know (missing or unparseable hours).
    """
    try:
        schedule = parse_opening_hours(opening_hours_text)
    except Exception:                           # never let odd data crash the app
        return None
    if schedule is None:
        return None
    slot_start, slot_end = to_minutes(start_hhmm), to_minutes(end_hhmm)
    needed = min(config.MIN_OPEN_MINUTES, slot_end - slot_start)
    for open_start, open_end in schedule[weekday]:
        overlap = min(slot_end, open_end) - max(slot_start, open_start)
        if overlap >= needed:
            return True
    return False


# ---------------------------------------------------------------------------
# Choosing stops
# ---------------------------------------------------------------------------
def choose_next(candidates, here, used_labels, rng):
    """
    Pick the next stop from `candidates`, close to `here`.

    Start with places within PREFERRED_HOP_MILES. If there are none, widen the
    limit step by step. Inside the allowed pool, prefer activity types we
    haven't used yet, then pick randomly among the nearest few.
    Returns (place, distance_in_miles) or (None, None).
    """
    if not candidates:
        return None, None
    with_distance = [(distance_between(here, p), p) for p in candidates]
    farthest = max(d for d, _ in with_distance)

    limit = config.PREFERRED_HOP_MILES
    while True:
        pool = [(d, p) for d, p in with_distance if d <= limit]
        if pool:
            fresh = [(d, p) for d, p in pool if p["label"] not in used_labels]
            if fresh:
                pool = fresh
            pool.sort(key=lambda pair: pair[0])
            distance, place = rng.choice(pool[: config.NEAREST_CHOICES])
            return place, distance
        if limit >= farthest:      # can't happen, but guarantees the loop ends
            return None, None
        limit += config.HOP_STEP_MILES


def build_plan(places, center, max_miles, weekday, rng):
    """
    Build the day. `center` is {"lat": .., "lon": ..} for the zip code,
    `weekday` is 0 (Monday) to 6 (Sunday), `rng` is a random.Random.
    Returns a list of stop dicts in time order.
    """
    # Only consider places inside the user's chosen range.
    in_range = [p for p in places if distance_between(center, p) <= max_miles]

    stops = []
    used_ids = set()
    used_labels = set()
    here = center
    for slot in config.TIME_SLOTS:
        candidates = [
            p for p in in_range
            if p["id"] not in used_ids
            and any(g in slot["groups"] for g in p["groups"])
            and is_open(p.get("opening_hours"), weekday, slot["start"], slot["end"]) is not False
        ]
        place, distance = choose_next(candidates, here, used_labels, rng)
        if place is None:
            continue                 # skip this slot gracefully
        stops.append({
            "slot": slot["name"],
            "start": pretty_time(slot["start"]),
            "end": pretty_time(slot["end"]),
            "place": place,
            "miles_from_previous": round(distance, 1),
            "is_first": not stops,
        })
        used_ids.add(place["id"])
        used_labels.add(place["label"])
        here = place
    return stops

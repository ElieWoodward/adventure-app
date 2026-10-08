"""
Talking to the outside world: zip code lookup and the Overpass places search.
Every failure is turned into a PlaceDataError with a friendly message.
"""

import math
import sys
import time

import requests

import config
import planner

HEADERS = {"User-Agent": config.USER_AGENT}


def use_windows_certificates():
    """
    On Windows, make Python trust the same security certificates Windows trusts.
    This fixes "certificate verify failed" errors when an antivirus (like Avast)
    inspects secure web traffic. It is optional: if the `truststore` package is
    missing or anything goes wrong, Python's normal certificates are used instead.
    Returns True if it was switched on.
    """
    if sys.platform != "win32":
        return False                    # Render runs Linux; its normal certificates work fine
    try:
        import truststore
        truststore.inject_into_ssl()
        return True
    except Exception:
        return False


use_windows_certificates()

# In-memory cache: {(zip, miles): (time_saved, result)}
_cache = {}


class PlaceDataError(Exception):
    """Something went wrong getting data. The message is safe to show users."""


class ZipNotFoundError(PlaceDataError):
    """The zip code doesn't exist (or the zip service doesn't know it)."""


def lookup_zip(zip_code):
    """Return {"lat", "lon", "place"} for a US zip code."""
    url = config.ZIP_API_URL.format(zip=zip_code)
    try:
        response = requests.get(url, headers=HEADERS, timeout=config.ZIP_TIMEOUT_SECONDS)
    except requests.RequestException:
        raise PlaceDataError("We couldn't reach the zip code service. Please try again in a minute.")
    if response.status_code == 404:
        raise ZipNotFoundError(f"We couldn't find zip code {zip_code}. Please check it and try again.")
    if response.status_code != 200:
        raise PlaceDataError("The zip code service had a problem. Please try again in a minute.")
    try:
        first = response.json()["places"][0]
        return {
            "lat": float(first["latitude"]),
            "lon": float(first["longitude"]),
            "place": f'{first["place name"]}, {first["state abbreviation"]}',
        }
    except (ValueError, KeyError, IndexError):
        raise PlaceDataError("The zip code service sent back something unexpected. Please try again.")


def build_query(lat, lon, miles):
    """
    One Overpass query asking for every place type in config.PLACE_TYPES.

    We search a square box around the center because Overpass answers that much
    faster than a circle; fetch_places() trims the results to a circle afterwards.
    Tags with the same key are grouped, e.g. amenity=restaurant|cafe|library.
    """
    dlat = miles / 69.0                                   # 1 degree of latitude is about 69 miles
    dlon = miles / (69.0 * math.cos(math.radians(lat)))   # longitude degrees shrink away from the equator
    box = f"{lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f}"

    values_by_key = {}
    for key, value, _label, _groups in config.PLACE_TYPES:
        values_by_key.setdefault(key, []).append(value)
    lines = [
        f'  nwr["{key}"~"^({"|".join(values)})$"]["name"];'
        for key, values in values_by_key.items()
    ]
    return (
        f"[out:json][timeout:{config.OVERPASS_TIMEOUT_SECONDS}]"
        f"[maxsize:{config.OVERPASS_MAXSIZE_BYTES}][bbox:{box}];\n(\n"
        + "\n".join(lines)
        + "\n);\nout center tags;"
    )


def _address(tags):
    """Build a short address from OSM addr:* tags, or '' if there isn't one."""
    street = tags.get("addr:street", "")
    if street and tags.get("addr:housenumber"):          # a house number alone isn't useful
        street = f'{tags["addr:housenumber"]} {street}'
    parts = [p for p in (street, tags.get("addr:city")) if p]
    return ", ".join(parts)


def element_to_place(element):
    """Convert one Overpass element into our place dict (or None if unusable)."""
    tags = element.get("tags", {})
    name = tags.get("name")
    # Nodes have lat/lon directly; ways and relations have a "center".
    lat = element.get("lat", element.get("center", {}).get("lat"))
    lon = element.get("lon", element.get("center", {}).get("lon"))
    if not name or lat is None or lon is None:
        return None
    for key, value, label, groups in config.PLACE_TYPES:
        if tags.get(key) == value:
            return {
                "id": f'{element["type"]}/{element["id"]}',
                "name": name,
                "label": label,
                "groups": groups,
                "lat": lat,
                "lon": lon,
                "address": _address(tags),
                "opening_hours": tags.get("opening_hours"),
            }
    return None


def fetch_places(lat, lon, miles):
    """Ask Overpass for places, trying each server in order."""
    query = build_query(lat, lon, miles)
    for url in config.OVERPASS_URLS:
        try:
            response = requests.post(
                url, data={"data": query}, headers=HEADERS,
                timeout=config.OVERPASS_TIMEOUT_SECONDS,
            )
            if response.status_code != 200:
                continue                        # busy or broken: try the next server
            data = response.json()
            # Overpass reports server-side timeouts in a "remark" with no results.
            if "remark" in data and not data.get("elements"):
                continue
        except (requests.RequestException, ValueError):
            continue                            # timeout, network error or bad JSON
        places = [element_to_place(e) for e in data.get("elements", [])]
        center = {"lat": lat, "lon": lon}
        return [p for p in places if p is not None and planner.distance_between(center, p) <= miles]
    raise PlaceDataError(
        "The map service is busy or not responding right now. "
        "Please wait a minute and try again, or try a smaller mile range."
    )


def has_enough(places):
    """True if every kind of stop in the day has at least a few places to choose from."""
    for slot in config.TIME_SLOTS:
        count = sum(1 for p in places if any(g in slot["groups"] for g in p["groups"]))
        if count < config.ENOUGH_PLACES_PER_SLOT:
            return False
    return True


def get_area(zip_code, miles):
    """
    Return {"center": {...}, "places": [...]} for a zip code and radius.

    To stay fast and reliable, we first search a smaller circle (FIRST_SEARCH_MILES).
    Each stop is picked from the nearest places anyway, so in towns and cities that
    is plenty. Only if it isn't enough do we search the user's full range.
    Results are cached for CACHE_SECONDS so "Try another plan" is fast.
    """
    now = time.time()
    # Throw away old entries so the cache can't grow forever.
    # (list() takes a snapshot, which is safe even if another request adds an entry.)
    for old_key, (saved_at, _) in list(_cache.items()):
        if now - saved_at >= config.CACHE_SECONDS:
            _cache.pop(old_key, None)

    key = (zip_code, miles)
    saved = _cache.get(key)
    if saved:
        return saved[1]

    center = lookup_zip(zip_code)
    first_miles = min(miles, config.FIRST_SEARCH_MILES)
    found = fetch_places(center["lat"], center["lon"], first_miles)
    if miles > first_miles and not has_enough(found):
        try:
            wider = fetch_places(center["lat"], center["lon"], miles)
            if len(wider) > len(found):
                found = wider
        except PlaceDataError:
            pass                                # keep what the smaller search found

    result = {"center": center, "places": found}
    _cache[key] = (now, result)                # only successful results are cached
    return result

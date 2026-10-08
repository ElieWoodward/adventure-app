"""
All settings for the Adventure app live here so they are easy to find and change.
"""

# ---------------------------------------------------------------------------
# Outside data sources (free, no API key needed)
# ---------------------------------------------------------------------------
ZIP_API_URL = "https://api.zippopotam.us/us/{zip}"
OVERPASS_URLS = [                                       # tried in this order
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "AdventureApp/1.0 (school project; github.com/ElieWoodward)"
ZIP_TIMEOUT_SECONDS = 10
OVERPASS_TIMEOUT_SECONDS = 25   # longest wait for any single Overpass request
OVERPASS_TOTAL_SECONDS = 90     # time budget for ALL Overpass attempts in one request
                                # (zip lookup + this must stay under gunicorn's 120s timeout)
BUSY_RETRY_WAIT_SECONDS = 2     # if a server says it's busy, wait this long and retry once
OVERPASS_MAXSIZE_BYTES = 128 * 1024 * 1024   # asking for less memory helps busy servers accept the query
FIRST_SEARCH_MILES = 5           # search this close first; only search the full range if needed
ENOUGH_PLACES_PER_SLOT = 3       # "needed" = some part of the day has fewer choices than this
CACHE_SECONDS = 10 * 60          # keep Overpass results in memory for 10 minutes

# ---------------------------------------------------------------------------
# Form limits
# ---------------------------------------------------------------------------
MIN_MILES = 1
MAX_MILES = 25
DEFAULT_MILES = 5

# ---------------------------------------------------------------------------
# Plan building
# ---------------------------------------------------------------------------
DAY_START = "10:00"              # nothing is scheduled before this...
DAY_END = "20:00"                # ...or after this (24-hour clock)
MIN_STOPS = 3                    # fewer stops than this = suggest a bigger range
PREFERRED_HOP_MILES = 2.0        # try to keep each stop this close to the last one
HOP_STEP_MILES = 2.0             # if nothing fits, widen the limit by this much each try
NEAREST_CHOICES = 10             # pick randomly among this many nearest candidates
MIN_OPEN_MINUTES = 30            # a place must be open at least this long during a slot

# The shape of the day. Each slot lists which place groups can fill it.
# Times are 24-hour "HH:MM".
TIME_SLOTS = [
    {"name": "Morning",        "start": "10:00", "end": "12:00", "groups": ["outdoor"]},
    {"name": "Lunch",          "start": "12:00", "end": "13:00", "groups": ["lunch"]},
    {"name": "Afternoon",      "start": "13:00", "end": "15:30", "groups": ["activity"]},
    {"name": "Treat",          "start": "15:30", "end": "16:30", "groups": ["treat"]},
    {"name": "Late afternoon", "start": "16:30", "end": "18:00", "groups": ["activity", "outdoor"]},
    {"name": "Dinner",         "start": "18:00", "end": "20:00", "groups": ["dinner"]},
]

# Which OpenStreetMap tags we look for.
# (osm key, osm value, label shown to the user, groups it belongs to)
PLACE_TYPES = [
    # Outdoor / easygoing
    ("leisure", "park",            "Park",           ["outdoor"]),
    ("leisure", "garden",          "Garden",         ["outdoor"]),
    ("tourism", "viewpoint",       "Viewpoint",      ["outdoor"]),
    ("natural", "beach",           "Beach",          ["outdoor"]),
    ("leisure", "nature_reserve",  "Nature Reserve", ["outdoor"]),
    ("leisure", "playground",      "Playground",     ["outdoor"]),
    # Food
    ("amenity", "restaurant",      "Restaurant",     ["lunch", "dinner"]),
    ("amenity", "cafe",            "Cafe",           ["lunch", "treat"]),
    # Activities
    ("tourism", "museum",          "Museum",         ["activity"]),
    ("tourism", "gallery",         "Gallery",        ["activity"]),
    ("amenity", "library",         "Library",        ["activity"]),
    ("tourism", "attraction",      "Attraction",     ["activity"]),
    ("leisure", "bowling_alley",   "Bowling",        ["activity"]),
    ("leisure", "miniature_golf",  "Mini Golf",      ["activity"]),
    ("leisure", "amusement_arcade", "Arcade",        ["activity"]),
    ("tourism", "zoo",             "Zoo",            ["activity"]),
    ("tourism", "aquarium",        "Aquarium",       ["activity"]),
    # Treats
    ("amenity", "ice_cream",       "Ice Cream",      ["treat"]),
    ("shop",    "bakery",          "Bakery",         ["treat"]),
    ("shop",    "pastry",          "Dessert",        ["treat"]),
]

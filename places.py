"""Turns a latitude and longitude into a name, like "Brazil" or "Pacific Ocean".

Countries come from static/world.json: Natural Earth's country borders (public domain), saved on the Pi
so it works without internet. Oceans and seas use simple latitude/longitude boxes, which is close enough
for a spacecraft 400 km up.
"""
import json, os

_countries = None


def _load():
    global _countries
    if _countries is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "world.json")
        try:
            with open(path) as f:
                _countries = json.load(f)["countries"]
        except (OSError, ValueError):
            _countries = []
    return _countries


def _inside(lon, lat, rings):
    """Ray casting: count how many border lines a ray going east crosses. Odd = inside (holes work too)."""
    inside = False
    for r in rings:
        n = len(r) // 2
        j = n - 1
        for i in range(n):
            xi, yi, xj, yj = r[2 * i], r[2 * i + 1], r[2 * j], r[2 * j + 1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
    return inside


# (name, south, north, west, east) checked in order, before the big oceans
SEAS = [
    ("Mediterranean Sea", 30, 46, -6, 36), ("Black Sea", 40.5, 47, 27, 42), ("Caspian Sea", 36.5, 47.5, 46.5, 55),
    ("Red Sea", 12, 30, 32, 44), ("Persian Gulf", 23, 30.5, 47.5, 57), ("Baltic Sea", 53, 66, 10, 30.5),
    ("North Sea", 51, 61, -4, 9), ("Gulf of Mexico", 18, 31, -98, -81), ("Caribbean Sea", 9, 22, -88, -60),
    ("Hudson Bay", 51, 66, -95, -75), ("Bay of Bengal", 5, 23, 80, 95), ("Arabian Sea", 0, 26, 50, 78),
    ("South China Sea", 0, 25, 99, 121), ("Sea of Japan", 33, 52, 127, 142), ("Tasman Sea", -47, -28, 147, 172),
]


def ocean(lat, lon):
    if lat <= -60:
        return "Southern Ocean"
    if lat >= 66:
        return "Arctic Ocean"
    for name, s, n, w, e in SEAS:
        if s <= lat <= n and w <= lon <= e:
            return name
    if (20 <= lon < 100 and lat < 30) or (100 <= lon < 147 and lat < -10):
        return "Indian Ocean"
    west = -70 if lat < 8 else -84 if lat < 20 else -100       # the Atlantic's western edge (the Americas)
    if west <= lon < 20 or (lat >= 30 and west <= lon < 40):
        return "Atlantic Ocean"
    return "Pacific Ocean"


def place_name(lat, lon):
    """Returns (name, is_water)."""
    for c in _load():
        x = lon + 360 if (c.get("w") and lon < 0) else lon      # Russia and Fiji are stored as 0..360
        w, s, e, n = c["b"]
        if w <= x <= e and s <= lat <= n and _inside(x, lat, c["r"]):
            return c["n"], False
    return ocean(lat, lon), True

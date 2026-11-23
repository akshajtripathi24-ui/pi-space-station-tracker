"""Pi Space Station Tracker - track the International Space Station live on a Raspberry Pi.

Shows where the ISS (plus China's Tiangong station, the Hubble telescope and the newest Starlink train)
is right now on a world map, predicts when it will pass over your town, how bright it will be and how
good the pass is, checks the clouds, and sends an alert to your phone before it flies over.

Run in the background:  bash setup-autostart.sh   (see README.md)
Run by hand:            source venv/bin/activate && python server.py
Then open http://<your-pi>.local:8080  (or http://<your-pi-ip>:8080)
Needs: pip install sgp4
Works with Python 3.9 and newer (Raspberry Pi OS Bullseye or Bookworm).
"""
import json, math, os, secrets, threading, time, urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sgp4.api import Satrec

import places   # places.py: "Brazil" or "Pacific Ocean" from a latitude and longitude
import sky      # sky.py: where the Moon and planets are

PORT = int(os.environ.get("ISS_PORT", "8080"))       # the stock tracker uses 8000, so both can run together
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CONFIG_FILE = os.path.join(HERE, "config.json")      # your settings (location, alerts). Never uploaded to GitHub.
SENT_FILE = os.path.join(DATA, "alerts_sent.json")   # which passes already got an alert
STATE_FILE = os.path.join(DATA, "state.json")        # small things to remember, like the last morning summary
SIGHTINGS_FILE = os.path.join(DATA, "sightings.json")  # your spotter log
HISTORY_FILE = os.path.join(DATA, "history.json")    # the height of each spacecraft from every orbit download

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={}&FORMAT=TLE"
GROUP_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP={}&FORMAT=TLE"
CREW_URL = "http://api.open-notify.org/astros.json"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast?latitude={:.2f}&longitude={:.2f}&hourly=cloud_cover&forecast_days=5"
UA = "pi-space-station-tracker/1.2 (+https://github.com/akshajtripathi24-ui/pi-space-station-tracker)"
TLE_MAX_AGE_H = 12          # download fresh orbit data twice a day (CelesTrak asks people not to download too often)
RECENT_H = 6                # how long after a pass you can still log "I saw it!"

# The spacecraft you can track. "catnr" is the catalog number CelesTrak uses.
# "std_mag" is how bright it is 1000 km away when half lit by the Sun (smaller = brighter). These are estimates.
SATS = {
    "iss": {"name": "ISS", "full": "International Space Station", "catnr": 25544, "crew": "ISS",
            "launched": "1998-11-20", "std_mag": -1.3},
    "tiangong": {"name": "Tiangong", "full": "Tiangong (China's space station)", "catnr": 48274, "crew": "Tiangong",
                 "launched": "2021-04-29", "std_mag": 0.3},
    "hubble": {"name": "Hubble", "full": "Hubble Space Telescope", "catnr": 20580, "crew": None,
               "launched": "1990-04-24", "std_mag": 2.2},
    # The newest Starlink launch: a "train" of satellites in a line, picked from everything launched in the last 30 days
    "starlink": {"name": "Starlink", "full": "Starlink train (the newest SpaceX launch)", "group": "last-30-days",
                 "crew": None, "launched": None, "std_mag": 4.0},
}

# ---------------------------------------------------------------- settings
DEFAULTS = {
    "lat": None, "lon": None, "place": "", "height_m": 0,
    "min_elevation": 10,     # degrees above the horizon that counts as a pass (trees and houses block lower ones)
    "alert_minutes": 10,     # how many minutes before a pass the phone alert arrives
    "alerts_on": True,
    "visible_only": True,    # only alert for passes you can actually SEE (dark sky, lit by the Sun)
    "min_stars": 1,          # only alert for passes rated at least this many stars (1 = every visible pass)
    "alert_sats": ["iss"],   # which spacecraft send alerts
    "summary_on": True,      # one message each morning listing the day's visible passes
    "summary_hour": 8,       # what time the morning summary arrives (0-23, Pi's local time)
    "weather_on": True,      # check the cloud forecast for each pass (uses the free Open-Meteo service)
    "video_url": "",         # optional: your own link for the ISS live video
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
}
_cfg_lock = threading.Lock()
_file_lock = threading.Lock()


def load_config():
    with _cfg_lock:
        cfg = dict(DEFAULTS)
        try:
            with open(CONFIG_FILE) as f:
                cfg.update(json.load(f))
        except (OSError, ValueError):
            pass
        cfg["alert_sats"] = [s for s in cfg.get("alert_sats") or [] if s in SATS]
        if not cfg["ntfy_topic"]:
            cfg["ntfy_topic"] = "iss-" + secrets.token_hex(8)   # random, so nobody can guess it
            _write_json(CONFIG_FILE, cfg)
        return cfg


def save_config(cfg):
    with _cfg_lock:
        _write_json(CONFIG_FILE, cfg)


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

# ---------------------------------------------------------------- orbit data (TLE)
_orbit = {sid: {"rec": None, "train": [], "fetched": 0.0, "error": "", "launched": None} for sid in SATS}


def tle_file(sid):
    return os.path.join(DATA, "tle_%s.txt" % sid)


def tle_epoch(rec):
    """The moment the orbit data was measured, as a unix time."""
    return (rec.jdsatepoch + rec.jdsatepochF - 2440587.5) * 86400


def _parse_tles(text):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    out = []
    for i, l in enumerate(lines):
        if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            name = lines[i - 1] if i > 0 and not lines[i - 1][:2] in ("1 ", "2 ") else ""
            out.append((name, l, lines[i + 1]))
    return out


def newest_starlink_launch(tles):
    """Keep only the Starlink satellites from the newest launch. They fly in a line: the "train"."""
    launches = {}
    for t in tles:
        if t[0].upper().startswith("STARLINK"):
            launches.setdefault(t[1][9:14], []).append(t)   # e.g. "26045" = 2026, launch number 45
    if not launches:
        return []
    return launches[max(launches)]


def _use_tle(sid, text, fetched_at):
    """Read orbit data. Returns the text worth saving."""
    tles = _parse_tles(text)
    group = SATS[sid].get("group")
    if group:
        tles = newest_starlink_launch(tles)
    if not tles:
        raise ValueError("no Starlink launches in the last 30 days" if group else "no TLE lines found")
    recs = [Satrec.twoline2rv(l1, l2) for _, l1, l2 in tles]
    lead = recs[len(recs) // 2]                           # for a train, the satellite in the middle
    _orbit[sid].update(rec=lead, train=recs if group else [], fetched=fetched_at, error="",
                       launched=min(tle_epoch(r) for r in recs) if group else None)
    if not group:
        record_history(sid, lead)
    return "\n".join("\n".join(t) if t[0] else t[1] + "\n" + t[2] for t in tles) + "\n"


def load_saved_tle(sid):
    """Load the orbit data saved last time, so the tracker works straight away (and without internet)."""
    os.makedirs(DATA, exist_ok=True)
    for path in (tle_file(sid), os.path.join(DATA, "iss_tle.txt") if sid == "iss" else None):
        if path and os.path.exists(path):              # (iss_tle.txt is where version 1.0 saved it)
            try:
                with open(path) as f:
                    _use_tle(sid, f.read(), os.path.getmtime(path))
                return
            except (OSError, ValueError) as e:
                log("saved orbit data unreadable:", path, e)


def refresh_tle(sid, force=False):
    """Download fresh orbit data when the saved copy is older than TLE_MAX_AGE_H."""
    os.makedirs(DATA, exist_ok=True)
    o = _orbit[sid]
    age_h = (time.time() - o["fetched"]) / 3600 if o["fetched"] else 1e9
    if not force and age_h < TLE_MAX_AGE_H:
        return
    s = SATS[sid]
    try:
        text = http_get(GROUP_URL.format(s["group"]) if s.get("group") else TLE_URL.format(s["catnr"]))
        keep = _use_tle(sid, text, time.time())
        with open(tle_file(sid), "w") as f:
            f.write(keep)
        log("downloaded fresh orbit data for", s["name"])
        _passes.pop(sid, None)        # recalculate passes with the new data
    except Exception as e:            # keep using the saved copy
        o["error"] = "Couldn't download fresh orbit data (%s). Using the saved copy." % e
        if s.get("group") and isinstance(e, ValueError):
            o["error"] = "There's no Starlink train right now (no Starlink launches in the last 30 days)."
            o.update(rec=None, train=[])
        log(s["name"], o["error"])

# ---------------------------------------------------------------- height history ("watch the ISS fall")


def record_history(sid, rec):
    """Save the average height from each new set of orbit data. Over weeks, this shows the ISS slowly falling."""
    try:
        alt = (rec.alta + rec.altp) / 2 * rec.radiusearthkm   # halfway between the lowest and highest point
    except AttributeError:
        return
    point = [int(tle_epoch(rec)), round(alt, 3)]
    with _file_lock:
        hist = _read_json(HISTORY_FILE, {})
        pts = hist.setdefault(sid, [])
        if any(abs(p[0] - point[0]) < 60 for p in pts):
            return
        pts.append(point)
        pts.sort()
        hist[sid] = pts[-3000:]
        _write_json(HISTORY_FILE, hist)


def get_history(sid):
    pts = _read_json(HISTORY_FILE, {}).get(sid, [])
    boosts = [[b[0], round(b[1] - a[1], 2)] for a, b in zip(pts, pts[1:])
              if b[1] - a[1] > 0.4 and b[0] - a[0] < 5 * 86400]   # jumped up: the engines fired (a "reboost")
    return {"points": pts, "reboosts": boosts}

# ---------------------------------------------------------------- orbit math
RE = 6378.137                        # Earth's radius at the equator, km (WGS-84)
FLAT = 1 / 298.257223563
E2 = FLAT * (2 - FLAT)


def julian(t):
    return t / 86400.0 + 2440587.5


def gmst(jd):
    """Greenwich sidereal time in radians: how far Earth has turned."""
    d = jd - 2451545.0
    T = d / 36525.0
    g = 280.46061837 + 360.98564736629 * d + 0.000387933 * T * T - T ** 3 / 38710000.0
    return math.radians(g % 360.0)


def sat_eci(sid, t, rec=None):
    """Position (km) and velocity (km/s) in space at unix time t."""
    rec = rec or _orbit[sid]["rec"]
    if rec is None:
        raise RuntimeError(_orbit[sid]["error"] or "no orbit data yet for " + SATS[sid]["name"])
    jd = julian(t)
    jd0 = math.floor(jd - 0.5) + 0.5
    err, r, v = rec.sgp4(jd0, jd - jd0)
    if err:
        raise RuntimeError("orbit calculation error %d (orbit data may be too old)" % err)
    return jd, r, v


def eci_to_ecef(r, jd):
    g = gmst(jd)
    c, s = math.cos(g), math.sin(g)
    return (c * r[0] + s * r[1], -s * r[0] + c * r[1], r[2])


def ecef_to_latlon(x, y, z):
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - E2))
    h = 0.0
    for _ in range(6):
        n = RE / math.sqrt(1 - E2 * math.sin(lat) ** 2)
        h = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1 - E2 * n / (n + h)))
    return math.degrees(lat), math.degrees(lon), h


def latlon_to_ecef(lat, lon, h_km):
    la, lo = math.radians(lat), math.radians(lon)
    n = RE / math.sqrt(1 - E2 * math.sin(la) ** 2)
    return ((n + h_km) * math.cos(la) * math.cos(lo),
            (n + h_km) * math.cos(la) * math.sin(lo),
            (n * (1 - E2) + h_km) * math.sin(la))


def look_angles(lat, lon, obs, sat):
    """Azimuth (compass direction) and elevation (height above the horizon) from the observer, in degrees."""
    dx, dy, dz = sat[0] - obs[0], sat[1] - obs[1], sat[2] - obs[2]
    la, lo = math.radians(lat), math.radians(lon)
    east = -math.sin(lo) * dx + math.cos(lo) * dy
    north = -math.sin(la) * math.cos(lo) * dx - math.sin(la) * math.sin(lo) * dy + math.cos(la) * dz
    up = math.cos(la) * math.cos(lo) * dx + math.cos(la) * math.sin(lo) * dy + math.sin(la) * dz
    rng = math.sqrt(east * east + north * north + up * up)
    return math.degrees(math.atan2(east, north)) % 360, math.degrees(math.asin(up / rng)), rng


def sun_dir(jd):
    """Unit vector toward the Sun in space (accurate to about 0.01 degrees)."""
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    return (math.cos(lam), math.cos(eps) * math.sin(lam), math.sin(eps) * math.sin(lam))


def sun_elevation(lat, lon, jd):
    s = eci_to_ecef(sun_dir(jd), jd)
    la, lo = math.radians(lat), math.radians(lon)
    up = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la))
    return math.degrees(math.asin(max(-1.0, min(1.0, sum(a * b for a, b in zip(up, s))))))


def subsolar_point(jd):
    """The place on Earth where the Sun is straight overhead (used to shade night on the map)."""
    lat, lon, _ = ecef_to_latlon(*[c * 1.496e8 for c in eci_to_ecef(sun_dir(jd), jd)])
    return lat, lon


def sunlit(r, jd):
    """True when sunlight is hitting the spacecraft (it's not in Earth's shadow)."""
    s = sun_dir(jd)
    along = sum(a * b for a, b in zip(r, s))
    if along > 0:
        return True
    perp = math.sqrt(max(0.0, sum(x * x for x in r) - along * along))
    return perp > RE


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(az):
    return COMPASS[int((az + 11.25) % 360 // 22.5)]


def magnitude(sid, sat_ecef, obs_ecef, jd, el):
    """How bright it looks (astronomers' magnitude: smaller is brighter, Venus is about -4).

    It's brightest when it's close and when the Sun is behind you, lighting up the side you see."""
    sun = eci_to_ecef(sun_dir(jd), jd)
    to_obs = [o - s for o, s in zip(obs_ecef, sat_ecef)]
    rng = math.sqrt(sum(v * v for v in to_obs))
    phase = math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(sun, to_obs)) / rng)))
    lit = math.sin(phase) + (math.pi - phase) * math.cos(phase)   # how much of the lit side faces you
    if lit <= 1e-4:
        return 9.0
    h = max(el, 0.5)                                    # the air near the horizon dims things a little
    airmass = 1 / (math.sin(math.radians(h)) + 0.50572 * (h + 6.07995) ** -1.6364)
    return SATS[sid]["std_mag"] + 5 * math.log10(rng / 1000) - 2.5 * math.log10(lit) + 0.2 * (airmass - 1)


def brightness_words(mag):
    if mag is None:
        return ""
    if mag <= -3:
        return "Super bright, like Venus"
    if mag <= -1.5:
        return "Very bright, brighter than any star"
    if mag <= 0.5:
        return "Bright, like the brightest stars"
    if mag <= 2.5:
        return "Like an ordinary star"
    return "Faint, you need a dark sky"


def orbits_per_day(sid):
    return _orbit[sid]["rec"].no_kozai * 1440 / (2 * math.pi)


_sun_cache = {}


def next_sun_change(sid, t):
    """When the crew next sees a sunrise or sunset (the moment it enters or leaves Earth's shadow)."""
    c = _sun_cache.get(sid)
    if c and c["orbit"] == _orbit[sid]["fetched"] and c["from"] <= t < c["result"]["time"]:
        return c["result"]                  # still in the future, so no need to work it out again
    result = _find_sun_change(sid, t)
    if result:
        _sun_cache[sid] = {"orbit": _orbit[sid]["fetched"], "from": t, "result": result}
    return result


def _find_sun_change(sid, t):
    def lit(tt):
        jd, r, _ = sat_eci(sid, tt)
        return sunlit(r, jd)
    now_lit = lit(t)
    a = t
    for _ in range(int(2 * 3600 / 20)):
        b = a + 20
        if lit(b) != now_lit:
            for _ in range(15):
                m = (a + b) / 2
                if lit(m) == now_lit:
                    a = m
                else:
                    b = m
            return {"type": "sunset" if now_lit else "sunrise", "time": int(b)}
        a = b
    return None


def launched_at(sid):
    if SATS[sid]["launched"]:
        return datetime.strptime(SATS[sid]["launched"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    return _orbit[sid]["launched"]


def where_now(sid, t=None):
    t = time.time() if t is None else t
    jd, r, v = sat_eci(sid, t)
    lat, lon, alt = ecef_to_latlon(*eci_to_ecef(r, jd))
    speed = math.sqrt(sum(x * x for x in v)) * 3600
    midnight = datetime.fromtimestamp(t).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    launched = launched_at(sid)
    per_day = orbits_per_day(sid)
    sun_lat, sun_lon = subsolar_point(jd)
    place, water = places.place_name(lat, lon)
    out = {"time": t, "lat": lat, "lon": lon, "alt_km": alt, "speed_kmh": speed, "sunlit": sunlit(r, jd),
           "place": place, "water": water, "km_today": speed * (t - midnight) / 3600,
           "orbits_since_launch": max(0, int((t - launched) / 86400 * per_day)) if launched else None,
           "launched": launched, "orbit_minutes": 1440 / per_day, "sunrises_per_day": per_day,
           "next_sun": next_sun_change(sid, t), "subsolar": [sun_lat, sun_lon]}
    if _orbit[sid]["train"]:                       # every satellite in the Starlink train
        train = []
        for rec in _orbit[sid]["train"]:
            try:
                j, rr, _ = sat_eci(sid, t, rec)
                la, lo, _ = ecef_to_latlon(*eci_to_ecef(rr, j))
                train.append([round(la, 3), round(lo, 3)])
            except RuntimeError:
                pass
        out["train"] = train
    return out


def ground_track(sid, t, before_min=45, after_min=95, step_s=30):
    pts = []
    for k in range(int(-before_min * 60 / step_s), int(after_min * 60 / step_s) + 1):
        tt = t + k * step_s
        jd, r, _ = sat_eci(sid, tt)
        lat, lon, _ = ecef_to_latlon(*eci_to_ecef(r, jd))
        pts.append([round(lat, 3), round(lon, 3), int(tt)])
    return pts

# ---------------------------------------------------------------- pass predictions
_passes = {}
_pass_lock = threading.Lock()


def _observer_view(sid, t, lat, lon, obs):
    jd, r, _ = sat_eci(sid, t)
    sat = eci_to_ecef(r, jd)
    az, el, rng = look_angles(lat, lon, obs, sat)
    return az, el, rng, r, jd, sat


def predict_passes(sid, lat, lon, height_m, min_el, t0=None, days=4):
    """Every time the spacecraft rises above min_el degrees over the next few days."""
    t0 = time.time() if t0 is None else t0
    obs = latlon_to_ecef(lat, lon, height_m / 1000.0)
    el = lambda t: _observer_view(sid, t, lat, lon, obs)[1]

    def crossing(a, b):                    # time between a and b where elevation crosses min_el
        ea = el(a)
        for _ in range(20):
            m = (a + b) / 2
            if (el(m) >= min_el) == (ea >= min_el):
                a = m
            else:
                b = m
        return (a + b) / 2

    out, step, t, prev = [], 20, t0, el(t0)
    start = t0 if prev >= min_el else None       # a pass that's already happening
    end_time = t0 + days * 86400
    while t < end_time:
        t2 = t + step
        e2 = el(t2)
        if start is None and prev < min_el <= e2:
            start = crossing(t, t2)
        elif start is not None and prev >= min_el > e2:
            out.append(_describe_pass(sid, start, crossing(t, t2), lat, lon, obs))
            start = None
        t, prev = t2, e2
    return out


def _describe_pass(sid, t_start, t_end, lat, lon, obs):
    view = lambda t: _observer_view(sid, t, lat, lon, obs)
    best_t, best_el, t = t_start, -90.0, t_start
    while t <= t_end:                      # find the highest point
        e = view(t)[1]
        if e > best_el:
            best_t, best_el = t, e
        t += 5
    for dt_ in range(-5, 6):
        e = view(best_t + dt_)[1]
        if e > best_el:
            best_t, best_el = best_t + dt_, e
    vis_start = vis_end = vis_top = None   # the part of the pass you can actually see
    vis_top_el, mag = -90.0, None
    t = t_start
    while t <= t_end:
        az, e, rng, r, jd, sat = view(t)
        if sunlit(r, jd) and sun_elevation(lat, lon, jd) < -6:
            vis_start = t if vis_start is None else vis_start
            vis_end = t
            if e > vis_top_el:
                vis_top, vis_top_el = t, e
            m = magnitude(sid, sat, obs, jd, e)
            mag = m if mag is None else min(mag, m)
        t += 5
    az0, azm, az1 = view(t_start)[0], view(best_t)[0], view(t_end)[0]
    p = {"sat": sid, "start": int(t_start), "max": int(best_t), "end": int(t_end),
         "max_el": round(best_el), "start_dir": compass(az0), "max_dir": compass(azm), "end_dir": compass(az1),
         "minutes": round((t_end - t_start) / 60, 1), "visible": vis_start is not None}
    if vis_start is not None:
        p.update(vis_start=int(vis_start), vis_end=int(vis_end), vis_max=int(vis_top), vis_max_el=round(vis_top_el),
                 vis_start_dir=compass(view(vis_start)[0]), vis_end_dir=compass(view(vis_end)[0]),
                 vis_max_dir=compass(view(vis_top)[0]), mag=round(mag, 1))
    return p


def rate_pass(p):
    """1 to 5 stars: brighter, higher and longer passes are better, and clouds make it worse."""
    if not p.get("visible"):
        return 0
    m, h, mins = p["mag"], p["vis_max_el"], (p["vis_end"] - p["vis_start"]) / 60
    score = 1.0
    score += 2 if m <= -3 else 1.5 if m <= -1.5 else 1 if m <= 0.5 else 0.5 if m <= 2.5 else 0
    score += 1.5 if h >= 60 else 1.1 if h >= 40 else 0.7 if h >= 25 else 0.3 if h >= 15 else 0
    score += 0.5 if mins >= 4 else 0.25 if mins >= 2 else 0
    if p.get("clouds") is not None:
        score -= 2 if p["clouds"] >= 70 else 1 if p["clouds"] >= 30 else 0
    return max(1, min(5, int(score + 0.5)))


def _all_passes(sid):
    """Passes from RECENT_H hours ago to 4 days ahead, worked out again every 10 minutes."""
    cfg = load_config()
    if cfg["lat"] is None or cfg["lon"] is None or _orbit[sid]["rec"] is None:
        return [], cfg
    key = (cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"], _orbit[sid]["fetched"], id(_orbit[sid]["rec"]))
    with _pass_lock:
        c = _passes.get(sid)
        if not c or c["key"] != key or time.time() - c["made"] > 600:
            now = time.time()
            c = {"key": key, "made": now,
                 "list": predict_passes(sid, cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"],
                                        t0=now - RECENT_H * 3600, days=4 + RECENT_H / 24)}
            _passes[sid] = c
    out = []
    for p in c["list"]:
        p = dict(p)
        p["clouds"] = cloud_cover_at(p.get("vis_start") or p["max"]) if cfg["weather_on"] else None
        p["stars"] = rate_pass(p)
        p["brightness"] = brightness_words(p.get("mag"))
        out.append(p)
    return out, cfg


def get_passes(sid):
    now = time.time()
    return [p for p in _all_passes(sid)[0] if p["end"] > now]


def recent_passes(sid):
    """Visible passes that are happening now or ended in the last few hours, for "I saw it!"."""
    now = time.time()
    return [p for p in _all_passes(sid)[0] if p["visible"] and p["vis_start"] <= now <= p["vis_end"] + RECENT_H * 3600]


def sky_path(sid, start, end):
    """The path across YOUR sky during one pass: compass direction and height every 5 seconds."""
    cfg = load_config()
    if cfg["lat"] is None:
        return []
    obs = latlon_to_ecef(cfg["lat"], cfg["lon"], cfg["height_m"] / 1000.0)
    pts, t = [], start
    while t <= end:
        az, el, _, r, jd, _ = _observer_view(sid, t, cfg["lat"], cfg["lon"], obs)
        seen = sunlit(r, jd) and sun_elevation(cfg["lat"], cfg["lon"], jd) < -6
        pts.append([round(az, 1), round(el, 1), int(t), seen])
        t += 5
    return pts

# ---------------------------------------------------------------- Moon and planets


def body_view(name, t, lat, lon, obs):
    """Compass direction, height and brightness of the Moon or a planet."""
    jd = julian(t)
    if name == "Moon":
        pos, mag = sky.moon(jd), -12.0
    else:
        pos, mag = sky.planet(name, jd)
    az, el, _ = look_angles(lat, lon, obs, [o + s for o, s in zip(obs, eci_to_ecef(pos, jd))]
                            if name != "Moon" else eci_to_ecef(pos, jd))
    return az, el, mag


def sky_bodies(t, lat, lon):
    """The Moon and bright planets above the horizon at time t (for the sky chart)."""
    obs = latlon_to_ecef(lat, lon, 0)
    out = []
    for name in ["Moon"] + sky.PLANETS:
        az, el, mag = body_view(name, t, lat, lon, obs)
        if el > 0 and mag < 1.5:
            out.append({"name": name, "az": round(az, 1), "el": round(el, 1), "mag": round(mag, 1)})
    return out


_tonight = {"key": None, "data": None}


def tonight():
    """Tonight's Moon phase, and which planets you can see and when."""
    cfg = load_config()
    if cfg["lat"] is None:
        return None
    lat, lon = cfg["lat"], cfg["lon"]
    now = time.time()
    key = (lat, lon, int(now // 600))
    if _tonight["key"] == key:
        return _tonight["data"]
    obs = latlon_to_ecef(lat, lon, 0)
    step, times = 600, [now + 600 * k for k in range(0, 24 * 6 + 1)]
    dark = [sun_elevation(lat, lon, julian(t)) < -6 for t in times]
    start = next((t for t, d in zip(times, dark) if d), None)
    end = None
    if start is not None:
        end = next((t for t, d in zip(times, dark) if t > start and not d), times[-1])
    planets, hidden = [], []
    for name in sky.PLANETS:
        seen = []
        if start is not None:
            for t in times:
                if start <= t <= end:
                    az, el, mag = body_view(name, t, lat, lon, obs)
                    if el > 5:
                        seen.append((t, az, el, mag))
        if seen:
            top = max(seen, key=lambda s: s[2])
            planets.append({"name": name, "from": int(seen[0][0]), "to": int(seen[-1][0]),
                            "dir": compass(seen[0][1]), "top_dir": compass(top[1]), "top_el": round(top[2]),
                            "mag": round(seen[0][3], 1),
                            "bright": "Super bright, the brightest planet" if name == "Venus" else brightness_words(seen[0][3]),
                            "up_now": seen[0][0] <= now + 600 and dark[0]})
        else:
            hidden.append(name)
    phase, emoji, lit, age = sky.moon_phase(julian(now))
    az, el, _ = body_view("Moon", now, lat, lon, obs)
    moon_el = lambda t: body_view("Moon", t, lat, lon, obs)[1]

    def crossing(kind):                       # next moonrise or moonset in the next 24 hours
        for a, b in zip(times, times[1:]):
            ea, eb = moon_el(a), moon_el(b)
            if (kind == "rise" and ea < 0 <= eb) or (kind == "set" and ea >= 0 > eb):
                for _ in range(12):
                    m = (a + b) / 2
                    if (moon_el(m) >= 0) == (ea >= 0):
                        a = m
                    else:
                        b = m
                return int(b)
        return None
    data = {"dark": {"start": int(start), "end": int(end)} if start is not None else None, "planets": planets,
            "hidden": hidden, "moon": {"phase": phase, "emoji": emoji, "lit": lit, "age": age, "up": el > 0,
                                       "dir": compass(az), "el": round(el), "rise": crossing("rise"), "set": crossing("set")}}
    _tonight.update(key=key, data=data)
    return data

# ---------------------------------------------------------------- cloud forecast (Open-Meteo, free, no key)
_weather = {"key": None, "hours": {}, "fetched": 0.0, "error": ""}
_weather_lock = threading.Lock()


def cloud_cover_at(t):
    """Forecast cloud cover (0-100 %) for the hour around time t, or None if unknown."""
    cfg = load_config()
    if cfg["lat"] is None:
        return None
    key = (round(cfg["lat"], 2), round(cfg["lon"], 2))   # the town's location, rounded, is all it needs
    with _weather_lock:
        if _weather["key"] != key or time.time() - _weather["fetched"] > 3600:   # at most once an hour
            _weather.update(key=key, fetched=time.time(), hours={})
            try:
                data = json.loads(http_get(WEATHER_URL.format(*key), timeout=10))
                hours = {}
                for stamp, cover in zip(data["hourly"]["time"], data["hourly"]["cloud_cover"]):
                    when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc).timestamp()
                    if cover is not None:
                        hours[int(when)] = int(round(cover))
                _weather.update(hours=hours, error="")
            except Exception as e:
                _weather["error"] = "Couldn't get the cloud forecast (%s)" % e
                log(_weather["error"])
    return _weather["hours"].get(int((t + 1800) // 3600 * 3600))     # the nearest whole hour (times are UTC)


def cloud_words(c):
    if c is None:
        return ""
    if c < 30:
        return "Clear skies (%d%% clouds)" % c
    if c < 70:
        return "Partly cloudy (%d%% clouds)" % c
    return "Cloudy (%d%% clouds), you might not see it" % c

# ---------------------------------------------------------------- phone alerts (ntfy)


def send_ntfy(cfg, title, message, tags="satellite", priority="high"):
    url = cfg["ntfy_server"].rstrip("/") + "/" + cfg["ntfy_topic"]
    req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST",
                                 headers={"Title": title, "Tags": tags, "Priority": priority, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def clock(t):
    return datetime.fromtimestamp(t).strftime("%I:%M %p").lstrip("0")


def height_words(el):
    if el >= 70:
        return "almost straight overhead"
    if el >= 40:
        return "high in the sky"
    if el >= 20:
        return "halfway up"
    return "low, near the horizon"


def stars_text(n):
    return "⭐" * n


def pass_message(p):
    if p.get("visible"):
        s, e = p["vis_start"], p["vis_end"]
        text = ("%s Look %s at %s. It climbs to %d° (%s) and disappears %s at %s. "
                "Visible for about %d min. %s: a steady dot moving fast, no blinking lights."
                % (stars_text(p["stars"]), p["vis_start_dir"], clock(s), p["vis_max_el"], height_words(p["vis_max_el"]),
                   p["vis_end_dir"], clock(e), max(1, round((e - s) / 60)), p["brightness"]))
    else:
        text = ("It rises %s at %s, reaches %d° at %s and sets %s at %s. "
                "It's not visible this time (daylight, or it's in Earth's shadow)."
                % (p["start_dir"], clock(p["start"]), p["max_el"], clock(p["max"]), p["end_dir"], clock(p["end"])))
    if p.get("clouds") is not None:
        text += " " + cloud_words(p["clouds"]) + "."
    return text


def morning_summary(cfg, now):
    lines = []
    for sid in cfg["alert_sats"]:
        for p in get_passes(sid):
            if p["visible"] and p["vis_start"] < now + 24 * 3600:
                line = "%s %s %s: look %s, up to %d°" % (clock(p["vis_start"]), SATS[sid]["name"], stars_text(p["stars"]),
                                                        p["vis_start_dir"], p["vis_max_el"])
                if p.get("clouds") is not None:
                    line += ", " + ("clear" if p["clouds"] < 30 else "partly cloudy" if p["clouds"] < 70 else "cloudy")
                lines.append((p["vis_start"], line))
    if not lines:
        return None
    lines.sort()
    n = len(lines)
    return ("%d visible pass%s in the next 24 hours" % (n, "" if n == 1 else "es"), "\n".join(l for _, l in lines))


def alert_loop():
    while True:
        try:
            cfg = load_config()
            now = time.time()
            if cfg["lat"] is not None:
                if cfg["alerts_on"]:
                    sent = _read_json(SENT_FILE, [])
                    for sid in cfg["alert_sats"]:
                        for p in get_passes(sid):
                            if cfg["visible_only"] and not p["visible"]:
                                continue
                            if p["visible"] and p["stars"] < cfg["min_stars"]:
                                continue
                            begin = p["vis_start"] if p.get("visible") else p["start"]
                            key = "%s-%d" % (sid, p["start"])
                            if 0 < begin - now <= cfg["alert_minutes"] * 60 and key not in sent:
                                mins = max(1, round((begin - now) / 60))
                                send_ntfy(cfg, "%s overhead in %d min!" % (SATS[sid]["name"], mins), pass_message(p))
                                sent = (sent + [key])[-80:]
                                _write_json(SENT_FILE, sent)
                                log("alert sent:", SATS[sid]["name"], "pass at", clock(begin))
                state = _read_json(STATE_FILE, {})
                local = datetime.fromtimestamp(now)
                today = local.strftime("%Y-%m-%d")
                # send it once a day, at the summary hour (or up to 3 hours late if the Pi was off)
                if cfg["summary_on"] and 0 <= local.hour - cfg["summary_hour"] < 3 \
                        and state.get("summary_date") != today:
                    msg = morning_summary(cfg, now)
                    if msg:
                        send_ntfy(cfg, msg[0], msg[1], tags="sunrise,satellite", priority="default")
                        log("morning summary sent")
                    state["summary_date"] = today
                    _write_json(STATE_FILE, state)
        except Exception as e:
            log("alert check failed:", e)
        time.sleep(20)


def tle_loop():
    while True:
        for sid in SATS:
            refresh_tle(sid)
        time.sleep(1800)

# ---------------------------------------------------------------- spotter log and badges


def _sightings():
    return _read_json(SIGHTINGS_FILE, [])


def _local(t):
    return datetime.fromtimestamp(t)


def _streak(s):
    days = {_local(x["vis_start"]).date() for x in s}
    return any(d + timedelta(days=1) in days and d + timedelta(days=2) in days for d in days)


_saw = lambda sid: (lambda s: any(x["sat"] == sid for x in s))
BADGES = [   # (id, emoji, name, how to earn it, check, goal for a progress count)
    ("first", "👀", "First Sighting", "See your first pass", lambda s: len(s) >= 1, 1),
    ("five", "🖐️", "High Five", "See 5 passes", lambda s: len(s) >= 5, 5),
    ("ten", "🔟", "Perfect Ten", "See 10 passes", lambda s: len(s) >= 10, 10),
    ("legend", "🏆", "Spotter Legend", "See 25 passes", lambda s: len(s) >= 25, 25),
    ("iss", "🛰️", "ISS Spotter", "See the ISS", _saw("iss"), None),
    ("tiangong", "🚀", "Tiangong Spotter", "See Tiangong", _saw("tiangong"), None),
    ("hubble", "🔭", "Hubble Hunter", "See Hubble", _saw("hubble"), None),
    ("starlink", "✨", "Train Spotter", "See a Starlink train", _saw("starlink"), None),
    ("all", "🌌", "Full Set", "See all four: ISS, Tiangong, Hubble and Starlink", lambda s: all(_saw(k)(s) for k in SATS), None),
    ("high", "⬆️", "Straight Up", "See a pass 70° or higher", lambda s: any(x["max_el"] >= 70 for x in s), None),
    ("bright", "🌟", "Super Bright", "See a pass as bright as Venus", lambda s: any((x.get("mag") or 9) <= -3 for x in s), None),
    ("early", "🌅", "Early Bird", "See a pass before 6 AM", lambda s: any(_local(x["vis_start"]).hour < 6 for x in s), None),
    ("owl", "🦉", "Night Owl", "See a pass after 10 PM", lambda s: any(_local(x["vis_start"]).hour >= 22 for x in s), None),
    ("cloud", "☁️", "Cloud Buster", "See a pass when the forecast said cloudy", lambda s: any((x.get("clouds") or 0) >= 70 for x in s), None),
    ("streak", "🔥", "Hat Trick", "See passes 3 days in a row", _streak, None),
]


def spotter_log():
    s = _sightings()
    badges = [{"id": b[0], "emoji": b[1], "name": b[2], "how": b[3], "earned": bool(b[4](s)),
               "progress": "%d/%d" % (min(len(s), b[5]), b[5]) if b[5] else None} for b in BADGES]
    return {"count": len(s), "sightings": sorted(s, key=lambda x: -x["vis_start"]), "badges": badges}


def log_sighting(sid, start):
    p = next((p for p in recent_passes(sid) if p["start"] == start), None)
    if p is None and any(q["start"] == start and q["visible"] for q in get_passes(sid)):
        raise ValueError("You can log it once it has started. Good luck!")
    if p is None:
        raise ValueError("That pass isn't in the list any more (you can log a pass for %d hours after it)." % RECENT_H)
    with _file_lock:
        s = _sightings()
        if not any(x["sat"] == sid and x["start"] == start for x in s):
            s.append({"sat": sid, "start": p["start"], "vis_start": p["vis_start"], "max_el": p["vis_max_el"],
                      "dir": p["vis_start_dir"], "mag": p["mag"], "clouds": p["clouds"], "stars": p["stars"],
                      "logged": int(time.time())})
            _write_json(SIGHTINGS_FILE, s[-2000:])
    return spotter_log()


def remove_sighting(sid, start):
    with _file_lock:
        _write_json(SIGHTINGS_FILE, [x for x in _sightings() if not (x["sat"] == sid and x["start"] == start)])
    return spotter_log()

# ---------------------------------------------------------------- calendar file (.ics)


def _ics_text(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _ics_fold(line):
    """Calendar files want lines of at most 75 bytes; longer ones continue on the next line after a space."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode("utf-8")) > 74:
            out.append(cur)
            cur = " "
        cur += ch
    return "\r\n".join(out + [cur])


def calendar_ics(sid):
    cfg = load_config()
    stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pi Space Station Tracker//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:%s passes" % SATS[sid]["name"]]
    for p in get_passes(sid):
        if not p["visible"]:
            continue
        lines += ["BEGIN:VEVENT", "UID:%s-%d@pi-space-station-tracker" % (sid, p["start"]), "DTSTAMP:" + stamp(time.time()),
                  "DTSTART:" + stamp(p["vis_start"]), "DTEND:" + stamp(p["vis_end"] + 60),
                  "SUMMARY:" + _ics_text("%s %s pass %s, look %s" % ("🔭" if sid == "hubble" else "🛰️", SATS[sid]["name"],
                                                                     stars_text(p["stars"]), p["vis_start_dir"])),
                  "DESCRIPTION:" + _ics_text(pass_message(p) + "\nFrom your Pi Space Station Tracker."),
                  "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + _ics_text("%s pass soon, look %s" % (SATS[sid]["name"], p["vis_start_dir"])),
                  "TRIGGER:-PT%dM" % cfg["alert_minutes"], "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_ics_fold(l) for l in lines) + "\r\n"

# ---------------------------------------------------------------- people in space (just for fun)
_crew = {"by_craft": {}, "fetched": 0.0}


def get_crew(sid):
    craft = SATS[sid]["crew"]
    if craft is None:
        return None
    if time.time() - _crew["fetched"] > 6 * 3600:
        _crew["fetched"] = time.time()
        try:
            by_craft = {}
            for p in json.loads(http_get(CREW_URL, timeout=10)).get("people", []):
                by_craft.setdefault(p.get("craft"), []).append(p.get("name"))
            _crew["by_craft"] = by_craft
        except Exception as e:
            log("couldn't get the crew list:", e)
    return _crew["by_craft"].get(craft, [])

# ---------------------------------------------------------------- web server


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path):
        root = os.path.realpath(os.path.join(HERE, "static"))
        full = os.path.realpath(os.path.join(root, path[len("/static/"):]))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        types = {".js": "text/javascript", ".css": "text/css", ".png": "image/png", ".json": "application/json",
                 ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml"}
        with open(full, "rb") as f:
            return self._send(200, f.read(), types.get(os.path.splitext(full)[1], "application/octet-stream"))

    def do_GET(self):
        url = urlparse(self.path)
        path, q = url.path, parse_qs(url.query)
        sid = q.get("sat", ["iss"])[0]
        if sid not in SATS:
            sid = "iss"
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._static(path)
            if path == "/manifest.webmanifest":
                return self._static("/static/manifest.webmanifest")
            if path == "/api/sats":
                return self._send(200, {k: {"name": v["name"], "full": v["full"], "launched": launched_at(k),
                                            "has_crew": v["crew"] is not None, "has_data": _orbit[k]["rec"] is not None,
                                            "error": _orbit[k]["error"]}
                                        for k, v in SATS.items()})
            if path == "/api/now":
                cfg = load_config()
                o = _orbit[sid]
                body = {"sat": sid, "now": where_now(sid), "tle_error": o["error"],
                        "tle_age_h": round((time.time() - o["fetched"]) / 3600, 1) if o["fetched"] else None,
                        "home": {"lat": cfg["lat"], "lon": cfg["lon"], "place": cfg["place"]}}
                if cfg["lat"] is not None:
                    obs = latlon_to_ecef(cfg["lat"], cfg["lon"], cfg["height_m"] / 1000.0)
                    az, el, rng = _observer_view(sid, time.time(), cfg["lat"], cfg["lon"], obs)[:3]
                    body["from_home"] = {"az": round(az), "dir": compass(az), "el": round(el, 1), "km": round(rng)}
                return self._send(200, body)
            if path == "/api/track":
                return self._send(200, {"points": ground_track(sid, time.time())})
            if path == "/api/passes":
                return self._send(200, {"passes": get_passes(sid), "recent": recent_passes(sid), "now": time.time(),
                                        "weather_error": _weather["error"]})
            if path == "/api/skypath":
                start, end = int(q.get("start", ["0"])[0]), int(q.get("end", ["0"])[0])
                if not 0 < end - start <= 1800:
                    return self._send(400, {"error": "bad pass times"})
                cfg = load_config()
                mid = int(q.get("at", [str((start + end) // 2)])[0])
                bodies = sky_bodies(mid, cfg["lat"], cfg["lon"]) if cfg["lat"] is not None else []
                return self._send(200, {"points": sky_path(sid, start, end), "bodies": bodies})
            if path == "/api/tonight":
                return self._send(200, {"tonight": tonight()})
            if path == "/api/sightings":
                return self._send(200, spotter_log())
            if path == "/api/history":
                return self._send(200, get_history(sid))
            if path == "/api/calendar.ics":
                return self._send(200, calendar_ics(sid).encode("utf-8"), "text/calendar; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="%s-passes.ics"' % sid})
            if path == "/api/crew":
                return self._send(200, {"crew": get_crew(sid)})
            if path == "/api/settings":
                return self._send(200, load_config())
            return self._send(404, {"error": "not found"})
        except Exception as e:
            log("error on", path, e)
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            cfg = load_config()
            if path == "/api/settings":
                if body.get("lat") in (None, "") or body.get("lon") in (None, ""):
                    cfg["lat"] = cfg["lon"] = None
                else:
                    lat, lon = float(body["lat"]), float(body["lon"])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        return self._send(400, {"error": "Latitude must be -90 to 90 and longitude -180 to 180."})
                    cfg["lat"], cfg["lon"] = round(lat, 3), round(lon, 3)
                cfg["place"] = str(body.get("place", cfg["place"]))[:60]
                cfg["min_elevation"] = max(0, min(60, int(body.get("min_elevation", cfg["min_elevation"]))))
                cfg["alert_minutes"] = max(1, min(60, int(body.get("alert_minutes", cfg["alert_minutes"]))))
                cfg["summary_hour"] = max(0, min(23, int(body.get("summary_hour", cfg["summary_hour"]))))
                cfg["min_stars"] = max(1, min(5, int(body.get("min_stars", cfg["min_stars"]))))
                for k in ("alerts_on", "visible_only", "summary_on", "weather_on"):
                    cfg[k] = bool(body.get(k, cfg[k]))
                if isinstance(body.get("alert_sats"), list):
                    cfg["alert_sats"] = [s for s in body["alert_sats"] if s in SATS]
                video = str(body.get("video_url", cfg["video_url"])).strip()[:300]
                cfg["video_url"] = video if (video == "" or video.startswith("https://")) else cfg["video_url"]
                save_config(cfg)
                return self._send(200, cfg)
            if path in ("/api/sightings", "/api/sightings/remove"):
                sid, start = body.get("sat"), int(body.get("start") or 0)
                if sid not in SATS:
                    return self._send(400, {"error": "unknown spacecraft"})
                try:
                    return self._send(200, log_sighting(sid, start) if path == "/api/sightings" else remove_sighting(sid, start))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
            if path == "/api/test-alert":
                send_ntfy(cfg, "Test from your Pi", "Your Pi Space Station Tracker can reach your phone! 🛰️", tags="tada")
                return self._send(200, {"ok": True})
            if path == "/api/test-summary":
                msg = morning_summary(cfg, time.time()) or ("No visible passes in the next 24 hours",
                                                            "The morning summary will list them when there are some.")
                send_ntfy(cfg, msg[0], msg[1], tags="sunrise,satellite", priority="default")
                return self._send(200, {"ok": True})
            if path == "/api/new-topic":
                cfg["ntfy_topic"] = "iss-" + secrets.token_hex(8)
                save_config(cfg)
                return self._send(200, cfg)
            if path == "/api/refresh-orbit":
                for sid in SATS:
                    refresh_tle(sid, force=True)
                errors = [_orbit[s]["error"] for s in SATS if _orbit[s]["error"]]
                return self._send(200, {"ok": not errors, "errors": errors})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            log("error on", path, e)
            return self._send(500, {"error": str(e)})


def main():
    load_config()
    for sid in SATS:
        load_saved_tle(sid)
    threading.Thread(target=tle_loop, daemon=True).start()
    threading.Thread(target=alert_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log("Pi Space Station Tracker running on port", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()

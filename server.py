"""Pi Space Station Tracker - track the International Space Station live on a Raspberry Pi.

Shows where the ISS (and China's Tiangong station and the Hubble telescope) is right now
on a world map, predicts when it will pass over your town, checks the clouds, and sends
an alert to your phone a few minutes before it flies over, plus a summary each morning.

Run in the background:  bash setup-autostart.sh   (see README.md)
Run by hand:            source venv/bin/activate && python server.py
Then open http://<your-pi>.local:8080  (or http://<your-pi-ip>:8080)
Needs: pip install sgp4
Works with Python 3.9 and newer (Raspberry Pi OS Bullseye or Bookworm).
"""
import json, math, os, secrets, threading, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from sgp4.api import Satrec

PORT = int(os.environ.get("ISS_PORT", "8080"))       # the stock tracker uses 8000, so both can run together
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CONFIG_FILE = os.path.join(HERE, "config.json")      # your settings (location, alerts). Never uploaded to GitHub.
SENT_FILE = os.path.join(DATA, "alerts_sent.json")   # which passes already got an alert
STATE_FILE = os.path.join(DATA, "state.json")        # small things to remember, like the last morning summary

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={}&FORMAT=TLE"
CREW_URL = "http://api.open-notify.org/astros.json"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast?latitude={:.2f}&longitude={:.2f}&hourly=cloud_cover&forecast_days=5"
UA = "pi-space-station-tracker/1.1 (+https://github.com/akshajtripathi24-ui/pi-space-station-tracker)"
TLE_MAX_AGE_H = 12          # download fresh orbit data twice a day (CelesTrak asks people not to download too often)

# The spacecraft you can track. "catnr" is the satellite's catalog number used by CelesTrak.
SATS = {
    "iss": {"name": "ISS", "full": "International Space Station", "catnr": 25544, "crew": "ISS",
            "launched": "1998-11-20"},
    "tiangong": {"name": "Tiangong", "full": "Tiangong (China's space station)", "catnr": 48274, "crew": "Tiangong",
                 "launched": "2021-04-29"},
    "hubble": {"name": "Hubble", "full": "Hubble Space Telescope", "catnr": 20580, "crew": None,
               "launched": "1990-04-24"},
}

# ---------------------------------------------------------------- settings
DEFAULTS = {
    "lat": None, "lon": None, "place": "", "height_m": 0,
    "min_elevation": 10,     # degrees above the horizon that counts as a pass (trees and houses block lower ones)
    "alert_minutes": 10,     # how many minutes before a pass the phone alert arrives
    "alerts_on": True,
    "visible_only": True,    # only alert for passes you can actually SEE (dark sky, lit by the Sun)
    "alert_sats": ["iss"],   # which spacecraft send alerts
    "summary_on": True,      # one message each morning listing the day's visible passes
    "summary_hour": 8,       # what time the morning summary arrives (0-23, Pi's local time)
    "weather_on": True,      # check the cloud forecast for each pass (uses the free Open-Meteo service)
    "video_url": "",         # optional: your own link for the "Live view from space" video
    "ntfy_server": "https://ntfy.sh",
    "ntfy_topic": "",
}
_cfg_lock = threading.Lock()


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
        json.dump(obj, f, indent=2)
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
_orbit = {sid: {"rec": None, "fetched": 0.0, "error": ""} for sid in SATS}


def tle_file(sid):
    return os.path.join(DATA, "tle_%s.txt" % sid)


def _use_tle(sid, text, fetched_at):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    l1 = next((l for l in lines if l.startswith("1 ")), None)
    l2 = next((l for l in lines if l.startswith("2 ")), None)
    if not l1 or not l2:
        raise ValueError("no TLE lines found")
    _orbit[sid].update(rec=Satrec.twoline2rv(l1, l2), fetched=fetched_at, error="")


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
    try:
        text = http_get(TLE_URL.format(SATS[sid]["catnr"]))
        _use_tle(sid, text, time.time())
        with open(tle_file(sid), "w") as f:
            f.write(text.strip() + "\n")
        log("downloaded fresh orbit data for", SATS[sid]["name"])
        _passes.pop(sid, None)        # recalculate passes with the new data
    except Exception as e:            # keep using the saved copy
        o["error"] = "Couldn't download fresh orbit data (%s). Using the saved copy." % e
        log(SATS[sid]["name"], o["error"])

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


def sat_eci(sid, t):
    """Position (km) and velocity (km/s) in space at unix time t."""
    rec = _orbit[sid]["rec"]
    if rec is None:
        raise RuntimeError("no orbit data yet for " + SATS[sid]["name"])
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


def where_now(sid, t=None):
    t = time.time() if t is None else t
    jd, r, v = sat_eci(sid, t)
    lat, lon, alt = ecef_to_latlon(*eci_to_ecef(r, jd))
    speed = math.sqrt(sum(x * x for x in v)) * 3600
    midnight = datetime.fromtimestamp(t).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    launched = datetime.strptime(SATS[sid]["launched"], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    per_day = orbits_per_day(sid)
    sun_lat, sun_lon = subsolar_point(jd)
    return {"time": t, "lat": lat, "lon": lon, "alt_km": alt, "speed_kmh": speed, "sunlit": sunlit(r, jd),
            "km_today": speed * (t - midnight) / 3600,
            "orbits_since_launch": max(0, int((t - launched) / 86400 * per_day)),
            "orbit_minutes": 1440 / per_day, "sunrises_per_day": per_day,
            "next_sun": next_sun_change(sid, t), "subsolar": [sun_lat, sun_lon]}


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
    az, el, rng = look_angles(lat, lon, obs, eci_to_ecef(r, jd))
    return az, el, rng, r, jd


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
    vis_start = vis_end = None             # the part of the pass you can actually see
    t = t_start
    while t <= t_end:
        az, e, rng, r, jd = view(t)
        if sunlit(r, jd) and sun_elevation(lat, lon, jd) < -6:
            vis_start = t if vis_start is None else vis_start
            vis_end = t
        t += 5
    az0, azm, az1 = view(t_start)[0], view(best_t)[0], view(t_end)[0]
    p = {"sat": sid, "start": int(t_start), "max": int(best_t), "end": int(t_end),
         "max_el": round(best_el), "start_dir": compass(az0), "max_dir": compass(azm), "end_dir": compass(az1),
         "minutes": round((t_end - t_start) / 60, 1), "visible": vis_start is not None}
    if vis_start is not None:
        p.update(vis_start=int(vis_start), vis_end=int(vis_end),
                 vis_start_dir=compass(view(vis_start)[0]), vis_end_dir=compass(view(vis_end)[0]))
    return p


def get_passes(sid):
    cfg = load_config()
    if cfg["lat"] is None or cfg["lon"] is None or _orbit[sid]["rec"] is None:
        return []
    key = (cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"], _orbit[sid]["fetched"])
    with _pass_lock:
        c = _passes.get(sid)
        if not c or c["key"] != key or time.time() - c["made"] > 600:
            c = {"key": key, "made": time.time(),
                 "list": predict_passes(sid, cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"])}
            _passes[sid] = c
    now = time.time()
    out = []
    for p in c["list"]:
        if p["end"] > now:
            p = dict(p)
            p["clouds"] = cloud_cover_at(p.get("vis_start") or p["max"]) if cfg["weather_on"] else None
            out.append(p)
    return out


def sky_path(sid, start, end):
    """The path across YOUR sky during one pass: compass direction and height every 5 seconds."""
    cfg = load_config()
    if cfg["lat"] is None:
        return []
    obs = latlon_to_ecef(cfg["lat"], cfg["lon"], cfg["height_m"] / 1000.0)
    pts, t = [], start
    while t <= end:
        az, el, _, r, jd = _observer_view(sid, t, cfg["lat"], cfg["lon"], obs)
        seen = sunlit(r, jd) and sun_elevation(cfg["lat"], cfg["lon"], jd) < -6
        pts.append([round(az, 1), round(el, 1), int(t), seen])
        t += 5
    return pts

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


def pass_message(p):
    if p.get("visible"):
        s, e = p["vis_start"], p["vis_end"]
        text = ("Look %s at %s. It climbs to %d° (%s) and disappears %s at %s. "
                "Visible for about %d min: a bright, steady dot moving fast, no blinking lights."
                % (p["vis_start_dir"], clock(s), p["max_el"], height_words(p["max_el"]), p["vis_end_dir"],
                   clock(e), max(1, round((e - s) / 60))))
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
                line = "%s %s: look %s, up to %d°" % (clock(p["vis_start"]), SATS[sid]["name"], p["vis_start_dir"], p["max_el"])
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

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path):
        root = os.path.realpath(os.path.join(HERE, "static"))
        full = os.path.realpath(os.path.join(root, path[len("/static/"):]))
        if not full.startswith(root + os.sep) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        types = {".js": "text/javascript", ".css": "text/css", ".png": "image/png"}
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
            if path == "/api/sats":
                return self._send(200, {k: {"name": v["name"], "full": v["full"], "launched": v["launched"],
                                            "has_crew": v["crew"] is not None, "has_data": _orbit[k]["rec"] is not None}
                                        for k, v in SATS.items()})
            if path == "/api/now":
                cfg = load_config()
                o = _orbit[sid]
                body = {"sat": sid, "now": where_now(sid), "tle_error": o["error"],
                        "tle_age_h": round((time.time() - o["fetched"]) / 3600, 1) if o["fetched"] else None,
                        "home": {"lat": cfg["lat"], "lon": cfg["lon"], "place": cfg["place"]}}
                if cfg["lat"] is not None:
                    obs = latlon_to_ecef(cfg["lat"], cfg["lon"], cfg["height_m"] / 1000.0)
                    az, el, rng, _, _ = _observer_view(sid, time.time(), cfg["lat"], cfg["lon"], obs)
                    body["from_home"] = {"az": round(az), "dir": compass(az), "el": round(el, 1), "km": round(rng)}
                return self._send(200, body)
            if path == "/api/track":
                return self._send(200, {"points": ground_track(sid, time.time())})
            if path == "/api/passes":
                return self._send(200, {"passes": get_passes(sid), "now": time.time(),
                                        "weather_error": _weather["error"]})
            if path == "/api/skypath":
                start, end = int(q.get("start", ["0"])[0]), int(q.get("end", ["0"])[0])
                if not 0 < end - start <= 1800:
                    return self._send(400, {"error": "bad pass times"})
                return self._send(200, {"points": sky_path(sid, start, end)})
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
                for k in ("alerts_on", "visible_only", "summary_on", "weather_on"):
                    cfg[k] = bool(body.get(k, cfg[k]))
                if isinstance(body.get("alert_sats"), list):
                    cfg["alert_sats"] = [s for s in body["alert_sats"] if s in SATS]
                video = str(body.get("video_url", cfg["video_url"])).strip()[:300]
                cfg["video_url"] = video if (video == "" or video.startswith("https://")) else cfg["video_url"]
                save_config(cfg)
                return self._send(200, cfg)
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

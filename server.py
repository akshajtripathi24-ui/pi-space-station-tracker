"""Pi Space Station Tracker - track the International Space Station live on a Raspberry Pi.

Shows where the ISS is right now on a world map, predicts when it will pass over
your town, and sends an alert to your phone a few minutes before it flies over.

Run in the background:  bash setup-autostart.sh   (see README.md)
Run by hand:            source venv/bin/activate && python server.py
Then open http://<your-pi>.local:8080  (or http://<your-pi-ip>:8080)
Needs: pip install sgp4
Works with Python 3.9 and newer (Raspberry Pi OS Bullseye or Bookworm).
"""
import json, math, os, secrets, threading, time, urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from sgp4.api import Satrec

PORT = int(os.environ.get("ISS_PORT", "8080"))       # the stock tracker uses 8000, so both can run together
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CONFIG_FILE = os.path.join(HERE, "config.json")      # your settings (location, alerts). Never uploaded to GitHub.
TLE_FILE = os.path.join(DATA, "iss_tle.txt")         # the latest orbit data, saved so it works after a restart
SENT_FILE = os.path.join(DATA, "alerts_sent.json")   # which passes already got an alert

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"
CREW_URL = "http://api.open-notify.org/astros.json"
UA = "pi-space-station-tracker/1.0 (+https://github.com/akshajtripathi24-ui/pi-space-station-tracker)"
TLE_MAX_AGE_H = 12          # download fresh orbit data twice a day (CelesTrak asks people not to download too often)

# ---------------------------------------------------------------- settings
DEFAULTS = {
    "lat": None, "lon": None, "place": "", "height_m": 0,
    "min_elevation": 10,     # degrees above the horizon that counts as a pass (trees and houses block lower ones)
    "alert_minutes": 10,     # how many minutes before a pass the phone alert arrives
    "alerts_on": True,
    "visible_only": True,    # only alert for passes you can actually SEE (dark sky, ISS lit by the Sun)
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


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

# ---------------------------------------------------------------- orbit data (TLE)
_sat = {"rec": None, "lines": None, "fetched": 0.0, "error": ""}
_sat_lock = threading.Lock()


def _use_tle(text, fetched_at):
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    l1 = next((l for l in lines if l.startswith("1 ")), None)
    l2 = next((l for l in lines if l.startswith("2 ")), None)
    if not l1 or not l2:
        raise ValueError("no TLE lines found")
    rec = Satrec.twoline2rv(l1, l2)
    with _sat_lock:
        _sat.update(rec=rec, lines=(l1, l2), fetched=fetched_at, error="")


def refresh_tle(force=False):
    """Load the saved orbit data, and download fresh data when it's older than TLE_MAX_AGE_H."""
    os.makedirs(DATA, exist_ok=True)
    if _sat["rec"] is None and os.path.exists(TLE_FILE):
        try:
            with open(TLE_FILE) as f:
                _use_tle(f.read(), os.path.getmtime(TLE_FILE))
        except (OSError, ValueError) as e:
            log("saved orbit data unreadable:", e)
    age_h = (time.time() - _sat["fetched"]) / 3600 if _sat["fetched"] else 1e9
    if not force and age_h < TLE_MAX_AGE_H:
        return
    try:
        text = http_get(TLE_URL)
        _use_tle(text, time.time())
        with open(TLE_FILE, "w") as f:
            f.write(text.strip() + "\n")
        log("downloaded fresh ISS orbit data")
        _passes["key"] = None          # recalculate passes with the new data
    except Exception as e:             # keep using the saved copy
        _sat["error"] = "Couldn't download fresh orbit data (%s). Using the saved copy." % e
        log(_sat["error"])

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


def sat_eci(t):
    """ISS position (km) and velocity (km/s) in space at unix time t."""
    rec = _sat["rec"]
    if rec is None:
        raise RuntimeError("no orbit data yet")
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


def iss_sunlit(r, jd):
    """True when sunlight is hitting the ISS (it's not in Earth's shadow)."""
    s = sun_dir(jd)
    along = sum(a * b for a, b in zip(r, s))
    if along > 0:
        return True
    perp = math.sqrt(max(0.0, sum(x * x for x in r) - along * along))
    return perp > RE


COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def compass(az):
    return COMPASS[int((az + 11.25) % 360 // 22.5)]


def where_now(t=None):
    t = time.time() if t is None else t
    jd, r, v = sat_eci(t)
    lat, lon, alt = ecef_to_latlon(*eci_to_ecef(r, jd))
    speed = math.sqrt(sum(x * x for x in v)) * 3600
    return {"time": t, "lat": lat, "lon": lon, "alt_km": alt, "speed_kmh": speed, "sunlit": iss_sunlit(r, jd)}


def ground_track(t, before_min=45, after_min=95, step_s=30):
    pts = []
    for k in range(int(-before_min * 60 / step_s), int(after_min * 60 / step_s) + 1):
        tt = t + k * step_s
        jd, r, _ = sat_eci(tt)
        lat, lon, _ = ecef_to_latlon(*eci_to_ecef(r, jd))
        pts.append([round(lat, 3), round(lon, 3), int(tt)])
    return pts

# ---------------------------------------------------------------- pass predictions
_passes = {"key": None, "list": [], "made": 0.0}
_pass_lock = threading.Lock()


def _observer_view(t, lat, lon, obs):
    jd, r, _ = sat_eci(t)
    az, el, rng = look_angles(lat, lon, obs, eci_to_ecef(r, jd))
    return az, el, rng, r, jd


def predict_passes(lat, lon, height_m, min_el, t0=None, days=4):
    """Every time the ISS rises above min_el degrees over the next few days."""
    t0 = time.time() if t0 is None else t0
    obs = latlon_to_ecef(lat, lon, height_m / 1000.0)
    el = lambda t: _observer_view(t, lat, lon, obs)[1]

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
            out.append(_describe_pass(start, crossing(t, t2), lat, lon, obs))
            start = None
        t, prev = t2, e2
    return out


def _describe_pass(t_start, t_end, lat, lon, obs):
    best_t, best_el, t = t_start, -90.0, t_start
    while t <= t_end:                      # find the highest point, 1 second at a time near the top
        e = _observer_view(t, lat, lon, obs)[1]
        if e > best_el:
            best_t, best_el = t, e
        t += 5
    for dt_ in range(-5, 6):
        e = _observer_view(best_t + dt_, lat, lon, obs)[1]
        if e > best_el:
            best_t, best_el = best_t + dt_, e
    vis_start = vis_end = None             # the part of the pass you can actually see
    t = t_start
    while t <= t_end:
        az, e, rng, r, jd = _observer_view(t, lat, lon, obs)
        if iss_sunlit(r, jd) and sun_elevation(lat, lon, jd) < -6:
            vis_start = t if vis_start is None else vis_start
            vis_end = t
        t += 5
    az0 = _observer_view(t_start, lat, lon, obs)[0]
    azm = _observer_view(best_t, lat, lon, obs)[0]
    az1 = _observer_view(t_end, lat, lon, obs)[0]
    p = {"start": int(t_start), "max": int(best_t), "end": int(t_end),
         "max_el": round(best_el), "start_dir": compass(az0), "max_dir": compass(azm), "end_dir": compass(az1),
         "start_az": round(az0), "end_az": round(az1),
         "minutes": round((t_end - t_start) / 60, 1),
         "visible": vis_start is not None}
    if vis_start is not None:
        vaz0 = _observer_view(vis_start, lat, lon, obs)[0]
        vaz1 = _observer_view(vis_end, lat, lon, obs)[0]
        p.update(vis_start=int(vis_start), vis_end=int(vis_end), vis_start_dir=compass(vaz0), vis_end_dir=compass(vaz1))
    return p


def get_passes():
    cfg = load_config()
    if cfg["lat"] is None or cfg["lon"] is None or _sat["rec"] is None:
        return []
    key = (cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"], _sat["fetched"])
    with _pass_lock:
        stale = time.time() - _passes["made"] > 600
        if _passes["key"] != key or stale:
            _passes["list"] = predict_passes(cfg["lat"], cfg["lon"], cfg["height_m"], cfg["min_elevation"])
            _passes.update(key=key, made=time.time())
        now = time.time()
        return [p for p in _passes["list"] if p["end"] > now]

# ---------------------------------------------------------------- phone alerts (ntfy)


def send_ntfy(cfg, title, message, tags="satellite", priority="high"):
    url = cfg["ntfy_server"].rstrip("/") + "/" + cfg["ntfy_topic"]
    req = urllib.request.Request(url, data=message.encode("utf-8"), method="POST",
                                 headers={"Title": title, "Tags": tags, "Priority": priority, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def clock(t):
    return datetime.fromtimestamp(t).strftime("%I:%M %p").lstrip("0")


def pass_message(p):
    if p.get("visible"):
        s, e = p["vis_start"], p["vis_end"]
        mins = max(1, round((e - s) / 60))
        return ("Look %s at %s. It climbs to %d° (%s) and disappears %s at %s. "
                "Visible for about %d min: a bright, steady dot moving fast, no blinking lights."
                % (p["vis_start_dir"], clock(s), p["max_el"], height_words(p["max_el"]), p["vis_end_dir"], clock(e), mins))
    return ("It rises %s at %s, reaches %d° at %s and sets %s at %s. "
            "It's not visible this time (daylight, or the ISS is in Earth's shadow)."
            % (p["start_dir"], clock(p["start"]), p["max_el"], clock(p["max"]), p["end_dir"], clock(p["end"])))


def height_words(el):
    if el >= 70:
        return "almost straight overhead"
    if el >= 40:
        return "high in the sky"
    if el >= 20:
        return "halfway up"
    return "low, near the horizon"


def alert_loop():
    while True:
        try:
            cfg = load_config()
            if cfg["alerts_on"] and cfg["lat"] is not None:
                try:
                    with open(SENT_FILE) as f:
                        sent = json.load(f)
                except (OSError, ValueError):
                    sent = []
                now = time.time()
                for p in get_passes():
                    if cfg["visible_only"] and not p["visible"]:
                        continue
                    begin = p["vis_start"] if p.get("visible") else p["start"]
                    if 0 < begin - now <= cfg["alert_minutes"] * 60 and str(p["start"]) not in sent:
                        mins = max(1, round((begin - now) / 60))
                        send_ntfy(cfg, "ISS overhead in %d min!" % mins, pass_message(p))
                        sent = (sent + [str(p["start"])])[-50:]
                        _write_json(SENT_FILE, sent)
                        log("alert sent for the pass at", clock(begin))
        except Exception as e:
            log("alert check failed:", e)
        time.sleep(20)


def tle_loop():
    while True:
        refresh_tle()
        time.sleep(1800)

# ---------------------------------------------------------------- people in space (just for fun)
_crew = {"names": [], "fetched": 0.0}


def get_crew():
    if time.time() - _crew["fetched"] > 6 * 3600:
        _crew["fetched"] = time.time()
        try:
            data = json.loads(http_get(CREW_URL, timeout=10))
            _crew["names"] = [p["name"] for p in data.get("people", []) if p.get("craft") == "ISS"]
        except Exception as e:
            log("couldn't get the crew list:", e)
    return _crew["names"]

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
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path.startswith("/static/"):
                return self._static(path)
            if path == "/api/now":
                cfg = load_config()
                body = {"iss": where_now(), "tle_error": _sat["error"],
                        "tle_age_h": round((time.time() - _sat["fetched"]) / 3600, 1) if _sat["fetched"] else None,
                        "home": {"lat": cfg["lat"], "lon": cfg["lon"], "place": cfg["place"]}}
                if cfg["lat"] is not None:
                    obs = latlon_to_ecef(cfg["lat"], cfg["lon"], cfg["height_m"] / 1000.0)
                    az, el, rng, _, jd = _observer_view(time.time(), cfg["lat"], cfg["lon"], obs)
                    body["from_home"] = {"az": round(az), "dir": compass(az), "el": round(el, 1), "km": round(rng)}
                return self._send(200, body)
            if path == "/api/track":
                return self._send(200, {"points": ground_track(time.time())})
            if path == "/api/passes":
                return self._send(200, {"passes": get_passes(), "now": time.time()})
            if path == "/api/crew":
                return self._send(200, {"iss_crew": get_crew()})
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
                cfg["alerts_on"] = bool(body.get("alerts_on", cfg["alerts_on"]))
                cfg["visible_only"] = bool(body.get("visible_only", cfg["visible_only"]))
                save_config(cfg)
                return self._send(200, cfg)
            if path == "/api/test-alert":
                send_ntfy(cfg, "Test from your Pi", "Your Pi Space Station Tracker can reach your phone! 🛰️", tags="tada")
                return self._send(200, {"ok": True})
            if path == "/api/new-topic":
                cfg["ntfy_topic"] = "iss-" + secrets.token_hex(8)
                save_config(cfg)
                return self._send(200, cfg)
            if path == "/api/refresh-orbit":
                refresh_tle(force=True)
                return self._send(200, {"ok": not _sat["error"], "error": _sat["error"]})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            log("error on", path, e)
            return self._send(500, {"error": str(e)})


def main():
    load_config()
    refresh_tle()
    threading.Thread(target=tle_loop, daemon=True).start()
    threading.Thread(target=alert_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log("Pi Space Station Tracker running on port", PORT)
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Where the Moon and the bright planets are, using simple formulas that need no internet.

The planets use NASA JPL's "approximate positions of the planets" (Keplerian elements, good from 1800 to 2050).
The Moon uses the low-precision formula from the Astronomical Almanac. Both are accurate to well under
a degree, which is plenty for "Jupiter is low in the SW".
Positions come back in the same space coordinates the orbit math in server.py uses (Earth-centered, km).
"""
import math

AU = 149597870.7          # km
RE = 6378.137             # Earth's radius, km
OBLIQUITY = math.radians(23.43928)

# a (AU), e, I, L, long. of perihelion, long. of ascending node (degrees), and how much each changes per century
ELEMENTS = {
    "Mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "Venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "Earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "Mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "Saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
}
PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn"]


def _helio(name, T):
    """Position around the Sun in AU (ecliptic coordinates)."""
    el = [a + b * T for a, b in zip(*ELEMENTS[name])]
    a, e, inc, L, peri, node = el[0], el[1], math.radians(el[2]), el[3], el[4], el[5]
    w = math.radians(peri - node)
    M = math.radians(((L - peri) + 180) % 360 - 180)
    E = M + e * math.sin(M)
    for _ in range(8):                                   # solve Kepler's equation
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    x1, y1 = a * (math.cos(E) - e), a * math.sqrt(1 - e * e) * math.sin(E)
    O = math.radians(node)
    cw, sw, cO, sO, ci, si = math.cos(w), math.sin(w), math.cos(O), math.sin(O), math.cos(inc), math.sin(inc)
    return ((cw * cO - sw * sO * ci) * x1 + (-sw * cO - cw * sO * ci) * y1,
            (cw * sO + sw * cO * ci) * x1 + (-sw * sO + cw * cO * ci) * y1,
            (sw * si) * x1 + (cw * si) * y1)


def _to_equator(x, y, z):
    c, s = math.cos(OBLIQUITY), math.sin(OBLIQUITY)
    return (x, y * c - z * s, y * s + z * c)


def planet(name, jd):
    """Returns (position in km from Earth's center, brightness as a magnitude)."""
    T = (jd - 2451545.0) / 36525
    p, e = _helio(name, T), _helio("Earth", T)
    g = [a - b for a, b in zip(p, e)]                    # from Earth to the planet
    r, d, R = (math.sqrt(sum(v * v for v in q)) for q in (p, g, e))
    i = math.degrees(math.acos(max(-1.0, min(1.0, (r * r + d * d - R * R) / (2 * r * d)))))   # phase angle
    k = 5 * math.log10(r * d)
    mag = {"Mercury": -0.42 + k + 0.0380 * i - 0.000273 * i ** 2 + 0.000002 * i ** 3,
           "Venus": -4.40 + k + 0.0009 * i + 0.000239 * i ** 2 - 0.00000065 * i ** 3,
           "Mars": -1.52 + k + 0.016 * i,
           "Jupiter": -9.40 + k + 0.005 * i,
           "Saturn": -8.88 + k + 0.044 * i}[name]
    return tuple(v * AU for v in _to_equator(*g)), mag


def _moon_ecliptic(jd):
    T = (jd - 2451545.0) / 36525
    s = lambda a, b: math.sin(math.radians(a + b * T))
    c = lambda a, b: math.cos(math.radians(a + b * T))
    lam = (218.32 + 481267.881 * T + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36) + 0.66 * s(235.7, 890534.22)
           + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05) - 0.11 * s(186.5, 966404.03))
    beta = 5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21)
    par = 0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36) + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74)
    return lam % 360, beta, RE / math.sin(math.radians(par))


def moon(jd):
    """The Moon's position in km from Earth's center."""
    lam, beta, dist = _moon_ecliptic(jd)
    l, b = math.radians(lam), math.radians(beta)
    return tuple(dist * v for v in _to_equator(math.cos(b) * math.cos(l), math.cos(b) * math.sin(l), math.sin(b)))


def sun_longitude(jd):
    n = jd - 2451545.0
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    return (280.460 + 0.9856474 * n + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360


PHASES = [(10, "New Moon", "🌑"), (80, "Waxing Crescent", "🌒"), (100, "First Quarter", "🌓"), (170, "Waxing Gibbous", "🌔"),
          (190, "Full Moon", "🌕"), (260, "Waning Gibbous", "🌖"), (280, "Last Quarter", "🌗"), (350, "Waning Crescent", "🌘"),
          (361, "New Moon", "🌑")]


def moon_phase(jd):
    """Returns (name, emoji, percent lit, days since new moon)."""
    lam, beta, _ = _moon_ecliptic(jd)
    angle = (lam - sun_longitude(jd)) % 360                # 0 = new, 90 = first quarter, 180 = full
    elong = math.acos(math.cos(math.radians(beta)) * math.cos(math.radians(angle)))
    lit = round((1 - math.cos(elong)) / 2 * 100)
    name, emoji = next((n, e) for limit, n, e in PHASES if angle < limit)
    return name, emoji, lit, round(angle / 360 * 29.53, 1)

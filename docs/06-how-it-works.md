# 6. How it works

## 1. Orbit data (TLE)
Space agencies track the ISS with radar and publish its orbit as a **TLE** (two-line element set): two lines of numbers that describe the shape of its orbit and where it was at a certain moment. The tracker downloads the latest TLE from [CelesTrak](https://celestrak.org) twice a day and saves it in `data/iss_tle.txt`, so it keeps working if the internet drops.

The ISS orbit changes slowly: thin air at 420 km drags on it, and it fires its engines now and then to boost back up. That's why fresh data matters. A TLE more than a couple of weeks old can be off by minutes.

## 2. Where is it right now? (SGP4)
The `sgp4` Python package runs **SGP4**, the same standard orbit model space agencies use with TLEs. Given a time, it returns the ISS's position and speed in space.

Then `server.py` does three conversions:
1. **Space → Earth:** Earth spins under the ISS, so the position is rotated by how far Earth has turned (called *sidereal time*).
2. **Earth position → latitude, longitude and altitude**, using the exact shape of the Earth (it's slightly squashed at the poles, the WGS-84 model).
3. **From your home:** the direction (compass bearing) and height above your horizon (elevation).

## 3. Predicting passes
The Pi checks the ISS's height above your horizon every 20 seconds for the next 4 days. Whenever it rises above your **lowest height** setting, that's a pass. It then zooms in to find the exact rise, highest point and set times to within about a second.

## 4. Can you see it?
For each moment of a pass, it checks two things:
- **Is the ISS in sunlight?** Earth's shadow is modeled as a cylinder behind the Earth. If the ISS is inside it, it's dark.
- **Is your sky dark?** The Sun has to be at least 6° below your horizon.

If both are true, that part of the pass is **visible**, marked **👀 Yes**.

## 5. Alerts
Every 20 seconds, it looks for a visible pass starting within your alert time. If there is one and it hasn't already alerted for it, it sends a message to your ntfy topic. It remembers which passes it already alerted for in `data/alerts_sent.json`, so you never get the same alert twice.

## How accurate is it?
We compared it with [Skyfield](https://rhodesmill.org/skyfield/), a professional astronomy library, over 2 days of passes:

| Check | Difference |
|---|---|
| ISS latitude and longitude | under 0.001° (about 50 meters) |
| Pass start, peak and end times | about 1 second |
| Highest point of each pass | under 0.5° |
| In sunlight or in shadow | matched every time |

That's far more accurate than you need to spot it with your eyes.

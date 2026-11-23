# 8. Build log: problems we hit

Building something real always means hitting problems. Here is every problem that came up while building this tracker, what caused it, and how it was fixed. New problems get added to the end as the project goes on.

## Part 1: Writing the code

### 1. The space-data websites were blocked on the computer where the code was written
**Problem:** The computer used to write the code couldn't reach CelesTrak (orbit data) or ntfy, so the tracker couldn't download live data there.
**Fix:** We tested the orbit math with a saved ISS orbit from 2014, with the clock set back to that date. We then compared every result with **Skyfield**, a professional astronomy library. Positions matched within 0.001° and pass times within about 1 second. Live data gets tested on the real Pi, which has normal internet.
**Lesson:** If you can't test something directly, compare against something you trust.

### 2. The map library came from the internet, so one website being down could break the whole page
**Problem:** The map library (Leaflet) was first loaded from a website called unpkg. When that site can't be reached, the page's code stops completely, so even the stats and passes disappear, not just the map.
**Fix:** The library is now included in the project (`static/leaflet/`) and served by the Pi. Only the map pictures (tiles) still come from the internet, and if they fail, everything else keeps working.

### 3. The path line drew a stripe across the whole map
**Problem:** When the ISS crosses the line between +180° and −180° longitude (in the Pacific), the line jumped from the far right of the map to the far left.
**Fix:** The line is split into pieces wherever the longitude jumps by more than 180°.

### 4. Alerts could repeat every 20 seconds
**Problem:** The alert check runs every 20 seconds. Without a memory, the same pass would trigger an alert again and again.
**Fix:** The tracker saves which passes it already alerted for in `data/alerts_sent.json`. A test that ran the check three times before one pass sent exactly one alert.

### 5. Alert times came out in the wrong time zone
**Problem:** In testing, the alert said "Look N at 10:31 AM" for a pass that was really at 5:31 AM local time. The test computer's clock was set to UTC.
**Fix:** The Pi writes times using its own time zone, so the guide now has a **Set your time zone** step ([Start here, step 2](00-start-here.md)).

### 6. It needed to run next to the Pi Stock Tracker
**Problem:** The stock tracker already uses port 8000 on the same Pi.
**Fix:** This tracker uses port **8080**, so both run at the same time.

### 7. Older Pi OS versions have Python 3.9
**Problem:** Some Raspberry Pi OS versions come with Python 3.9, which doesn't understand some newer Python features.
**Fix:** The code avoids newer-only features, and needs just one package (`sgp4`), which has ready-made downloads for the Pi.

### 8. Keeping your location private
**Problem:** Pass predictions need your location, and the code is public on GitHub.
**Fix:** Your location is only saved in `config.json` on your Pi, which is listed in `.gitignore` so it can never be uploaded. The page also asks for your town's coordinates rounded to 2 decimal places instead of your exact address.

## Part 2: Running it on the real Pi
*Problems from installing and running it on a real Raspberry Pi 4 will be added here.*

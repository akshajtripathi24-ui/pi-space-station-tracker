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

## Part 2: Adding 8 new features (version 1.1)
Version 1.1 added km/miles, day/night shading, the morning summary, fun stats, the sky chart, the cloud check, Tiangong and Hubble, and NASA's live video. These problems came up while building them.

### 9. The weather website was blocked too
**Problem:** Just like CelesTrak in problem 1, the computer used to write the code couldn't reach Open-Meteo (the cloud forecast).
**Fix:** For testing, the code was given a made-up forecast in exactly the same format Open-Meteo uses, with the clouds changing every hour. That proved the right forecast hour gets matched to each pass. The real forecast gets tested on the Pi.

### 10. With no internet, the website would have taken a minute to start
**Problem:** Version 1.0 downloaded the ISS orbit data *before* starting the website. With three spacecraft, if the internet was down, the Pi would wait up to 20 seconds for each one, so the page wouldn't load for a whole minute.
**Fix:** It now loads the saved orbit data first, starts the website straight away, and downloads fresh data in the background.

### 11. Upgrading from version 1.0 would have thrown away the saved orbit
**Problem:** Version 1.0 saved the ISS orbit in `data/iss_tle.txt`. Version 1.1 saves one file per spacecraft (`data/tle_iss.txt` and so on), so the new code wouldn't have found the old file.
**Fix:** If `tle_iss.txt` doesn't exist yet, it reads the old `iss_tle.txt`. A test started version 1.1 with only the old file, and the ISS showed up right away.

### 12. The sky chart crashed the page
**Problem:** The page error said `Cannot read properties of null (reading 'forEach')`. The page redraws every second, so it tried to draw the sky chart before the pass's path had finished downloading from the Pi.
**Fix:** The chart now waits until the path has arrived.

### 13. The labels on the sky chart piled on top of each other
**Problem:** On a low pass, the start time, end time and height labels were all squeezed together near the edge of the circle and you couldn't read them.
**Fix:** The chart now just has a green dot for the start, an arrow for the direction and the highest point, and the times are written in a sentence under the chart.

### 14. "Highest" pointed at a part of the pass you can't see
**Problem:** On some passes the highest point happens while the spacecraft is still in Earth's shadow. The sky chart said "highest 18°", but the part you could see only went up to about 15°.
**Fix:** For visible passes, the chart and caption now use the highest point you can actually **see**.

### 15. The morning summary could arrive at night
**Problem:** The first version sent the summary any time after 8 AM if it hadn't sent one that day. So switching the Pi on at 9 PM would send a "morning" summary at 9 PM.
**Fix:** It only sends in the 3 hours after your summary time. A test at 7:59, 8:00, 8:20 and 11:30 the next day sent exactly one summary, at 8:00.

### 16. "-41,400 trips around Earth since launch"
**Problem:** The test used orbit data from 2014 with the clock set to 2014, but Tiangong was launched in 2021. So it counted trips backward.
**Fix:** The count can never go below zero. It can't happen with real data, but now it can't happen at all.

### 17. "Where is the Tiangong right now?"
**Problem:** The page said "the ISS", so it also said "the Tiangong" and "the Hubble", which sounds wrong.
**Fix:** It says "the ISS", but just "Tiangong" and "Hubble".

## Part 3: Running it on the real Pi
*Problems from installing and running it on a real Raspberry Pi 4 will be added here.*

# 🛰️ Pi Space Station Tracker

A web app that runs on a Raspberry Pi and tracks the **International Space Station (ISS)** live, plus China's **Tiangong** space station, the **Hubble Space Telescope** and the newest **Starlink train**. It shows where they are right now on a world map, predicts when they'll fly over **your town**, checks the cloud forecast, and sends an **alert to your phone** a few minutes before a pass you can actually see, so you can go outside and watch it.

You only need the Pi. No sensors, wires or add-on boards. Open it on any phone, tablet or computer on your home Wi-Fi.

## Features

- **🌍 Live map:** the ISS moving across the world, where it's been (dashed line), where it's going next (solid line), and a circle showing everywhere on Earth that can see it right now.
- **🌗 Day and night on the map:** the night side of Earth is shaded, and ☀️ marks where the Sun is straight overhead.
- **🛰️ Four things to track:** switch between the **ISS**, **Tiangong**, **Hubble** and the newest **Starlink train** with the buttons at the top.
- **📏 Kilometers or miles:** one tap at the top of the page switches every distance and speed.
- **📊 Live stats:** what it's over (the country or ocean, like "Brazil" or "Pacific Ocean"), its altitude (about 420 km), its speed (about 27,600 km/h), whether it's in sunlight or in Earth's shadow, and where it is from your home.
- **🤩 Fun stats:** how far it has traveled today, how many trips around Earth since launch, how long one trip takes, and a countdown to the crew's next sunrise or sunset (they get about 16 a day).
- **🔭 Pass predictions:** every time it passes over you in the next 4 days, with the time, which direction to look, how high it gets, and whether you can actually **see** it.
- **⭐ Pass ratings and brightness:** every visible pass gets 1 to 5 stars and a brightness forecast, like "Super bright, like Venus".
- **🧭 Sky chart:** a compass-style picture of the pass's path across your sky, with the Moon and planets. Tap any pass to see its chart.
- **🌙 Tonight's sky:** the Moon phase and which planets you can see tonight.
- **☁️ Cloud check:** the cloud forecast for each pass you could see, so you know if it's worth going outside.
- **⏱️ Countdown** to the next pass you can see, with plain-English directions ("Look NW. It climbs halfway up and fades out in the E").
- **📱 Phone alerts:** a notification a few minutes before a visible pass, using the free ntfy app. No account needed. You can choose to only get alerts for the best passes.
- **🔊 Talking countdown:** the page tells you out loud when to look up and where.
- **🏅 Spotter log and badges:** tap "I saw it!" after a pass and earn 15 badges.
- **📅 Calendar:** add visible passes to your phone's calendar.
- **📉 Watch the ISS fall:** a chart of its height over the weeks, with the jumps when it fires its engines.
- **📲 Home screen app:** put it on your phone's home screen with its own icon.
- **🌅 Morning summary:** one message each morning listing the day's visible passes.
- **📺 Live view from the ISS:** NASA's live video, right on the page. (Tiangong and Hubble don't have a live video you can watch, so the page explains why.)
- **👩‍🚀 Who's on board:** the names of the astronauts on the ISS and Tiangong right now.
- **Runs by itself:** starts when the Pi boots, restarts if it crashes, updates its orbit data twice a day, and updates with one command.
- **Private:** your location stays on your Pi. It's never uploaded anywhere.

## 👉 New here? Start with the checklist

**[0. Start here: the whole project, step by step](docs/00-start-here.md)** takes you from a Pi to phone alerts, with the exact commands and a "You're done when…" check for each step.

## Step-by-step guides

| # | Guide | What you'll do | Needed? |
|---|---|---|---|
| 0 | [**Start here**](docs/00-start-here.md) | The whole project as one checklist, in order | ✅ Start here |
| 1 | [Get your Raspberry Pi ready](docs/01-prepare-the-pi.md) | Install Raspberry Pi OS, turn on SSH, **set your time zone**, connect from your computer | If your Pi isn't set up yet |
| 2 | [Install the tracker](docs/02-install.md) | Download, install, auto-start, open the website, update, uninstall | ✅ Yes |
| 3 | [Set your location](docs/03-set-your-location.md) | Find your town's coordinates and enter them, safely | ✅ Yes, for passes |
| 4 | [Phone alerts](docs/04-phone-alerts.md) | Install ntfy, subscribe, test, choose when alerts arrive | Optional |
| 5 | [How to spot the ISS](docs/05-spot-the-iss.md) | What it looks like, where to look, and the "fist trick" for measuring height | Recommended |
| 6 | [How it works](docs/06-how-it-works.md) | Orbit data, the SGP4 math, and how it decides if you can see a pass | For the curious |
| 7 | [Troubleshooting](docs/07-troubleshooting.md) | Every error we've seen and how to fix it | When stuck |
| 8 | [Build log: problems we hit](docs/08-build-log.md) | The real problems that came up while building this, and how they were fixed | For the curious |
| 9 | [Extras](docs/09-extras.md) | Badges, the talking countdown, calendar, home screen app, watching the ISS fall, tonight's sky | Fun |

## Quick install (if your Pi is already set up)

Run these on the Pi, one line at a time:

```bash
sudo apt update
sudo apt install -y git python3-venv
git clone https://github.com/akshajtripathi24-ui/pi-space-station-tracker ~/isstracker
cd ~/isstracker
python3 -m venv venv
venv/bin/pip install -r requirements.txt
bash setup-autostart.sh
```

Then open **http://raspberrypi.local:8080** (or `http://YOUR-PI-IP:8080`) in a browser, and set your location at the bottom of the page.

**Update later:** `cd ~/isstracker && git pull && sudo systemctl restart isstracker`

**Version 1.1** added Tiangong and Hubble, km/miles, day/night shading, the sky chart, the cloud check, the morning summary, fun stats and NASA's live video.
**Version 1.2** added pass ratings, brightness forecasts, country and ocean names, the talking countdown, the spotter log and badges, the Moon and planets, calendar files, Starlink trains, the home screen app and the "watch the ISS fall" chart.
If you installed an older version, the update command above is all you need. Your settings are kept.

It uses port **8080**, so it can run on the same Pi as the [Pi Stock Tracker](https://github.com/akshajtripathi24-ui/pi-stock-tracker) (port 8000).

## Good to know

- **Keep it on your home network.** Don't forward ports on your router or put it on the public internet. It has no password, and it knows your location.
- **Use your town's location, not your exact address.** Two decimal places (about 1 km) gives exactly the same pass times.
- Data comes from free services: orbit data from [CelesTrak](https://celestrak.org), the crew list from [Open Notify](http://open-notify.org), the cloud forecast from [Open-Meteo](https://open-meteo.com), country borders from [Natural Earth](https://www.naturalearthdata.com) (public domain), map tiles from [OpenStreetMap](https://www.openstreetmap.org/copyright), and the live video from NASA on YouTube. Please don't change the code to download from them more often.
- This is a student learning project and isn't affiliated with NASA.

## Files

| File | What it is |
|---|---|
| `server.py` | The whole app: downloads orbit data, does the orbit math, predicts passes, sends alerts, and serves the website |
| `index.html` | The website you see in the browser |
| `places.py` | Turns a latitude and longitude into a country or ocean name |
| `sky.py` | Works out where the Moon and planets are, and the Moon's phase |
| `static/world.json` | Country borders ([Natural Earth](https://www.naturalearthdata.com), public domain, via the [world-atlas](https://github.com/topojson/world-atlas) package) |
| `static/icons/`, `static/manifest.webmanifest` | The 🛰️ icon and settings for putting it on your home screen |
| `static/leaflet/` | The map library ([Leaflet](https://leafletjs.com), BSD-2 license), included so the page works even if the library's website is down |
| `setup-autostart.sh` | Makes the tracker start by itself when the Pi boots |
| `requirements.txt` | The one Python package it needs: `sgp4` |
| `config.json`, `data/` | Created on your Pi: your settings, saved orbit data (`data/tle_*.txt`), which alerts were already sent, your spotter log (`data/sightings.json`) and the height history (`data/history.json`). Never uploaded to GitHub |

## License

MIT. See [LICENSE](LICENSE).

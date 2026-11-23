# 🛰️ Pi Space Station Tracker

A web app that runs on a Raspberry Pi and tracks the **International Space Station (ISS)** live. It shows where the ISS is right now on a world map, predicts when it will fly over **your town**, and sends an **alert to your phone** a few minutes before a pass you can actually see, so you can go outside and watch it.

You only need the Pi. No sensors, wires or add-on boards. Open it on any phone, tablet or computer on your home Wi-Fi.

## Features

- **🌍 Live map:** the ISS moving across the world, where it's been (dashed line), where it's going next (solid line), and a circle showing everywhere on Earth that can see it right now.
- **📊 Live stats:** what it's over, its altitude (about 420 km), its speed (about 27,600 km/h), whether it's in sunlight or in Earth's shadow, and where it is from your home.
- **🔭 Pass predictions:** every time the ISS passes over you in the next 4 days, with the time, which direction to look, how high it gets, and whether you can actually **see** it.
- **⏱️ Countdown** to the next pass you can see, with plain-English directions ("Look NW. It climbs halfway up and fades out in the E").
- **📱 Phone alerts:** a notification a few minutes before a visible pass, using the free ntfy app. No account needed.
- **👩‍🚀 Who's on board:** the names of the astronauts on the ISS right now.
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

It uses port **8080**, so it can run on the same Pi as the [Pi Stock Tracker](https://github.com/akshajtripathi24-ui/pi-stock-tracker) (port 8000).

## Good to know

- **Keep it on your home network.** Don't forward ports on your router or put it on the public internet. It has no password, and it knows your location.
- **Use your town's location, not your exact address.** Two decimal places (about 1 km) gives exactly the same pass times.
- Data comes from free services: orbit data from [CelesTrak](https://celestrak.org), the crew list from [Open Notify](http://open-notify.org), and map tiles from [OpenStreetMap](https://www.openstreetmap.org/copyright). Please don't change the code to download from them more often.
- This is a student learning project and isn't affiliated with NASA.

## Files

| File | What it is |
|---|---|
| `server.py` | The whole app: downloads orbit data, does the orbit math, predicts passes, sends alerts, and serves the website |
| `index.html` | The website you see in the browser |
| `static/leaflet/` | The map library ([Leaflet](https://leafletjs.com), BSD-2 license), included so the page works even if the library's website is down |
| `setup-autostart.sh` | Makes the tracker start by itself when the Pi boots |
| `requirements.txt` | The one Python package it needs: `sgp4` |
| `config.json`, `data/` | Created on your Pi: your settings and saved orbit data. Never uploaded to GitHub |

## License

MIT. See [LICENSE](LICENSE).

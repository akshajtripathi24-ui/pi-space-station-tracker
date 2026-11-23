# 0. Start here: the whole project, step by step

Follow these steps in order. Each one has a **✅ You're done when…** check, so you always know it worked before moving on.

**Time:** about 30–45 minutes if your Pi is already set up.
**You need:** a Raspberry Pi (any Pi 3, 4 or 5 works; this was built on a Pi 4) with power supply and microSD card, a computer on your home Wi-Fi, and (optional) a phone for alerts.

---

## Part A: Get the Pi ready
*Skip to Part B if your Pi already runs Raspberry Pi OS and you can SSH into it.*

**Step 1. Set up the Pi.** Follow [1. Get your Raspberry Pi ready](01-prepare-the-pi.md).
✅ You're done when you can type `ssh pi@raspberrypi.local` (with your own username) on your computer and see a prompt like `pi@raspberrypi:~ $`.

**Step 2. Set the time zone.** On the Pi, run:
```bash
sudo raspi-config
```
Choose **Localisation Options → Timezone** and pick your area and city. Then **Finish**.
✅ You're done when `date` shows your local time.
*Why it matters: the alert messages say "Look NW at 7:42 PM". Without this, the times would be in UTC.*

## Part B: Install the tracker

**Step 3. Update the Pi and install git.**
```bash
sudo apt update
sudo apt install -y git python3-venv
```
✅ You're done when the last line has no `E:` errors.

**Step 4. Download the tracker from GitHub.**
```bash
git clone https://github.com/akshajtripathi24-ui/pi-space-station-tracker ~/isstracker
cd ~/isstracker
```
✅ You're done when `ls` shows `server.py`, `index.html` and `setup-autostart.sh`.

**Step 5. Install the one Python package it needs.**
```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```
✅ You're done when you see `Successfully installed sgp4` (or `Requirement already satisfied`).

**Step 6. Make it start by itself.**
```bash
bash setup-autostart.sh
```
✅ You're done when it says `Done!` and `systemctl is-active isstracker` says `active`.

**Step 7. Open the website.** On any device on your Wi-Fi, open **http://raspberrypi.local:8080** (use your Pi's name if you changed it). If that doesn't load, use the IP address: run `hostname -I` on the Pi and open `http://THAT-IP:8080`.
✅ You're done when you see the map with the 🛰️ moving and the badge at the top says **● Live**.

## Part C: Make it yours

**Step 8. Set your location.** Follow [3. Set your location](03-set-your-location.md), then press **Save**.
✅ You're done when the 🏠 appears on the map and the **Upcoming passes** table fills in.

**Step 9. Phone alerts (optional).** Follow [4. Phone alerts](04-phone-alerts.md).
✅ You're done when **Send test notification** makes your phone buzz.

**Step 10. Go see it!** Read [5. How to spot the ISS](05-spot-the-iss.md), then wait for a pass marked **👀 Yes**.
✅ You're done when you've seen a bright dot glide across the sky. 🎉

**Step 11. Try the extras (optional).**
- Tap **Tiangong** or **Hubble** at the top to track China's space station or the Hubble telescope.
- Tap **miles** if you prefer miles to kilometers.
- Tap any pass in the table to see its **🧭 sky chart**.
- Press **▶ Start NASA's live video** to watch Earth from space.
- Tick **Morning summary** in the settings to get the day's passes each morning.

✅ You're done when you've found your favorite. 🛰️

---

**Stuck?** Check [7. Troubleshooting](07-troubleshooting.md). Curious what went wrong while building it? See the [build log](08-build-log.md).

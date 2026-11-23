# 9. Extras: badges, talking countdown, calendar and more

These are all on the tracker page. None of them need extra hardware.

## 🏅 Spotter log and badges
After you see a pass, tap **👀 I saw it!** (under the countdown, in the **Next time you can see it** box). It appears when a visible pass starts and stays for 6 hours after it ends. Each sighting goes into your **Spotter log** and can earn badges:

| Badge | How to earn it |
|---|---|
| 👀 First Sighting | See your first pass |
| 🖐️ High Five | See 5 passes |
| 🔟 Perfect Ten | See 10 passes |
| 🏆 Spotter Legend | See 25 passes |
| 🛰️ ISS Spotter | See the ISS |
| 🚀 Tiangong Spotter | See Tiangong |
| 🔭 Hubble Hunter | See Hubble |
| ✨ Train Spotter | See a Starlink train |
| 🌌 Full Set | See all four: ISS, Tiangong, Hubble and Starlink |
| ⬆️ Straight Up | See a pass 70° or higher |
| 🌟 Super Bright | See a pass as bright as Venus |
| 🌅 Early Bird | See a pass before 6 AM |
| 🦉 Night Owl | See a pass after 10 PM |
| ☁️ Cloud Buster | See a pass when the forecast said cloudy |
| 🔥 Hat Trick | See passes 3 days in a row |

Tapped it by mistake? Press **✖** next to that sighting to remove it. Your log is saved on the Pi in `data/sightings.json`, so it's the same on every phone and computer.

## 🔊 Talking countdown
Press **🔈 Talking countdown: off** under the countdown to turn it on. The page then speaks out loud:
- 5 minutes before: *"Get ready! The ISS will appear in the north-west in 5 minutes."*
- 1 minute before: *"One minute! Look toward the north-west."*
- When it appears: *"Look up now!"*
- At its highest point: *"It's at its highest point now, 46 degrees up…"*
- When it's gone: *"Did you see it?"*

It uses the speaker of the phone or computer showing the page, so **keep the page open and the screen on**. Each device remembers whether it's on.

## 📅 Add passes to your calendar
Press **📅 Add visible passes to my calendar** above the passes table. It downloads a calendar file with every visible pass of the spacecraft you're looking at, with a reminder before each one. Open the file to add the passes to your phone's or computer's calendar. Passes change a little as new orbit data comes in, so do it again every few days.

## 📲 Put it on your home screen
- **iPhone or iPad:** open the page in **Safari**, tap **Share**, then **Add to Home Screen**. It opens full screen with its own 🛰️ icon, like a real app.
- **Android:** in **Chrome**, tap **⋮**, then **Add to Home screen**. You get the 🛰️ icon, but it opens in Chrome. (Android only installs full apps from `https://` websites, and the Pi uses `http://`.)

It only works on your home Wi-Fi, because that's where your Pi is.

## 📉 Watch the ISS fall
Every time the Pi downloads new orbit data (twice a day), it saves the spacecraft's **average height** in `data/history.json`. The chart starts empty and fills up over the days and weeks:
- The line slowly goes **down**: there's still a tiny bit of air 400 km up, and it slows the ISS down, so it sinks (often 50–100 meters a day).
- Every so often it **jumps up** 🚀: that's a **reboost**, when the ISS fires engines to climb back up.
- Hubble has no engines, so its line only goes down.

Move your finger or mouse over the chart to see each measurement, or open **Show the numbers**.

## 🌙 Tonight's sky
Shows tonight's **Moon phase**, when the Moon rises and sets, and which **planets** you can see, when, and in which direction. Planets look like bright stars that stay in the same place for hours. The ISS crosses the whole sky in a few minutes. The **sky chart** shows the Moon and bright planets too, so you can use them to find your way.

## 📍 Where is it over?
The **Over** box says the country or ocean the spacecraft is above, like *Brazil* or *🌊 Pacific Ocean*. It uses a map of country borders saved on the Pi (`static/world.json`), so it works without internet.

**Next:** back to the [README](../README.md)

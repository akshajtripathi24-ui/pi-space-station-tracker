# 3. Set your location

The tracker needs to know roughly where you are to work out when the ISS passes over you.

## 🔒 Use your town, not your exact address
Pass times are the same for everywhere within a few kilometers, so you don't need your exact location. **Two decimal places is plenty** (about 1 km). For example, use `40.71, -74.01`, not `40.712776, -74.005974`.

Your location is saved only on your Pi, in `config.json`. It's never uploaded to GitHub or anywhere else. Still, don't share screenshots of the settings box, and don't put the tracker on the public internet.

## Find your town's coordinates
**Google Maps on a computer:**
1. Search for your **town** (not your street).
2. Right-click the middle of the town. The first line of the menu shows two numbers, like `40.7128, -74.0060`.
3. The first number is the **latitude**, and the second is the **longitude**. Round each to **2 decimal places**: `40.71` and `-74.01`.

**Keep the minus signs!** West of London (all of the Americas) has a **negative** longitude. South of the equator has a **negative** latitude.

## Enter it
At the bottom of the tracker page, under **Your location**:
1. Type a name, like `Home` (it's only shown to you).
2. Type the **latitude** and **longitude**.
3. Press **Save**.

The 🏠 appears on the map and the **Upcoming passes** table fills in.

## The other settings
| Setting | What it means | Default |
|---|---|---|
| **Lowest height to count** | Passes lower than this (in degrees above the horizon) are ignored, because trees and houses block them | 10° |
| **Alert me this many minutes before** | When the phone alert arrives | 10 minutes |
| **Send phone alerts before a pass** | Turns alerts on or off | On |
| **Only alert when I can actually see it** | Skips passes in daylight or when the spacecraft is in Earth's shadow | On |
| **Send alerts for** | Which spacecraft send alerts: ISS, Tiangong and/or Hubble | ISS only |
| **Morning summary** | One message each morning listing the day's visible passes, at the time you pick | On, 8:00 AM |
| **Check the cloud forecast** | Shows the forecast clouds for each visible pass, and adds it to alerts | On |
| **Live video link** | Leave empty for NASA's live video, or paste a YouTube link to a different live video | Empty |

Press **Save** after changing any of them.

## The switches at the top of the page
| Switch | What it does |
|---|---|
| **🛰️ ISS · 🛰️ Tiangong · 🔭 Hubble** | Which spacecraft the map, stats, passes and sky chart show |
| **km · miles** | Shows distances and speeds in kilometers or miles |

These are remembered by each phone or computer you use, so your phone can show miles while your laptop shows km. They don't change your alerts.

**Next:** [4. Phone alerts](04-phone-alerts.md)

# 4. Phone alerts

The Pi checks every 20 seconds. A few minutes before a pass you can see, it sends a notification to your phone, like this:

> **ISS overhead in 10 min!**
> ⭐⭐⭐⭐ Look NW at 7:42 PM. It climbs to 47° (high in the sky) and disappears SE at 7:48 PM. Visible for about 5 min. Very bright, brighter than any star: a steady dot moving fast, no blinking lights.

It works even when the website is closed. When the cloud check is on, the alert also says what the clouds will be like, for example *"Partly cloudy (45% clouds)."*

## Set it up
1. Install the free **ntfy** app on your phone ([App Store](https://apps.apple.com/app/ntfy/id1625396347) or [Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy)). You don't need an account.
2. On the tracker page, find **📱 Phone alerts** and press **Copy** next to the topic (it looks like `iss-3f9a1c…`).
3. In the ntfy app, tap **+**, paste the topic **exactly**, and tap **Subscribe**.
4. Back on the tracker page, press **Send test notification**.

✅ Your phone should buzz within a few seconds.

## 🌅 Morning summary
Once a day, at the time you pick (8:00 AM unless you change it), you get one message listing every visible pass in the next 24 hours:

> **2 visible passes in the next 24 hours**
> 6:12 PM ISS: look WNW, up to 52°, clear
> 7:48 PM ISS: look W, up to 18°, partly cloudy

If there are no visible passes that day, it stays quiet. If the Pi was switched off at that time, it sends the summary when it's back on, up to 3 hours late. To try it right now, press **Send test morning summary**.

## Only the best passes
Getting too many alerts? Set **Only alert for passes rated at least** to ⭐⭐⭐. You'll only hear about bright, high passes. (See [5. How to spot the ISS](05-spot-the-iss.md#ratings-and-brightness) for how the stars work.)

## Alerts for Tiangong, Hubble and Starlink
Under **Send alerts for** in the settings, tick **Tiangong**, **Hubble** and/or **Starlink trains**. Their alerts look the same, with their own name: *"Tiangong overhead in 10 min!"* The morning summary includes them too.

## 🔒 Keep your topic private
The topic is like a secret channel name: **anyone who knows it can read your alerts.** The tracker makes a random one for you. Don't post it online or show it in a video. If it ever leaks, press **New topic** and subscribe to the new one.

## Problems?
| Problem | Fix |
|---|---|
| The test notification never arrives | Check the topic is pasted exactly (no spaces). On iPhone, allow notifications for ntfy in Settings. |
| `❌` error when pressing the test button | The Pi can't reach ntfy.sh. Check the Pi's internet: `ping -c 3 ntfy.sh` |
| No alert before a pass | Is **Send phone alerts** ticked, and is that spacecraft ticked under **Send alerts for**? With **Only alert when I can actually see it** ticked, you only get alerts for passes marked **👀 Yes**. |
| No morning summary | There may be no visible passes that day (it stays quiet then). Check **Morning summary** is ticked, and press **Send test morning summary** to test it. |
| The alert time is wrong by a few hours | Set the Pi's time zone: `sudo raspi-config` → Localisation Options → Timezone. |

**Next:** [5. How to spot the ISS](05-spot-the-iss.md)

# 1. Get your Raspberry Pi ready

*Already have Raspberry Pi OS running and can SSH in? Just do [Step 4](#step-4-set-your-time-zone) and skip to [2. Install the tracker](02-install.md).*

New to Raspberry Pi? This video walks through the whole setup: [Raspberry Pi setup guide (video)](https://www.youtube.com/watch?v=RV0saVGXQ5k).

## Step 1: Put Raspberry Pi OS on the microSD card
1. On your computer, download the free **Raspberry Pi Imager** from [raspberrypi.com/software](https://www.raspberrypi.com/software/).
2. Put the microSD card in your computer and open Imager.
3. Choose your **Pi model**, then **Raspberry Pi OS (64-bit)** (Lite is fine too, since you won't need a desktop), then your **SD card**.
4. When it asks about settings, choose **Edit settings**:
   - Set a **username and password**. Write them down.
   - Turn on **Wireless LAN** and type your Wi-Fi name and password.
   - Set your **time zone**.
   - On the **Services** tab, turn on **SSH** with password authentication.
5. **Save**, then **Write**.

**Tip:** use a good-quality microSD card from a known brand. Most "write failed" errors come from bad or fake cards.

## Step 2: Start the Pi
Put the card in the Pi and plug in the power. Wait 3–5 minutes for the first start. The green light blinks while it's busy.

## Step 3: Connect from your computer (SSH)
- **Windows:** press the Windows key, type `cmd`, press Enter.
- **Mac:** open the **Terminal** app.

Type this, using your own username:
```bash
ssh pi@raspberrypi.local
```
Type `yes` if it asks about a fingerprint, then your password. **Nothing appears while you type the password. That's normal.**

If `raspberrypi.local` doesn't work, use the Pi's IP address instead: find a device called `raspberrypi` in your router's app, or run `hostname -I` on the Pi.

## Step 4: Set your time zone
If you didn't set it in Imager:
```bash
sudo raspi-config
```
**Localisation Options → Timezone**, pick your area and city, then **Finish**. Check it with `date`.

**Next:** [2. Install the tracker](02-install.md)

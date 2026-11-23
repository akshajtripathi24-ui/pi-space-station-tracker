# 2. Install the tracker

Run every command on the Pi (connected over SSH). Type or paste one line at a time.

## Install
```bash
sudo apt update
sudo apt install -y git python3-venv
git clone https://github.com/akshajtripathi24-ui/pi-space-station-tracker ~/isstracker
cd ~/isstracker
python3 -m venv venv
venv/bin/pip install -r requirements.txt
bash setup-autostart.sh
```

What each line does:
| Command | What it does |
|---|---|
| `sudo apt update` | Gets the latest list of software for the Pi |
| `sudo apt install -y git python3-venv` | Installs git (downloads code from GitHub) and Python's virtual environments |
| `git clone … ~/isstracker` | Downloads this project into a folder called `isstracker` |
| `cd ~/isstracker` | Moves into that folder |
| `python3 -m venv venv` | Makes a private Python space for this project, so it can't break anything else |
| `venv/bin/pip install -r requirements.txt` | Installs `sgp4`, the orbit-math package NASA and space agencies use |
| `bash setup-autostart.sh` | Makes the tracker run in the background and start whenever the Pi boots |

## Open it
On any device on your Wi-Fi, open **http://raspberrypi.local:8080**. If that doesn't work, run `hostname -I` on the Pi and open `http://THAT-IP:8080`.

The first time it starts, it downloads the latest ISS orbit data, which takes a few seconds. Then set your location: [3. Set your location](03-set-your-location.md).

## Useful commands
```bash
systemctl is-active isstracker          # is it running? (should say: active)
journalctl -u isstracker -n 30          # the last 30 lines of its log
journalctl -u isstracker -f             # watch the log live (Ctrl+C to stop watching)
sudo systemctl restart isstracker       # restart it
```

## Update to the newest version
```bash
cd ~/isstracker && git pull && sudo systemctl restart isstracker
```
Your settings in `config.json` are kept.

## Uninstall
```bash
sudo systemctl disable --now isstracker
sudo rm /etc/systemd/system/isstracker.service
rm -rf ~/isstracker
```

## Problems?
| Problem | Fix |
|---|---|
| `fatal: destination path '…isstracker' already exists` | You installed it before. Use the update command above instead. |
| `pip` errors while installing `sgp4` | Run `~/isstracker/venv/bin/pip install --upgrade pip`, then try again. |
| The page doesn't load | Check `systemctl is-active isstracker`, then see [Troubleshooting](07-troubleshooting.md). |

**Next:** [3. Set your location](03-set-your-location.md)

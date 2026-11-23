# 7. Troubleshooting

Find your problem below. Most fixes are one command, run on the Pi over SSH.

**First, three checks that fix most problems:**
```bash
systemctl is-active isstracker          # should say: active
journalctl -u isstracker -n 30          # shows the last 30 lines of the log
sudo systemctl restart isstracker       # restarts the tracker
```

## Installing and running
| Problem | Fix |
|---|---|
| `Unit isstracker.service not found` | Auto-start isn't set up. Run `cd ~/isstracker && bash setup-autostart.sh`. |
| `ModuleNotFoundError: No module named 'sgp4'` | Run `~/isstracker/venv/bin/pip install -r ~/isstracker/requirements.txt`, then restart. |
| `Address already in use` | Something else uses port 8080, or a second copy is running. Run `sudo systemctl stop isstracker; pkill -f isstracker/server.py; sudo systemctl start isstracker`. |
| `fatal: destination path … already exists` | It's already installed. Update instead: `cd ~/isstracker && git pull && sudo systemctl restart isstracker`. |

## The website
| Problem | Fix |
|---|---|
| `raspberrypi.local` doesn't load | Some networks don't support `.local` names. Use the IP address: run `hostname -I` on the Pi and open `http://THAT-IP:8080`. |
| The map is gray, but the 🛰️ and lines show | The map pictures come from OpenStreetMap over the internet. Check the device you're browsing on has internet. Everything else still works. |
| The badge says **⚠️ Using saved orbit data** | The Pi couldn't download fresh orbit data. It keeps working with the saved copy. Check the Pi's internet: `ping -c 3 celestrak.org`. |
| An error says `orbit calculation error` | The saved orbit data is too old. Make sure the Pi has internet, then restart the tracker. |
| **Upcoming passes** stays empty | Set your location and press **Save**. |
| "Who's on board" says unavailable | The free crew-list service is sometimes down. It tries again every 6 hours. Nothing else is affected. |

## Times and alerts
| Problem | Fix |
|---|---|
| Times in alerts are a few hours off | Set the Pi's time zone: `sudo raspi-config` → **Localisation Options → Timezone**. Check with `date`. |
| Passes happen at different times than predicted | Check the Pi's clock with `date`. The Pi sets its clock from the internet, so it needs internet after every boot. |
| No visible passes for days | Normal! Visible passes come in groups, often a week or two at a time, then none for a while. |
| The test notification doesn't arrive | See [4. Phone alerts](04-phone-alerts.md#problems). |

Found a problem that isn't here? It might be in the [build log](08-build-log.md).

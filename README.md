# Squat Reminder

A tiny Windows tray app that pops up every hour with a reminder to do 10 squats.

## What it does
- Runs quietly in the system tray.
- Every hour, shows an always-on-top popup: **Done ✅ (+10)** or **Skip**.
- Logs every completed reminder to `squat_log.csv` (timestamp + squat count).
- Tray menu: **Squat Now** (trigger immediately), **Pause/Resume Reminders**, **Today: N squats**, **Quit**.
- Starts automatically at login (after running the installer once).

## Setup
1. Requires Python 3 with tkinter (bundled with standard Windows installs).
2. Run the installer once, from PowerShell in this folder:
   ```powershell
   .\install_startup.ps1
   ```
   This installs `pystray` + `pillow` and adds a shortcut to your Startup folder.

## Run it now (without rebooting)
```powershell
pythonw squat_reminder.pyw
```
Or just double-click `squat_reminder.pyw`.

## Changing the interval
Edit the constants at the top of `squat_reminder.pyw`:
```python
INTERVAL_MINUTES = 60
SQUATS_PER_REMINDER = 10
```

## The log
`squat_log.csv` is a simple `timestamp,squats` CSV appended to on every "Done". It's gitignored since it's personal data — delete it any time to reset your count.

## Uninstall
Delete the shortcut from your Startup folder:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SquatReminder.lnk`

Then quit the running app via the tray icon's **Quit** option (or Task Manager, look for `pythonw.exe`).

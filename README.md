# Squat Reminder

A tiny Windows tray app that pops up on a configurable interval (default: every hour) with a reminder to do 10 squats.

## What it does
- Runs quietly in the system tray.
- On the configured interval, shows a centered, always-on-top, draggable popup: **Done ✓ (+10)** or **Skip**.
- The popup is a small dark card (rounded corners, no OS chrome) showing a plain running count of today's squats — no goals, no progress ring.
- **Control Panel** (tray menu): today/week/month/all-time stat tiles, a reminder-interval control, a trend chart you can switch between Week / Month / Year (with ‹ › navigation through past periods), and a GitHub-style year heatmap with current streak, best day, and year total.
- Every completed reminder is logged to a local **SQLite** database (`squats.db`).
- Tray menu: **Control Panel**, **Pause/Resume Reminders**, **Today: N squats**, **Quit**.
- Starts automatically at login (after running the installer once).

## Setup
1. Requires Python 3 and the [WebView2 runtime](https://developer.microsoft.com/microsoft-edge/webview2/) (preinstalled on Windows 10/11 alongside Edge).
2. Run the installer once, from PowerShell in this folder:
   ```powershell
   .\install_startup.ps1
   ```
   This installs `pywebview` + `pystray` + `pillow` and adds a shortcut to your Startup folder.

## Run it now (without rebooting)
```powershell
pythonw squat_reminder.pyw
```
Or just double-click `squat_reminder.pyw`.

## Changing the interval
Open **Control Panel** from the tray menu and use the **Reminder interval** section — pick a preset (15/30/45/60/90/120 min) or enter a custom value. Changes apply immediately, interrupting the current countdown; no restart needed. The interval is stored in `squats.db`, not in source.

To change squats-per-reminder, edit the constant at the top of `squat_reminder.pyw`:
```python
SQUATS_PER_REMINDER = 10
```

## The data
`squats.db` is a small SQLite database (one row per completed reminder). It's gitignored since it's personal data — delete it any time to reset your history. If you're upgrading from an older version that used `squat_log.csv`, it's migrated into `squats.db` automatically on first run and renamed to `squat_log.csv.migrated`.

## Uninstall
Delete the shortcut from your Startup folder:
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SquatReminder.lnk`

Then quit the running app via the tray icon's **Quit** option (or Task Manager, look for `pythonw.exe`).

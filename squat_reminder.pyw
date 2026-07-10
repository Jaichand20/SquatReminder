import csv
import datetime
import os
import socket
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont

INTERVAL_MINUTES = 60
SQUATS_PER_REMINDER = 10
LOCK_PORT = 47653

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "squat_log.csv")

# Bound for the lifetime of the process; a second launch fails to bind and exits.
_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _lock_socket.bind(("127.0.0.1", LOCK_PORT))
except OSError:
    sys.exit(0)


def log_completion():
    is_new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["timestamp", "squats"])
        writer.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            SQUATS_PER_REMINDER,
        ])


def todays_total():
    if not os.path.exists(LOG_FILE):
        return 0
    today = datetime.date.today().isoformat()
    total = 0
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("timestamp", "").startswith(today):
                try:
                    total += int(row["squats"])
                except (KeyError, ValueError):
                    pass
    return total


class AppState:
    def __init__(self):
        self.paused = False


state = AppState()


class SquatApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.popup = None
        self.timer_id = None
        self.tray_icon = None
        self.schedule_next()

    def schedule_next(self, delay_ms=None):
        if delay_ms is None:
            delay_ms = INTERVAL_MINUTES * 60 * 1000
        if self.timer_id is not None:
            self.root.after_cancel(self.timer_id)
        self.timer_id = self.root.after(delay_ms, self.on_timer)

    def on_timer(self):
        if state.paused:
            self.schedule_next()
            return
        self.show_popup()

    def trigger_now(self):
        self.show_popup()

    def show_popup(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            self.popup.focus_force()
            return

        popup = tk.Toplevel(self.root)
        self.popup = popup
        popup.title("Squat Time!")
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.protocol("WM_DELETE_WINDOW", self.on_skip)

        width, height = 420, 260
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        popup.geometry(f"{width}x{height}+{x}+{y}")

        title_font = tkfont.Font(size=20, weight="bold")
        body_font = tkfont.Font(size=12)

        tk.Label(
            popup, text=f"Time for {SQUATS_PER_REMINDER} squats! \U0001F3CB",
            font=title_font, pady=20, wraplength=380,
        ).pack()
        tk.Label(
            popup, text=f"Today: {todays_total()} squats", font=body_font,
        ).pack(pady=5)

        btn_frame = tk.Frame(popup)
        btn_frame.pack(pady=20)

        tk.Button(
            btn_frame, text=f"Done ✅  (+{SQUATS_PER_REMINDER})", font=body_font,
            bg="#4CAF50", fg="white", padx=15, pady=8,
            command=self.on_done,
        ).pack(side="left", padx=10)

        tk.Button(
            btn_frame, text="Skip", font=body_font, padx=15, pady=8,
            command=self.on_skip,
        ).pack(side="left", padx=10)

        popup.deiconify()
        popup.lift()
        popup.attributes("-topmost", True)
        popup.focus_force()
        popup.grab_set()

    def _close_popup(self):
        if self.popup is not None:
            self.popup.grab_release()
            self.popup.destroy()
            self.popup = None

    def on_done(self):
        log_completion()
        self._close_popup()
        self.schedule_next()
        self.update_tray_menu()

    def on_skip(self):
        self._close_popup()
        self.schedule_next()

    def toggle_pause(self):
        state.paused = not state.paused
        self.update_tray_menu()

    def update_tray_menu(self):
        if self.tray_icon is not None:
            self.tray_icon.update_menu()

    def quit_app(self):
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def build_tray_icon(app):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def make_image():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 58, 58), fill="#4CAF50")
        return img

    def on_squat_now(icon, item):
        app.root.after(0, app.trigger_now)

    def on_toggle_pause(icon, item):
        app.root.after(0, app.toggle_pause)

    def pause_text(item):
        return "Resume Reminders" if state.paused else "Pause Reminders"

    def today_text(item):
        return f"Today: {todays_total()} squats"

    def on_quit(icon, item):
        app.root.after(0, app.quit_app)

    menu = pystray.Menu(
        pystray.MenuItem("Squat Now", on_squat_now),
        pystray.MenuItem(pause_text, on_toggle_pause),
        pystray.MenuItem(today_text, lambda icon, item: None),
        pystray.MenuItem("Quit", on_quit),
    )

    return pystray.Icon("squat_reminder", make_image(), "Squat Reminder", menu)


def main():
    app = SquatApp()
    tray_icon = build_tray_icon(app)
    if tray_icon is not None:
        app.tray_icon = tray_icon
        threading.Thread(target=tray_icon.run, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()

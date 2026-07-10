import csv
import ctypes
import datetime
import os
import socket
import sys
import threading

import webview

INTERVAL_MINUTES = 60
SQUATS_PER_REMINDER = 10
LOCK_PORT = 47653
WINDOW_WIDTH = 360
WINDOW_HEIGHT = 460
CARD_BACKGROUND = "#131315"
CORNER_RADIUS = 26

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


POPUP_HTML = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {{
    margin: 0; padding: 0; width: 100%; height: 100%;
    background: {CARD_BACKGROUND}; overflow: hidden;
  }}
  .card {{
    width: 100%; height: 100%; box-sizing: border-box;
    border-radius: {CORNER_RADIUS}px;
    background:
      radial-gradient(130% 85% at 50% -8%, rgba(255, 69, 88, 0.32), transparent 55%),
      {CARD_BACKGROUND};
    display: flex; flex-direction: column; align-items: center;
    padding: 40px 32px 22px;
    font-family: -apple-system, "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
    color: #f7f7f8;
    -webkit-user-select: none; user-select: none;
  }}
  h1 {{
    font-size: 27px; font-weight: 700; margin: 12px 0 10px;
    letter-spacing: -0.02em; text-align: center;
  }}
  .sub {{ font-size: 14.5px; color: #a2a2a8; margin: 0 0 24px; text-align: center; line-height: 1.5; }}
  .count-block {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 20px; }}
  .count-block .num {{
    font-size: 44px; font-weight: 750; letter-spacing: -0.02em; color: #ffffff;
    font-variant-numeric: tabular-nums; line-height: 1;
  }}
  .count-block .label {{ font-size: 13.5px; font-weight: 500; color: #8f8f96; padding-bottom: 4px; }}
  .actions {{ width: 100%; display: flex; flex-direction: column; gap: 10px; margin-top: auto; }}
  .btn-primary {{
    width: 100%; border: none; padding: 14px; border-radius: 15px;
    background: linear-gradient(120deg, #ff5f6d, #ff375f);
    color: #ffffff; font-size: 15px; font-weight: 650; cursor: pointer;
    box-shadow: 0 10px 22px -8px rgba(255, 55, 95, 0.55);
  }}
  .btn-ghost {{
    border: 1px solid rgba(255, 255, 255, 0.14); background: none; color: #d6d6d9;
    font-size: 13.5px; font-weight: 500; padding: 10px; border-radius: 15px; cursor: pointer;
  }}
  button:focus-visible {{ outline: 2px solid #7ab8ff; outline-offset: 2px; }}
  .btn-primary:hover, .btn-ghost:hover {{ filter: brightness(1.08); }}
  .btn-primary:active, .btn-ghost:active {{ transform: scale(0.98); }}
</style>
</head>
<body>
  <div class="card">
    <h1>Time to move</h1>
    <p class="sub">{SQUATS_PER_REMINDER} squats. Thirty seconds.</p>
    <div class="count-block">
      <span class="num" id="count">{todays_total()}</span>
      <span class="label">squats today</span>
    </div>
    <div class="actions">
      <button class="btn-primary" onclick="pywebview.api.done()">Done ✓ (+{SQUATS_PER_REMINDER})</button>
      <button class="btn-ghost" onclick="pywebview.api.skip()">Skip</button>
    </div>
  </div>
<script>
function setCount(n) {{ document.getElementById('count').textContent = n; }}
</script>
</body>
</html>
"""


class Api:
    def __init__(self, app):
        # Underscore prefix: pywebview recursively introspects public attributes
        # of js_api to build JS bindings, and would otherwise walk into
        # app.window.native (a .NET control tree with circular Accessibility
        # references), which is skipped for names starting with "_".
        self._app = app

    def done(self):
        self._app.on_done()

    def skip(self):
        self._app.on_skip()


def apply_rounded_corners(window, width, height, radius):
    # pywebview's transparent=True doesn't give true desktop-level transparency on
    # Windows (the Form's own background stays opaque white), which showed up as
    # white squares in the corners outside the CSS border-radius. Clipping the
    # actual window shape via SetWindowRgn is the reliable fix.
    hwnd = ctypes.c_void_p(window.native.Handle.ToInt64())
    region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius * 2, radius * 2)
    ctypes.windll.user32.SetWindowRgn(hwnd, region, True)


class SquatApp:
    def __init__(self):
        self.window = None
        self.api = Api(self)
        self.paused = False
        self.tray_icon = None
        self._stop = threading.Event()
        self._quitting = False

    def start(self):
        screen = webview.screens[0]
        pos_x = (screen.width - WINDOW_WIDTH) // 2
        pos_y = (screen.height - WINDOW_HEIGHT) // 2

        self.window = webview.create_window(
            "Squat Reminder", html=POPUP_HTML, js_api=self.api,
            width=WINDOW_WIDTH, height=WINDOW_HEIGHT, x=pos_x, y=pos_y,
            frameless=True, easy_drag=False, on_top=True, resizable=False,
            hidden=True, shadow=True, background_color=CARD_BACKGROUND,
        )
        self.window.events.closing += self._on_closing
        self.window.events.loaded += self._on_loaded
        webview.start(self._run_background, debug=False)

    def _on_closing(self):
        if self._quitting:
            return True
        self.window.hide()
        return False

    def _on_loaded(self):
        # The native Form handle only exists once content has loaded, even for
        # a hidden window -- can't apply this any earlier.
        apply_rounded_corners(self.window, WINDOW_WIDTH, WINDOW_HEIGHT, CORNER_RADIUS)

    def _run_background(self):
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        self.tray_icon = build_tray_icon(self)
        if self.tray_icon is not None:
            self.tray_icon.run()
        else:
            self._stop.wait()

    def _scheduler_loop(self):
        while not self._stop.is_set():
            timed_out = not self._stop.wait(INTERVAL_MINUTES * 60)
            if not timed_out:
                break
            if not self.paused:
                self.show_popup()

    def show_popup(self):
        total = todays_total()
        self.window.evaluate_js(f"setCount({total})")
        self.window.show()

    def trigger_now(self):
        self.show_popup()

    def on_done(self):
        log_completion()
        self.window.hide()
        self.update_tray_menu()

    def on_skip(self):
        self.window.hide()

    def toggle_pause(self):
        self.paused = not self.paused
        self.update_tray_menu()

    def update_tray_menu(self):
        if self.tray_icon is not None:
            self.tray_icon.update_menu()

    def quit_app(self):
        self._quitting = True
        self._stop.set()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.window.destroy()


def build_tray_icon(app):
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def make_image():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((6, 6, 58, 58), fill="#ff375f")
        return img

    def on_squat_now(icon, item):
        app.trigger_now()

    def on_toggle_pause(icon, item):
        app.toggle_pause()

    def pause_text(item):
        return "Resume Reminders" if app.paused else "Pause Reminders"

    def today_text(item):
        return f"Today: {todays_total()} squats"

    def on_quit(icon, item):
        app.quit_app()

    menu = pystray.Menu(
        pystray.MenuItem("Squat Now", on_squat_now),
        pystray.MenuItem(pause_text, on_toggle_pause),
        pystray.MenuItem(today_text, lambda icon, item: None),
        pystray.MenuItem("Quit", on_quit),
    )

    return pystray.Icon("squat_reminder", make_image(), "Squat Reminder", menu)


def main():
    app = SquatApp()
    app.start()


if __name__ == "__main__":
    main()

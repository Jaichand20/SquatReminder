import csv
import datetime
import os
import sqlite3

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "squats.db")
LEGACY_CSV = os.path.join(SCRIPT_DIR, "squat_log.csv")


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS squats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            count INTEGER NOT NULL
        )
        """
    )
    return conn


def init_db():
    conn = _connect()
    conn.close()
    _migrate_csv_if_needed()


def _migrate_csv_if_needed():
    if not os.path.exists(LEGACY_CSV):
        return
    conn = _connect()
    already_populated = conn.execute("SELECT COUNT(*) FROM squats").fetchone()[0] > 0
    if not already_populated:
        with open(LEGACY_CSV, newline="", encoding="utf-8") as f:
            rows = [(row["timestamp"], int(row["squats"])) for row in csv.DictReader(f)]
        if rows:
            conn.executemany("INSERT INTO squats (timestamp, count) VALUES (?, ?)", rows)
            conn.commit()
    conn.close()
    os.replace(LEGACY_CSV, LEGACY_CSV + ".migrated")


def log_completion(count):
    conn = _connect()
    conn.execute(
        "INSERT INTO squats (timestamp, count) VALUES (?, ?)",
        (datetime.datetime.now().isoformat(timespec="seconds"), count),
    )
    conn.commit()
    conn.close()


def _sum_between(start_date, end_date):
    """Sum of counts where the date part of timestamp is in [start_date, end_date)."""
    conn = _connect()
    total = conn.execute(
        """
        SELECT COALESCE(SUM(count), 0) FROM squats
        WHERE substr(timestamp, 1, 10) >= ? AND substr(timestamp, 1, 10) < ?
        """,
        (start_date, end_date),
    ).fetchone()[0]
    conn.close()
    return total


def todays_total():
    today = datetime.date.today()
    return _sum_between(today.isoformat(), (today + datetime.timedelta(days=1)).isoformat())


def all_time_total():
    conn = _connect()
    total = conn.execute("SELECT COALESCE(SUM(count), 0) FROM squats").fetchone()[0]
    conn.close()
    return total


def stats():
    today = datetime.date.today()
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    week_start = (today - datetime.timedelta(days=6)).isoformat()
    month_start = (today - datetime.timedelta(days=29)).isoformat()
    return {
        "today": _sum_between(today.isoformat(), tomorrow),
        "week": _sum_between(week_start, tomorrow),
        "month": _sum_between(month_start, tomorrow),
        "all_time": all_time_total(),
    }


def daily_totals(start_date, end_date):
    """{'YYYY-MM-DD': total} for every date with activity in [start_date, end_date)."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT substr(timestamp, 1, 10) AS d, SUM(count)
        FROM squats
        WHERE substr(timestamp, 1, 10) >= ? AND substr(timestamp, 1, 10) < ?
        GROUP BY d
        """,
        (start_date, end_date),
    ).fetchall()
    conn.close()
    return {d: total for d, total in rows}


def monthly_totals(year):
    """List of 12 totals (Jan..Dec) for the given year."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT substr(timestamp, 6, 2) AS m, SUM(count)
        FROM squats
        WHERE substr(timestamp, 1, 4) = ?
        GROUP BY m
        """,
        (f"{year:04d}",),
    ).fetchall()
    conn.close()
    totals = [0] * 12
    for m, total in rows:
        totals[int(m) - 1] = total
    return totals


def year_daily_totals(year):
    return daily_totals(f"{year:04d}-01-01", f"{year + 1:04d}-01-01")


def current_streak():
    conn = _connect()
    rows = conn.execute("SELECT DISTINCT substr(timestamp, 1, 10) FROM squats").fetchall()
    conn.close()
    active_days = {r[0] for r in rows}
    if not active_days:
        return 0

    today = datetime.date.today()
    cursor = today if today.isoformat() in active_days else today - datetime.timedelta(days=1)
    if cursor.isoformat() not in active_days:
        return 0

    streak = 0
    while cursor.isoformat() in active_days:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


def best_day():
    conn = _connect()
    row = conn.execute(
        """
        SELECT substr(timestamp, 1, 10) AS d, SUM(count) AS total
        FROM squats GROUP BY d ORDER BY total DESC LIMIT 1
        """
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"date": row[0], "count": row[1]}

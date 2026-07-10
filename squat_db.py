import csv
import datetime
import logging
import os
import sqlite3
from contextlib import contextmanager

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, "squats.db")
LEGACY_CSV = os.path.join(SCRIPT_DIR, "squat_log.csv")

logger = logging.getLogger(__name__)


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


@contextmanager
def _connection():
    """Yields a connection, guaranteeing it's closed even if a query raises."""
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with _connection():
        pass
    _migrate_csv_if_needed()


def _migrate_csv_if_needed():
    if not os.path.exists(LEGACY_CSV):
        return
    try:
        with _connection() as conn:
            already_populated = conn.execute("SELECT COUNT(*) FROM squats").fetchone()[0] > 0
            if not already_populated:
                with open(LEGACY_CSV, newline="", encoding="utf-8") as f:
                    rows = [(row["timestamp"], int(row["squats"])) for row in csv.DictReader(f)]
                if rows:
                    conn.executemany("INSERT INTO squats (timestamp, count) VALUES (?, ?)", rows)
                    conn.commit()
        os.replace(LEGACY_CSV, LEGACY_CSV + ".migrated")
    except Exception:
        logger.exception("Failed to migrate legacy CSV %s; left in place for retry", LEGACY_CSV)


def log_completion(count):
    with _connection() as conn:
        conn.execute(
            "INSERT INTO squats (timestamp, count) VALUES (?, ?)",
            (datetime.datetime.now().isoformat(timespec="seconds"), count),
        )
        conn.commit()


def _sum_between(start_date, end_date):
    """Sum of counts where the date part of timestamp is in [start_date, end_date)."""
    with _connection() as conn:
        total = conn.execute(
            """
            SELECT COALESCE(SUM(count), 0) FROM squats
            WHERE substr(timestamp, 1, 10) >= ? AND substr(timestamp, 1, 10) < ?
            """,
            (start_date, end_date),
        ).fetchone()[0]
    return total


def todays_total():
    today = datetime.date.today()
    return _sum_between(today.isoformat(), (today + datetime.timedelta(days=1)).isoformat())


def all_time_total():
    with _connection() as conn:
        total = conn.execute("SELECT COALESCE(SUM(count), 0) FROM squats").fetchone()[0]
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
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT substr(timestamp, 1, 10) AS d, SUM(count)
            FROM squats
            WHERE substr(timestamp, 1, 10) >= ? AND substr(timestamp, 1, 10) < ?
            GROUP BY d
            """,
            (start_date, end_date),
        ).fetchall()
    return {d: total for d, total in rows}


def monthly_totals(year):
    """List of 12 totals (Jan..Dec) for the given year."""
    with _connection() as conn:
        rows = conn.execute(
            """
            SELECT substr(timestamp, 6, 2) AS m, SUM(count)
            FROM squats
            WHERE substr(timestamp, 1, 4) = ?
            GROUP BY m
            """,
            (f"{year:04d}",),
        ).fetchall()
    totals = [0] * 12
    for m, total in rows:
        totals[int(m) - 1] = total
    return totals


def year_daily_totals(year):
    return daily_totals(f"{year:04d}-01-01", f"{year + 1:04d}-01-01")


def current_streak():
    with _connection() as conn:
        rows = conn.execute("SELECT DISTINCT substr(timestamp, 1, 10) FROM squats").fetchall()
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
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT substr(timestamp, 1, 10) AS d, SUM(count) AS total
            FROM squats GROUP BY d ORDER BY total DESC LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {"date": row[0], "count": row[1]}

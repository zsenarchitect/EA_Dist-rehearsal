"""Turn a raw log_<user>.sexyDuck dict into windowed usage metrics.

Pure functions over plain dicts -- no EnneadTab imports, no filesystem, no
clock of its own (today is always passed in). That makes every claim in the
recap testable against a synthetic log.

Deliberately NOT computed here:
  * "hours saved" -- nothing in the log supports it, and a fabricated number
    is exactly the credibility loss the guardrails exist to prevent.
  * success/failure rate -- `result` holds str(out) of arbitrary returns,
    where "None" is the overwhelmingly common SUCCESS value.
"""

import datetime
import re


LOG_KEY_FORMAT = "%Y-%m-%d_%H-%M-%S"

# TIME.get_readable_time emits a formatted string ("1.23s", "1m 3s", "2h 5m"),
# never a number. Parse tolerantly and track how much we understood.
_DURATION_UNITS = {
    "s": 1.0,
    "sec": 1.0,
    "m": 60.0,
    "min": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
}
_DURATION_TOKEN = re.compile(r"([0-9]*\.?[0-9]+)\s*([a-zA-Z]+)")


def parse_duration(raw):
    """Seconds from a readable duration string. None if nothing parsed."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    total = 0.0
    matched = False
    for value, unit in _DURATION_TOKEN.findall(str(raw)):
        factor = _DURATION_UNITS.get(unit.lower())
        if factor is None:
            continue
        try:
            total += float(value) * factor
        except ValueError:
            continue
        matched = True
    return total if matched else None


def normalize_tool_key(name):
    """Canonical form for joining a log function_name to a catalog alias.

    LOG.log already does `.replace("\\n", " ")` on the title before storing,
    so both sides must agree on whitespace collapsing and case.
    """
    if name is None:
        return ""
    text = str(name).replace("\n", " ").replace("\r", " ")
    return " ".join(text.split()).strip().lower()


def script_basename(script_path):
    """Lowercased file name from a log/catalog script path.

    Both runtimes store Windows-style paths, so splitting on os.sep alone is
    wrong when this runs on a POSIX box (tests, CI). Split on both.
    """
    if not script_path:
        return ""
    text = str(script_path).replace("\\", "/")
    return text.rsplit("/", 1)[-1].strip().lower()


def parse_records(raw_log):
    """[(datetime, record)] sorted by time, plus a count of unparseable keys.

    Unparseable keys are COUNTED, not silently dropped -- a nonzero count is a
    bug signal worth surfacing in --dry-run rather than swallowing.
    """
    records = []
    unparseable = 0
    for key, value in (raw_log or {}).items():
        try:
            stamp = datetime.datetime.strptime(str(key), LOG_KEY_FORMAT)
        except (ValueError, TypeError):
            unparseable += 1
            continue
        if not isinstance(value, dict):
            unparseable += 1
            continue
        records.append((stamp, value))
    records.sort(key=lambda pair: pair[0])
    return records, unparseable


# ------------------------------------------------------------------- windows

def month_bounds(today, offset=0):
    """(first_day, last_day) of the calendar month `offset` months back.

    offset=1 -> the last COMPLETE month, which is what a monthly recap reports.
    """
    year, month = today.year, today.month
    for _ in range(offset):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    first = datetime.date(year, month, 1)
    if month == 12:
        next_first = datetime.date(year + 1, 1, 1)
    else:
        next_first = datetime.date(year, month + 1, 1)
    return first, next_first - datetime.timedelta(days=1)


def week_bounds(today, days=7):
    return today - datetime.timedelta(days=days - 1), today


# ------------------------------------------------------------------- metrics

def _blank_window(start, end):
    return {
        "start": start,
        "end": end,
        "total_runs": 0,
        "active_days": 0,
        "runs_by_application": {},
        "runs_by_tool": {},
        "runs_by_tool_app": {},
        "basenames_by_tool": {},
        "distinct_tools": 0,
        "seconds_in_tools": 0.0,
        "seconds_by_tool": {},
        "duration_parse_coverage": 0.0,
        "busiest_day": None,
        "top_tools": [],
    }


def window_metrics(records, start, end):
    """Metrics for records whose date falls in [start, end] inclusive."""
    out = _blank_window(start, end)
    days = {}
    duration_seen = 0
    duration_parsed = 0

    for stamp, record in records:
        day = stamp.date()
        if day < start or day > end:
            continue

        out["total_runs"] += 1
        days[day] = days.get(day, 0) + 1

        app = str(record.get("application") or "Unknown")
        out["runs_by_application"][app] = out["runs_by_application"].get(app, 0) + 1

        key = normalize_tool_key(record.get("function_name"))
        if not key:
            continue
        out["runs_by_tool"][key] = out["runs_by_tool"].get(key, 0) + 1
        out["runs_by_tool_app"].setdefault(key, app)
        # Script basename is the tier-2 join key: titles get reworded between
        # releases, file paths do not.
        basename = script_basename(record.get("script_path"))
        if basename:
            out["basenames_by_tool"].setdefault(key, basename)

        duration_seen += 1
        seconds = parse_duration(record.get("duration"))
        if seconds is not None:
            duration_parsed += 1
            out["seconds_in_tools"] += seconds
            out["seconds_by_tool"][key] = out["seconds_by_tool"].get(key, 0.0) + seconds

    out["active_days"] = len(days)
    out["distinct_tools"] = len(out["runs_by_tool"])
    if duration_seen:
        out["duration_parse_coverage"] = float(duration_parsed) / duration_seen
    if days:
        out["busiest_day"] = max(days.items(), key=lambda kv: kv[1])[0]
    out["top_tools"] = sorted(
        out["runs_by_tool"].items(), key=lambda kv: (-kv[1], kv[0])
    )[:10]
    return out


def first_use_dates(records):
    """{tool_key: 'YYYY-MM-DD'} of the earliest run seen in these records."""
    out = {}
    for stamp, record in records:
        key = normalize_tool_key(record.get("function_name"))
        if not key:
            continue
        day = stamp.date().isoformat()
        if key not in out or day < out[key]:
            out[key] = day
    return out


def month_over_month(current, previous, min_combined=10):
    """{tool_key: (prev_count, now_count)} for tools with enough total volume.

    The floor keeps "your use of X tripled" off a 1 -> 3 change.
    """
    out = {}
    keys = set(current.get("runs_by_tool", {})) | set(previous.get("runs_by_tool", {}))
    for key in keys:
        now = current.get("runs_by_tool", {}).get(key, 0)
        was = previous.get("runs_by_tool", {}).get(key, 0)
        if now + was >= min_combined:
            out[key] = (was, now)
    return out


def working_day_streak(records, today=None, is_working_day=None):
    """Length of the consecutive active working-day run ending at the LAST
    ACTIVE DAY.

    Deliberately independent of `today`. Coupling the two (walking back from
    today and breaking on the first idle day) makes the streak and the idle
    gap the same measurement, so "your streak is at risk" becomes
    unexpressible: by the time the user is idle enough to warn, the streak has
    already been zeroed. Callers combine this with `working_days_since_last_run`
    to decide whether the run is still alive.

    Weekends and holidays (via `is_working_day`) never break a run -- a
    calendar-day streak resets every Saturday and the mechanic is worthless.
    """
    if is_working_day is None:
        is_working_day = lambda d: d.weekday() < 5

    active = set(stamp.date() for stamp, _record in records)
    if not active:
        return 0

    cursor = max(active)
    streak = 0
    for _ in range(2000):
        if not is_working_day(cursor):
            cursor -= datetime.timedelta(days=1)
            continue
        if cursor not in active:
            break
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


def is_streak_alive(working_days_idle, grace_days=1):
    """A run survives today being idle -- the day is not over yet."""
    if working_days_idle is None:
        return False
    return working_days_idle <= grace_days


def days_since_last_run(records, today):
    if not records:
        return None
    return (today - records[-1][0].date()).days


def working_days_since_last_run(records, today, is_working_day=None):
    """Idle span in WORKING days, which is what the streak is measured in.

    Calendar days are the wrong unit here: last run Friday, checked Tuesday is
    4 calendar days but only 2 working days. Gating "your streak is about to
    end" on calendar days would push users out of the warning window over
    every weekend -- precisely when the warning is most useful.
    """
    if not records:
        return None
    if is_working_day is None:
        is_working_day = lambda d: d.weekday() < 5
    last = records[-1][0].date()
    count = 0
    cursor = last + datetime.timedelta(days=1)
    while cursor <= today:
        if is_working_day(cursor):
            count += 1
        cursor += datetime.timedelta(days=1)
    return count


def build(raw_log, today, is_working_day=None):
    """The full metric bundle the claim engine consumes."""
    records, unparseable = parse_records(raw_log)

    month_start, month_end = month_bounds(today, offset=1)
    prev_start, prev_end = month_bounds(today, offset=2)
    week_start, week_end = week_bounds(today)

    month = window_metrics(records, month_start, month_end)
    prev_month = window_metrics(records, prev_start, prev_end)
    week = window_metrics(records, week_start, week_end)

    # Lifetime window: same shape as the month window (runs_by_tool,
    # seconds_by_tool, basenames_by_tool) so the time-saved estimate reuses the
    # identical join + baseline path for "since you started" as for the month.
    # One extra pass over records already held in memory -- the producer runs
    # off-thread under CPython, never on the Revit UI thread.
    if records:
        life = window_metrics(records, records[0][0].date(), records[-1][0].date())
    else:
        life = _blank_window(today, today)

    idle_working = working_days_since_last_run(records, today, is_working_day)
    streak = working_day_streak(records, today, is_working_day)

    return {
        "today": today,
        "unparseable_keys": unparseable,
        "total_runs_ever": len(records),
        "distinct_tools_ever": len(first_use_dates(records)),
        "first_use_dates": first_use_dates(records),
        "days_since_last_run": days_since_last_run(records, today),
        "working_days_idle": idle_working,
        "streak": streak,
        "streak_alive": is_streak_alive(idle_working),
        "month": month,
        "prev_month": prev_month,
        "week": week,
        "lifetime": life,
        "mom_delta_by_tool": month_over_month(month, prev_month),
        "month_id": "{:04d}-{:02d}".format(month_start.year, month_start.month),
        "month_label": month_start.strftime("%B"),
    }

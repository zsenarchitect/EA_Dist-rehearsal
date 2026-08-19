"""Persistent recap state: cadence stamps, claim rotation, first-seen index.

Kept separate from the log because two of these outlive it. `first_seen` in
particular MUST be persisted independently: the log is unpruned today, but
once it is compacted, "the first time you used X" becomes unanswerable from
the log alone and the claim would silently start lying.
"""

import datetime
import json
import os

import recap_env


STATE_VERSION = 1
CLAIM_HISTORY_LEN = 6
RECOMMEND_STRIKE_LIMIT = 3


def _state_name(user_name):
    return "recap_state_{}".format(user_name)


def _empty_state():
    return {
        "schema": STATE_VERSION,
        "last_weekly_week_id": None,
        "last_monthly_sent_month": None,
        "last_monthly_attempt": None,
        "last_loss_aversion": None,
        "claim_history": [],      # [{month, type, tool}], newest last
        "recommend_history": {},  # tool_key -> times recommended
        "first_seen": {},         # tool_key -> "YYYY-MM-DD"
        "asked_baseline": {},     # script_path -> "YYYY-MM-DD" the by-hand-time ask fired
        "streak": {},
    }


def load(user_name=None):
    recap_env.bootstrap()
    from EnneadTab import DATA_FILE
    user_name = user_name or recap_env.get_user_name()
    try:
        data = DATA_FILE.get_data(_state_name(user_name)) or {}
    except Exception:
        data = {}
    base = _empty_state()
    if not isinstance(data, dict):
        return base
    # Forward-compatible merge: unknown keys survive, missing keys get defaults.
    base.update(data)
    base["schema"] = STATE_VERSION
    for key in ("claim_history",):
        if not isinstance(base.get(key), list):
            base[key] = []
    for key in ("recommend_history", "first_seen", "asked_baseline", "streak"):
        if not isinstance(base.get(key), dict):
            base[key] = {}
    return base


def save(state, user_name=None):
    recap_env.bootstrap()
    from EnneadTab import DATA_FILE
    user_name = user_name or recap_env.get_user_name()
    DATA_FILE.set_data(state, _state_name(user_name))


def dry_run_path(user_name):
    """Where --dry-run dumps state it would have written, without writing it."""
    return recap_env.dump_file("recap_state_{}_dryrun.json".format(user_name))


def dump_dry_run(state, user_name):
    path = dry_run_path(user_name)
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass
    return path


# ---------------------------------------------------------------- claim rotation

def recent_claim_types(state, count=2):
    """The last `count` claim types used, newest first."""
    history = state.get("claim_history") or []
    return [entry.get("type") for entry in history[-count:]][::-1]


def record_claim(state, claim_type, tool, month_id):
    history = state.get("claim_history") or []
    history.append({"month": month_id, "type": claim_type, "tool": tool})
    state["claim_history"] = history[-CLAIM_HISTORY_LEN:]
    return state


# ------------------------------------------------------------ recommend strikes

def recommend_strikes(state, tool_key):
    return int((state.get("recommend_history") or {}).get(tool_key, 0))


def is_burned_out(state, tool_key):
    """Three strikes and a tool is never recommended to this user again.

    Re-pitching something someone has ignored three times is how the whole
    feature becomes noise.
    """
    return recommend_strikes(state, tool_key) >= RECOMMEND_STRIKE_LIMIT


def record_recommendations(state, tool_keys):
    history = state.get("recommend_history") or {}
    for key in tool_keys:
        history[key] = int(history.get(key, 0)) + 1
    state["recommend_history"] = history
    return state


# ----------------------------------------------------- by-hand-time ask dedup

def already_asked_baseline(state, script_path):
    """True once the by-hand-time ask has fired for this tool for this user.

    A tool is asked at most once per user, ever -- re-asking the same tool is
    exactly the nag that makes the whole feature feel like a survey treadmill.
    """
    return script_path in (state.get("asked_baseline") or {})


def record_baseline_asked(state, script_path, date_str):
    """Stamp a tool as asked so it is never re-asked for this user."""
    asked = state.get("asked_baseline") or {}
    asked.setdefault(script_path, date_str)
    state["asked_baseline"] = asked
    return state


# -------------------------------------------------------------- first-seen index

def update_first_seen(state, first_dates):
    """Merge {tool_key: 'YYYY-MM-DD'} keeping the EARLIEST date per tool."""
    seen = state.get("first_seen") or {}
    for key, date_str in first_dates.items():
        current = seen.get(key)
        if current is None or date_str < current:
            seen[key] = date_str
    state["first_seen"] = seen
    return state


def first_time_tools(state, window_start, window_end):
    """Tools whose first-ever use falls inside [window_start, window_end]."""
    out = []
    for key, date_str in (state.get("first_seen") or {}).items():
        try:
            seen = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if window_start <= seen <= window_end:
            out.append(key)
    return sorted(out)


# ------------------------------------------------------------------ cadence gates

def iso_week_id(date_obj):
    iso = date_obj.isocalendar()
    return "{}-W{:02d}".format(iso[0], iso[1])


def month_id(date_obj):
    return "{:04d}-{:02d}".format(date_obj.year, date_obj.month)


def weekly_due(state, today):
    return state.get("last_weekly_week_id") != iso_week_id(today)


def monthly_due(state, today):
    """Monthly is due from the 2nd onward, so the reported month is complete."""
    if today.day < 2:
        return False
    return state.get("last_monthly_sent_month") != month_id(today)


def loss_aversion_allowed(state, today, min_gap_days=14):
    """At most one loss-aversion message per `min_gap_days`.

    Repeated loss warnings stop reading as a nudge and start reading as
    nagging, which is the exact failure principle 4 exists to avoid.
    """
    last = state.get("last_loss_aversion")
    if not last:
        return True
    try:
        last_date = datetime.datetime.strptime(last, "%Y-%m-%d").date()
    except Exception:
        return True
    return (today - last_date).days >= min_gap_days

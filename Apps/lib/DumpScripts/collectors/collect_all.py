"""Run InfraWatch collectors. Single entry point for Task Scheduler.

Runs silently — no output, no popups, no console. Failures reported to
ErrorDump only.

Modes:
    python collect_all.py               # All collectors (default)
    python collect_all.py --heavy       # Drive health + machine spec (slow-changing data, run every 6h)
    python collect_all.py --events-only # Just events (run hourly for fast detection)
    python collect_all.py --journals-only # Revit journals only (weekly; independent kill switch)
    python collect_all.py --spec-only   # Just machine spec (good for login trigger)
    python collect_all.py --loop 60     # Every 60 minutes (in-process; prefer Task Scheduler)
"""

import os
import sys
import time

# Kill switch: drop a file named ".infrawatch_kill" at the EnneadTab-OS / EA_Dist
# root to disable every collector POST fleet-wide. One-file commit kills the fleet
# without needing each machine to re-enroll. Walks up from this file to find ROOT.
def _kill_switch_active():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(8):
        if os.path.basename(cur) in ("EA_Dist", "EnneadTab-OS"):
            return os.path.exists(os.path.join(cur, ".infrawatch_kill"))
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return False


def run_heavy():
    """Slow-changing telemetry. Drive utilization + hardware spec.
    Cadence: 6h is plenty — data drifts on the scale of hours."""
    import collect_drive_health
    import collect_machine_spec
    collect_drive_health.collect_once()
    collect_machine_spec.main()


def run_events_only():
    """Fast-changing failure-class data (BSODs, drive disconnects).
    Cadence: hourly so on-call sees incidents within ~1h, not ~6h."""
    import collect_events
    collect_events.main()


def run_all():
    """Everything in one pass. Each collector is independent —
    one failing doesn't block others."""
    run_heavy()
    run_events_only()


def run_spec_only():
    """Just the machine spec collector (lightweight, good for login trigger)."""
    import collect_machine_spec
    collect_machine_spec.main()


def run_journals_only():
    """Weekly Revit journal upload. Not coupled to infra kill switch."""
    import collect_revit_journal
    collect_revit_journal.main()


def _journal_kill_switch_active():
    import collect_revit_journal
    return collect_revit_journal.journal_kill_switch_active()


def main():
    if "--journals-only" in sys.argv:
        if _journal_kill_switch_active():
            return
        run_journals_only()
        return
    if _kill_switch_active():
        return
    if "--heavy" in sys.argv:
        run_heavy()
        return
    if "--events-only" in sys.argv:
        run_events_only()
        return
    if "--spec-only" in sys.argv:
        run_spec_only()
        return

    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 60
        while True:
            run_all()
            time.sleep(interval * 60)
    else:
        run_all()


if __name__ == "__main__":
    main()

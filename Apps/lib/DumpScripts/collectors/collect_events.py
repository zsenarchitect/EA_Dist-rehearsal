"""Collect system events (BSOD/crashes) and POST to InfraWatch.

Stdlib-only — no pip dependencies. Uses PowerShell to query Windows Event Log.
Designed to run silently on every EA_Dist machine (hourly or on schedule).

Hourly run also posts lightweight drive connectivity probes before BSOD scan.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_connectivity import probe_expected_drives
from infrawatch_common import post_to_infrawatch_detailed, report_error, get_machine_name


def post_drive_connectivity():
    """Lightweight hourly connectivity probe for expected office drives."""
    drives = probe_expected_drives()
    if not drives:
        return
    payload = {
        "machine_name": get_machine_name(),
        "timestamp": datetime.now().isoformat(),
        "drives": drives,
    }
    ok, detail = post_to_infrawatch_detailed("drive-health", payload)
    if not ok:
        report_error("collect_events.post_drive_connectivity",
                     "POST to drive-health failed [{} drives]: {}".format(len(drives), detail))


def get_recent_bsod_events(hours=24):
    """Query Windows Event Log for BSOD events in the last N hours."""
    events = []
    try:
        ps_cmd = (
            "$cutoff = (Get-Date).AddHours(-{hours});"
            "Get-WinEvent -FilterHashtable @{{"
            "  LogName='System';"
            "  ProviderName='Microsoft-Windows-WER-SystemErrorReporting';"
            "  Id=1001;"
            "  StartTime=$cutoff"
            "}} -ErrorAction SilentlyContinue | "
            "ForEach-Object {{"
            "  $msg = $_.Message;"
            "  if ($msg -match 'minidump|.dmp') {{"
            "    @{{"
            "      TimeCreated = $_.TimeCreated.ToString('o');"
            "      Message = $msg.Substring(0, [Math]::Min($msg.Length, 500));"
            "      EventID = $_.Id"
            "    }}"
            "  }}"
            "}} | ConvertTo-Json"
        ).format(hours=hours)

        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )

        if result.stdout.strip():
            parsed = json.loads(result.stdout)
            if isinstance(parsed, dict):
                parsed = [parsed]
            for evt in parsed:
                events.append({
                    "type": "blue_screen",
                    "occurred_at": evt.get("TimeCreated", datetime.now().isoformat()),
                    "details": {
                        "description": "Blue Screen with Crash Dump",
                        "event_id": evt.get("EventID", 1001),
                        "message": evt.get("Message", ""),
                        "user": os.environ.get("USERNAME", "Unknown"),
                    },
                })
    except Exception as e:
        report_error("collect_events.get_recent_bsod_events", str(e))

    return events


def main():
    try:
        post_drive_connectivity()

        events = get_recent_bsod_events(hours=24)
        if not events:
            return

        payload = {
            "machine_name": get_machine_name(),
            "events": events,
        }
        ok, detail = post_to_infrawatch_detailed("events", payload)
        if not ok:
            report_error("collect_events.main", "POST to events failed: {}".format(detail))
    except Exception as e:
        report_error("collect_events.main", str(e))


if __name__ == "__main__":
    main()

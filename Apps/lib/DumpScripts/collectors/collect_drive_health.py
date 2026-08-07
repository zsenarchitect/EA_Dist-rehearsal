"""Collect network drive health and POST to InfraWatch.

Stdlib-only — no pip dependencies. Uses PowerShell for drive discovery.
Designed to run silently via Task Scheduler on every EA_Dist machine.

Probes every expected drive from office_drives.json (even when Win32 omits
disconnected letters). Heavy tier adds capacity/latency for connected drives.

Usage:
    python collect_drive_health.py           # One-shot
    python collect_drive_health.py --loop 5  # Every 5 minutes
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drive_connectivity import load_office_drives_config, probe_expected_drives
from infrawatch_common import post_to_infrawatch_detailed, report_error, get_machine_name


def _wmi_drives_by_letter():
    """Win32_LogicalDisk metrics keyed by drive letter (connected only)."""
    by_letter = {}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_LogicalDisk | "
             "Select-Object DeviceID,DriveType,Size,FreeSpace,ProviderName | "
             "ConvertTo-Json"],
            capture_output=True, text=True, timeout=30
        )
        disks = json.loads(result.stdout)
        if isinstance(disks, dict):
            disks = [disks]

        for disk in disks:
            device_id = disk.get("DeviceID", "")
            if not device_id:
                continue
            letter = device_id[0].upper()
            drive_type = disk.get("DriveType", 0)
            if drive_type not in (3, 4):
                continue

            total_bytes = disk.get("Size") or 0
            free_bytes = disk.get("FreeSpace") or 0
            if total_bytes == 0:
                continue

            total_gb = round(total_bytes / (1024 ** 3), 1)
            free_gb = round(free_bytes / (1024 ** 3), 1)
            used_gb = round(total_gb - free_gb, 1)
            usage_pct = round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0
            unc_path = disk.get("ProviderName") or None
            protocol = "SMB" if drive_type == 4 else "Local"
            latency_ms = _measure_latency("{}\\".format(letter))

            by_letter[letter] = {
                "unc_path": unc_path,
                "latency_ms": latency_ms,
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "usage_pct": usage_pct,
                "protocol": protocol,
            }
    except Exception as e:
        report_error("collect_drive_health._wmi_drives_by_letter", str(e))
    return by_letter


def _measure_latency(path):
    """Measure directory listing latency in ms."""
    try:
        start = time.perf_counter()
        os.listdir(path)
        return round((time.perf_counter() - start) * 1000, 1)
    except Exception:
        return None


def get_drives():
    """Expected drives with connectivity probe; heavy metrics when connected."""
    config = load_office_drives_config()
    probed = probe_expected_drives(config)
    if not probed:
        return []

    wmi = _wmi_drives_by_letter()
    drives = []
    for row in probed:
        letter = row["letter"]
        entry = {
            "letter": letter,
            "unc_path": row.get("unc_path"),
            "connected": row["connected"],
            "probe_ms": row["probe_ms"],
            "error_class": row["error_class"],
            "protocol": row.get("protocol"),
        }
        if row["connected"] and letter in wmi:
            entry.update(wmi[letter])
            if entry.get("unc_path") is None and wmi[letter].get("unc_path"):
                entry["unc_path"] = wmi[letter]["unc_path"]
        drives.append(entry)
    return drives


def collect_once():
    """Run one collection cycle."""
    drives = get_drives()
    if not drives:
        return

    payload = {
        "machine_name": get_machine_name(),
        "timestamp": datetime.now().isoformat(),
        "drives": drives,
    }
    ok, detail = post_to_infrawatch_detailed("drive-health", payload)
    if not ok:
        report_error("collect_drive_health.collect_once",
                     "POST to drive-health failed [{} drives]: {}".format(len(drives), detail))


def main():
    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 5
        while True:
            collect_once()
            time.sleep(interval * 60)
    else:
        collect_once()


if __name__ == "__main__":
    main()

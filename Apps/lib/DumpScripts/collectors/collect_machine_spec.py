"""Collect machine hardware specs and POST to InfraWatch.

Stdlib-only — no pip dependencies. Uses PowerShell for WMI queries.
Designed to run silently on every EA_Dist machine (daily or on login).
"""

import json
import os
import platform
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infrawatch_common import post_to_infrawatch, report_error, get_machine_name, get_username


def _ps_json(command):
    """Run a PowerShell command and return parsed JSON."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(result.stdout)
    except Exception:
        return None


def collect_spec():
    """Gather full machine spec via PowerShell WMI queries."""
    spec = {
        "machine_name": get_machine_name(),
        "username": get_username(),
        "os": platform.platform(),
    }

    # CPU
    cpu = _ps_json(
        "Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,"
        "NumberOfLogicalProcessors,MaxClockSpeed | ConvertTo-Json"
    )
    if cpu:
        if isinstance(cpu, list):
            cpu = cpu[0]
        spec["cpu"] = {
            "model": cpu.get("Name"),
            "cores": cpu.get("NumberOfCores"),
            "threads": cpu.get("NumberOfLogicalProcessors"),
            "frequency": "{} MHz".format(cpu.get("MaxClockSpeed", "")),
        }

    # GPU
    gpus = _ps_json(
        "Get-CimInstance Win32_VideoController | "
        "Where-Object { $_.Name -ne 'Microsoft Basic Display Driver' } | "
        "Select-Object Name,AdapterRAM,DriverVersion,DriverDate | ConvertTo-Json"
    )
    if gpus:
        if isinstance(gpus, dict):
            gpus = [gpus]
        spec["gpu"] = []
        for g in gpus:
            ram = g.get("AdapterRAM")
            mem_str = "{:.1f} GB".format(ram / (1024**3)) if ram else "Unknown"
            spec["gpu"].append({
                "name": g.get("Name"),
                "memory": mem_str,
                "driver_version": g.get("DriverVersion"),
                "driver_date": g.get("DriverDate"),
            })

    # RAM
    mem = _ps_json(
        "Get-CimInstance Win32_OperatingSystem | "
        "Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json"
    )
    if mem:
        total_kb = mem.get("TotalVisibleMemorySize", 0)
        free_kb = mem.get("FreePhysicalMemory", 0)
        total_gb = total_kb / (1024 * 1024) if total_kb else 0
        used_pct = round(((total_kb - free_kb) / total_kb) * 100, 1) if total_kb else 0
        spec["ram"] = {
            "total": "{:.1f} GB".format(total_gb),
            "used_percent": "{}%".format(used_pct),
        }

    # Primary disk
    disks = _ps_json(
        "Get-CimInstance Win32_DiskDrive | Select-Object Model,MediaType,Size | ConvertTo-Json"
    )
    if disks:
        if isinstance(disks, dict):
            disks = [disks]
        spec["storage"] = []
        for d in disks:
            size = d.get("Size")
            spec["storage"].append({
                "model": d.get("Model"),
                "media_type": d.get("MediaType"),
                "total": "{:.1f} GB".format(size / (1024**3)) if size else "Unknown",
            })

    # System age (OS install date)
    age = _ps_json(
        "Get-CimInstance Win32_OperatingSystem | Select-Object InstallDate | ConvertTo-Json"
    )
    if age and age.get("InstallDate"):
        try:
            install_str = age["InstallDate"].split(".")[0] if isinstance(age["InstallDate"], str) else ""
            if install_str:
                install_date = datetime.strptime(install_str, "%Y%m%d%H%M%S")
                spec["system_age_days"] = (datetime.now() - install_date).days
        except Exception:
            pass

    return spec


def main():
    try:
        spec = collect_spec()
        ok = post_to_infrawatch("machine-spec", spec)
        if not ok:
            report_error("collect_machine_spec.main", "POST to machine-spec failed")
    except Exception as e:
        report_error("collect_machine_spec.main", str(e))


if __name__ == "__main__":
    main()

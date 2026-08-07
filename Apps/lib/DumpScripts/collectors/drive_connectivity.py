"""Fleet drive connectivity probe for expected office drive letters.

Loads office_drives.json from the EA_Dist / EnneadTab-OS root (or collectors
fallback). Probes every expected letter with a short timeout so disconnected
network drives surface as timeout/unavailable instead of being omitted.
"""

import json
import os
import threading
import time

_DEFAULT_CONFIG = {
    "expected": [],
    "probe_timeout_sec": 5,
}


def _ecosystem_roots():
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    roots = []
    for _ in range(10):
        if os.path.basename(cur) in ("EA_Dist", "EnneadTab-OS"):
            roots.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return roots


def _config_paths():
    paths = []
    for root in _ecosystem_roots():
        paths.append(os.path.join(root, "office_drives.json"))
    paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "office_drives.json"))
    return paths


def load_office_drives_config():
    for path in _config_paths():
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return dict(_DEFAULT_CONFIG)


def _classify_os_error(err):
    if err is None:
        return "unavailable"
    winerr = getattr(err, "winerror", None)
    if winerr == 2:
        return "not_mapped"
    if winerr == 5:
        return "access_denied"
    if winerr in (53, 67, 1219, 1326):
        return "unavailable"
    msg = str(err).lower()
    if "access is denied" in msg:
        return "access_denied"
    if "cannot find" in msg or "system cannot find" in msg:
        return "not_mapped"
    return "unavailable"


def _probe_listdir(path, timeout_sec):
    """Return (connected, probe_ms, error_class)."""
    start = time.perf_counter()
    result = {"ok": False, "error": None}

    def worker():
        try:
            os.listdir(path)
            result["ok"] = True
        except OSError as exc:
            result["error"] = exc

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout_sec)
    probe_ms = round((time.perf_counter() - start) * 1000, 1)

    if thread.is_alive():
        return False, probe_ms, "timeout"
    if result["ok"]:
        return True, probe_ms, "ok"
    return False, probe_ms, _classify_os_error(result["error"])


def probe_expected_drives(config=None):
    """Probe every expected drive letter from office_drives.json."""
    cfg = config or load_office_drives_config()
    timeout_sec = int(cfg.get("probe_timeout_sec") or 5)
    expected = cfg.get("expected") or []
    rows = []

    for entry in expected:
        letter = str(entry.get("letter", "")).strip().upper()[:1]
        if not letter:
            continue
        path = "{}:\\".format(letter)
        connected, probe_ms, error_class = _probe_listdir(path, timeout_sec)
        rows.append({
            "letter": letter,
            "unc_path": entry.get("unc"),
            "connected": connected,
            "probe_ms": probe_ms,
            "error_class": error_class,
            "protocol": "SMB",
        })
    return rows

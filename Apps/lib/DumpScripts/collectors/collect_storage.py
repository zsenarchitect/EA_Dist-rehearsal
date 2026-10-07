"""Collect storage folder snapshots and POST to InfraWatch.

Stdlib-only — no pip dependencies.
Cross-platform: runs seamlessly on macOS, Windows, and Linux.
Dynamically resolves repository roots, configuration files, and target paths
without hardcoded local filesystem assumptions.

Designed to run weekly on designated reporter machines (3-reporter pool).
Walks storage_watchlist.json, collects folder sizes/latencies, and posts
partial results (reporting any unavailable shares in shares_failed[]).

Usage:
    python collect_storage.py              # Live run (gated on reporter pool)
    python collect_storage.py --dry-run    # Preview snapshot without POSTing
    python collect_storage.py --force-run  # Run even if not in reporter pool
    python collect_storage.py --verbose    # Output detailed per-folder walk progress
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infrawatch_common import (
    get_machine_name,
    post_to_infrawatch_detailed,
    report_error,
)

CONFIG_FILENAME = "storage_watchlist.json"


def _ecosystem_roots():
    """Walk up from this file looking for EA_Dist or EnneadTab-OS roots dynamically."""
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


def get_repo_root():
    """Return primary detected repository root, or fall back relative to __file__."""
    roots = _ecosystem_roots()
    if roots:
        return roots[0]
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "..", ".."))


def _potential_config_paths():
    """Search candidate locations for storage_watchlist.json across platforms."""
    candidates = []
    env_path = os.environ.get("STORAGE_WATCHLIST_PATH")
    if env_path:
        candidates.append(env_path)

    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, CONFIG_FILENAME))

    for root in _ecosystem_roots():
        candidates.append(os.path.join(root, CONFIG_FILENAME))
        candidates.append(os.path.join(root, "Apps", "lib", "DumpScripts", "collectors", CONFIG_FILENAME))

    # User home directory fallback (~/.enneadtab/storage_watchlist.json)
    home = os.path.expanduser("~")
    candidates.append(os.path.join(home, ".enneadtab", CONFIG_FILENAME))

    return candidates


def load_config(config_path=None):
    if config_path:
        search_paths = [config_path]
    else:
        search_paths = _potential_config_paths()

    for path in search_paths:
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                report_error("collect_storage.load_config", f"Error reading {path}: {e}")

    return {"reporters": [], "folders": []}


def is_designated_reporter(config):
    # Environment override for ad-hoc or automated test runs
    if os.environ.get("INFRAWATCH_REPORTER") == "1" or os.environ.get("INFRAWATCH_STORAGE_REPORTER") == "1":
        return True

    env_reporters = os.environ.get("STORAGE_REPORTERS")
    reporters = config.get("reporters", [])
    if env_reporters:
        reporters = [r.strip() for r in env_reporters.split(",") if r.strip()]

    if not reporters or "*" in reporters:
        return True

    current = get_machine_name().upper()
    current_short = current.split(".")[0]

    for r in reporters:
        r_clean = r.upper().split(".")[0]
        if current == r.upper() or current_short == r_clean:
            return True
    return False


def resolve_folder_path(item, repo_root=None):
    r"""Resolve a watchlist item to a platform-native, dynamically expanded path.

    Supports:
      - Platform-specific overrides: path_mac, path_win, path_linux
      - Candidate lists: [path1, path2] trying each until one exists
      - Path tokens: {REPO_ROOT}, {ROOT}, {HOME}
      - Environment variables: $VAR, %VAR%, ~
      - Automatic translation of UNC (\\server\share) and Windows drive letters on macOS (/Volumes/share)
    """
    if repo_root is None:
        repo_root = get_repo_root()

    home = os.path.expanduser("~")

    # 1. Select candidate string(s) based on platform
    candidates = []
    if sys.platform == "darwin":
        val = item.get("path_mac") or item.get("mac_path")
        if val:
            candidates.extend(val if isinstance(val, list) else [val])
    elif sys.platform == "win32":
        val = item.get("path_win") or item.get("win_path")
        if val:
            candidates.extend(val if isinstance(val, list) else [val])
    elif sys.platform.startswith("linux"):
        val = item.get("path_linux") or item.get("linux_path")
        if val:
            candidates.extend(val if isinstance(val, list) else [val])

    generic = item.get("folder_path") or item.get("path")
    if generic:
        candidates.extend(generic if isinstance(generic, list) else [generic])

    if not candidates:
        return None

    def expand_str(s):
        s = s.replace("{REPO_ROOT}", repo_root).replace("{ROOT}", repo_root).replace("{HOME}", home)
        s = os.path.expanduser(os.path.expandvars(s))
        return s

    # 2. Test candidate paths in order; return first that exists
    for cand in candidates:
        expanded = expand_str(cand)
        norm = os.path.normpath(expanded)
        if os.path.exists(norm):
            return norm

        # On macOS, check if Windows UNC or drive letter maps to a mounted volume
        if sys.platform == "darwin":
            # UNC: \\server\share\path or //server/share/path -> /Volumes/share/path
            unc_match = re.match(r"^[\\/]{2}[^\\/]+[\\/]([^\\/]+)(.*)$", expanded)
            if unc_match:
                share_name, subpath = unc_match.group(1), unc_match.group(2).replace("\\", "/")
                vol_path = os.path.normpath(f"/Volumes/{share_name}{subpath}")
                if os.path.exists(vol_path):
                    return vol_path

            # Drive letter: L:\path -> /Volumes/L/path or /Volumes/<alias>
            drive_match = re.match(r"^([A-Za-z]):[\\/](.*)$", expanded)
            if drive_match:
                drive_letter, subpath = drive_match.group(1).upper(), drive_match.group(2).replace("\\", "/")
                vol_path = os.path.normpath(f"/Volumes/{drive_letter}/{subpath}")
                if os.path.exists(vol_path):
                    return vol_path

    # Fallback to the first candidate normalized
    return os.path.normpath(expand_str(candidates[0]))


def _calc_depth(p):
    """Universal path segment count that works consistently across Mac, Linux, and Windows."""
    parts = [seg for seg in p.replace("\\", "/").strip("/").split("/") if seg and not re.match(r"^[A-Za-z]:$", seg)]
    return len(parts)


def measure_folder(folder_path, max_depth=5, timeout_sec=60):
    """Measure folder size, file count, and listing latency.
    Returns (ok, result_dict_or_error_str).
    """
    start_time = time.perf_counter()
    try:
        if not os.path.exists(folder_path):
            return False, f"path does not exist or network path unavailable ({folder_path})"
        if not os.path.isdir(folder_path):
            return False, f"path is not a directory ({folder_path})"

        # Latency check: time to list top-level
        list_start = time.perf_counter()
        os.listdir(folder_path)
        latency_ms = round((time.perf_counter() - list_start) * 1000, 1)

        total_bytes = 0
        file_count = 0
        dir_count = 0
        deadline = start_time + timeout_sec
        timed_out = False

        base_depth = _calc_depth(folder_path)

        for root, dirs, files in os.walk(folder_path):
            if time.perf_counter() > deadline:
                timed_out = True
                break

            current_depth = _calc_depth(root) - base_depth
            if current_depth >= max_depth:
                dirs.clear()

            dir_count += len(dirs)
            for f in files:
                file_count += 1
                fp = os.path.join(root, f)
                try:
                    total_bytes += os.path.getsize(fp)
                except (OSError, IOError):
                    pass

        total_gb = round(total_bytes / (1024 ** 3), 2)
        total_time_ms = round((time.perf_counter() - start_time) * 1000, 1)

        data = {
            "total_bytes": total_bytes,
            "total_gb": total_gb,
            "file_count": file_count,
            "dir_count": dir_count,
            "latency_ms": latency_ms,
            "walk_time_ms": total_time_ms,
            "timed_out": timed_out,
        }
        return True, data
    except Exception as e:
        return False, str(e)


def collect_snapshots(config, verbose=False):
    folders = config.get("folders", [])
    snapshots = []
    shares_failed = []
    repo_root = get_repo_root()

    for item in folders:
        key = item.get("canonical_key")
        resolved_path = resolve_folder_path(item, repo_root=repo_root)

        if not resolved_path:
            continue
        if not key:
            key = resolved_path

        if verbose:
            print(f"[collect_storage] Probing {key} -> {resolved_path}...", file=sys.stderr)

        ok, result = measure_folder(resolved_path)
        if ok:
            record = {
                "canonical_key": key,
                "folder_path": resolved_path,
                "status": "online",
                **result,
            }
            snapshots.append(record)
            if verbose:
                print(f"[collect_storage]   -> {result["total_gb"]} GB, {result["file_count"]} files", file=sys.stderr)
        else:
            fail_record = {
                "canonical_key": key,
                "folder_path": resolved_path,
                "status": "unavailable",
                "error": result,
            }
            shares_failed.append(fail_record)
            if verbose:
                print(f"[collect_storage]   -> FAILED: {result}", file=sys.stderr)

    return snapshots, shares_failed


def build_payload(snapshots, shares_failed):
    return {
        "machine_name": get_machine_name(),
        "platform": sys.platform,
        "repo_root": get_repo_root(),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "collector_version": "1.1.0",
        "snapshots": snapshots,
        "shares_failed": shares_failed,
        "total_shares_monitored": len(snapshots) + len(shares_failed),
        "successful_shares": len(snapshots),
        "failed_shares": len(shares_failed),
    }


def main():
    parser = argparse.ArgumentParser(description="InfraWatch Storage Snapshot Collector")
    parser.add_argument("--dry-run", action="store_true", help="Print payload and do not POST")
    parser.add_argument("--force-run", action="store_true", help="Bypass reporter pool check")
    parser.add_argument("--verbose", action="store_true", help="Verbose progress output")
    parser.add_argument("--config", type=str, default=None, help="Path to custom watchlist config")
    args, _ = parser.parse_known_args()

    config = load_config(args.config)

    if not args.force_run and not is_designated_reporter(config):
        if args.verbose:
            print(f"[collect_storage] Machine \"{get_machine_name()}\" is not in designated reporter pool. Skipping.", file=sys.stderr)
        return 0

    try:
        snapshots, shares_failed = collect_snapshots(config, verbose=args.verbose)
        payload = build_payload(snapshots, shares_failed)

        if args.dry_run:
            print(json.dumps(payload, indent=2))
            return 0

        ok, detail = post_to_infrawatch_detailed("storage/snapshot", payload)
        if not ok:
            print(f"[collect_storage] POST failed: {detail}", file=sys.stderr)
            report_error("collect_storage.post", detail)
            return 1

        if args.verbose:
            print(f"[collect_storage] Successfully posted {len(snapshots)} snapshots ({len(shares_failed)} failed shares).", file=sys.stderr)
        return 0
    except Exception as e:
        report_error("collect_storage.main", str(e))
        print(f"[collect_storage] Unhandled error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

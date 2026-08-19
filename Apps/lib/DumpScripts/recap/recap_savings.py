"""Estimate time SAVED from a curated per-tool manual-effort baseline.

Time SPENT is measured -- LOG stores each tool's runtime -- and recap_stats
deliberately refuses to fabricate time SAVED because nothing in the log supports
it. This module makes the estimate HONEST by binding it to the same discipline
the rest of the recap already lives by, plus two gates that exist ONLY because
the multiplier here is authored rather than measured:

  * A tool with no curated baseline contributes NOTHING. No imputation, ever.
  * The magnitude is authored, so it is always rendered as an estimate, never as
    a measured superlative, and it is gated on top of the usual volume floors by
    a floor on the number of distinct baselined tools and a cap on any single
    tool's share of the total (both enforced in the claim builder).
  * Confidence is graded. `low`-confidence baselines feed the dry-run diagnostic
    but are excluded from the number a claim would ever surface (min_rank=2).

net-of-runtime is a CONSERVATIVE HEURISTIC, not a rigor guarantee. It subtracts
the machine's measured wall-time from the authored hand-time, which mixes units
(a 30-min unattended render costs the user ~0 min of their own, not 30). It only
ever biases the estimate DOWN, which is the safe direction, and nothing more is
claimed for it. It is applied per tool, and only when that tool actually has
trustworthy parsed runtime -- a tool absent from seconds_by_script gets no
invented runtime subtracted.

Pure functions over plain dicts: no EnneadTab import, no clock, no filesystem
except load_baselines, so every number is testable against a synthetic log and a
synthetic baseline file.
"""

import json
import os


# Ordinal rank so a claim can demand a minimum confidence. Authored numbers are
# never `high` until backed by real timings; the seed file is low/med only.
CONFIDENCE_RANK = {"high": 3, "med": 2, "medium": 2, "low": 1}

# Minimum distinct user responses before a fleet median may be used. Below this a
# tool falls back to the curated seed. A quality floor, NOT an abuse control --
# forged responses that clear it are defeated on the ingest side (a server-side
# bucket-midpoint whitelist), never here.
FLEET_N_MIN = 5

FLEET_FILE = "fleet_time_baselines.json"


def _coerce_manual_seconds(entry):
    """(seconds, None) if entry carries a usable manual_seconds, else (None, reason).

    A valid-JSON entry with a missing / non-numeric / non-positive manual_seconds
    is exactly what a file-level 'bad file -> {}' guard does NOT catch, and an
    unchecked bad value KeyErrors / TypeErrors inside estimate_saved -- so both
    the seed and the fleet loader run this same check.
    """
    if not isinstance(entry, dict):
        return None, "entry is not an object"
    try:
        seconds = float(entry.get("manual_seconds"))
    except (TypeError, ValueError):
        return None, "manual_seconds is not a number"
    if seconds <= 0:
        return None, "manual_seconds <= 0"
    return seconds, None


def load_baselines(path=None):
    """(baselines, rejected) -- both {script_path: ...}.

    A missing or unparseable FILE yields ({}, {}) so the whole feature is simply
    absent rather than fatal. A malformed ENTRY (valid JSON, but manual_seconds
    missing / non-numeric / <= 0) is skipped and recorded in `rejected` -- a
    valid-JSON bad entry is exactly what "missing file -> {}" does NOT catch, and
    a silent skip would hide a typo'd baseline forever. Keys starting with "_"
    are treated as file-level comments and ignored.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "time_baselines.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}

    baselines = {}
    rejected = {}
    for script, entry in raw.items():
        if str(script).startswith("_"):
            continue
        seconds, reason = _coerce_manual_seconds(entry)
        if seconds is None:
            rejected[script] = reason
            continue
        confidence = str(entry.get("confidence") or "low").strip().lower()
        if confidence not in CONFIDENCE_RANK:
            confidence = "low"
        baselines[script] = {
            "manual_seconds": seconds,
            "basis": str(entry.get("basis") or "").strip(),
            "confidence": confidence,
        }
    return baselines, rejected


def load_fleet_baselines(path=None):
    """(fleet, rejected) -- fleet[script] = {manual_seconds, n, basis}.

    The fleet-aggregated median of user-reported by-hand times, produced by the
    InfraWatch aggregation job and distributed as a JSON file (read exactly like
    the curated seed and the knowledge files -- the producer makes no HTTP call).
    Same file-level resilience (missing/bad file -> {}) AND the same per-entry
    validation as load_baselines, because a valid-JSON bad median would otherwise
    crash the unwrapped estimate_saved. `n` (response count) drives the N_MIN gate.
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), FLEET_FILE)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        return {}, {}
    if not isinstance(raw, dict):
        return {}, {}

    fleet = {}
    rejected = {}
    for script, entry in raw.items():
        if str(script).startswith("_"):
            continue
        seconds, reason = _coerce_manual_seconds(entry)
        if seconds is None:
            rejected[script] = reason
            continue
        try:
            n = int(entry.get("n"))
        except (TypeError, ValueError):
            n = 0
        if n < 0:
            n = 0
        fleet[script] = {
            "manual_seconds": seconds,
            "n": n,
            "basis": str(entry.get("basis") or "").strip(),
        }
    return fleet, rejected


def merge_baselines(seed, fleet, n_min=FLEET_N_MIN):
    """The authoritative baseline dict estimate_saved consumes.

    Precedence per script_path: a fleet median WITH quorum (n >= n_min), graded
    'med' (first-party + real N, never 'high' without stopwatch timings); else the
    curated seed entry; else the key is absent so estimate_saved contributes 0.
    KeyError-safe for seed-only and fleet-only keys -- with an empty fleet this is
    byte-identical to the seed dict, which is what keeps step 1 inert until fleet
    data exists.
    """
    seed = seed or {}
    fleet = fleet or {}
    merged = {}
    for script in set(seed) | set(fleet):
        entry = fleet.get(script)
        if entry is not None and entry.get("n", 0) >= n_min:
            merged[script] = {
                "manual_seconds": entry["manual_seconds"],
                "confidence": "med",
                "basis": entry.get("basis") or "fleet median (n={})".format(
                    entry.get("n", 0)),
            }
        elif script in seed:
            merged[script] = seed[script]
    return merged


def unresolved_baseline_keys(baselines, catalog):
    """Baseline script_paths that do not resolve to a catalog tool.

    Full-path keys are backslash- and case-sensitive, so a transcription slip is
    a SILENT miss (the tool just contributes 0). Surfacing these in the dry run
    and asserting them empty in a test is the backstop against that.
    """
    known = set((catalog or {}).get("tools", {}).keys())
    return [script for script in baselines if script not in known]


def estimate_saved(joined_runs, seconds_by_script, baselines,
                   window_total_runs, duration_coverage_ok=True, min_rank=1):
    """Estimated seconds saved over one usage window.

    joined_runs       : {script_path: run_count}          (from join_usage)
    seconds_by_script : {script_path: total_runtime_secs} (from join_usage)
    baselines         : {script_path: {...}}              (from load_baselines)
    window_total_runs : total runs in the window INCLUDING catalog-unmatched
                        ones -- the honest denominator for baseline_coverage, so
                        an under-matched join cannot inflate the coverage read.
    min_rank          : drop baselines below this confidence rank. The claim
                        path passes 2 (med+); the dry-run diagnostic passes 1.

    Returns a dict; seconds are floored at 0 per tool (a tool whose observed
    runtime exceeds its authored hand-time nets to 0 and drops out).
    """
    per_tool = {}
    runs_by_tool = {}
    assumed_by_tool = {}

    for script, runs in (joined_runs or {}).items():
        if runs <= 0:
            continue
        entry = baselines.get(script)
        if not entry:
            continue
        if CONFIDENCE_RANK.get(entry["confidence"], 1) < min_rank:
            continue

        manual = entry["manual_seconds"]
        # Net out observed runtime PER TOOL, and only when THIS tool has
        # trustworthy parsed runtime. The window-wide coverage gate is necessary
        # but not sufficient: a single tool can be 100% unparseable while the
        # window sits at 0.9, so absence from seconds_by_script means "no usable
        # runtime" -> do not invent one, fall back to the authored hand-time.
        observed_total = (seconds_by_script or {}).get(script)
        if duration_coverage_ok and observed_total is not None:
            observed_per_run = observed_total / runs
        else:
            observed_per_run = 0.0

        net_per_run = manual - observed_per_run
        if net_per_run <= 0:
            continue

        per_tool[script] = net_per_run * runs
        runs_by_tool[script] = runs
        assumed_by_tool[script] = manual

    seconds_saved = sum(per_tool.values())
    covered_runs = sum(runs_by_tool.values())
    total = int(window_total_runs or 0)

    contributors = []
    for script, seconds in sorted(per_tool.items(), key=lambda kv: -kv[1]):
        contributors.append({
            "script": script,
            "seconds": seconds,
            "runs": runs_by_tool[script],
            "assumed_seconds": assumed_by_tool[script],
        })

    max_share = (max(per_tool.values()) / seconds_saved) if seconds_saved > 0 else 0.0

    return {
        "seconds_saved": seconds_saved,
        "covered_runs": covered_runs,
        "total_runs": total,
        "baseline_coverage": (float(covered_runs) / total) if total else 0.0,
        "distinct_tools": len(per_tool),
        "contributors": contributors,
        "max_share": max_share,
    }

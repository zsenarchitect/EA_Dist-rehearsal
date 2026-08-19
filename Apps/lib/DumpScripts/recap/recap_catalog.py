"""Tool catalog: join usage records to known buttons, then recommend unused ones.

The join is the single most credibility-critical piece of the recap. If it
under-matches, the recap recommends tools the user demonstrably already uses --
which is the fastest way to make the whole feature look automated and wrong.

Three tiers, in order:
  1. normalized alias   -- sound even for multi-alias scripts, because LOG.log
                           records max(aliases, key=len) and the catalog
                           registers EVERY alias as a key.
  2. script basename    -- catches tools whose __title__ was reworded between
                           releases. Paths are the more stable identity.
  3. _unknown bucket    -- counted, never recommended, never used in a claim.
"""

import json
import os

import recap_stats


REVIT = "Revit"
RHINO = "Rhino"

_KNOWLEDGE_FILES = {
    REVIT: os.path.join("_revit", "knowledge_revit_database.sexyDuck"),
    RHINO: os.path.join("_rhino", "knowledge_rhino_database.sexyDuck"),
}

# Mirrors DOCUMENTATION.sanitize: archive and tailor entries are not real
# fleet-wide tools and must never be recommended.
_EXCLUDED_PATH_MARKERS = ("archive", "tailor")


def _apps_folder():
    here = os.path.dirname(os.path.abspath(__file__))
    # .../Apps/lib/DumpScripts/recap -> .../Apps
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def load_knowledge(app):
    """Raw knowledge dict for one app, or {} when unavailable.

    Reads the committed .sexyDuck directly rather than going through
    DOCUMENTATION.get_revit_knowledge(): ENVIRONMENT builds those paths with a
    hardcoded backslash, so the library call cannot resolve off Windows. The
    on-disk file is identical, and reading it keeps this module testable.
    """
    rel = _KNOWLEDGE_FILES.get(app)
    if not rel:
        return {}
    path = os.path.join(_apps_folder(), rel)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _aliases_of(entry):
    """Every alias an entry registers, as a list of strings."""
    alias = entry.get("alias")
    if isinstance(alias, (list, tuple)):
        return [str(item) for item in alias if item]
    if alias:
        return [str(alias)]
    return []


def build_catalog(apps=(REVIT, RHINO)):
    """{script_path: entry} plus alias/basename lookup maps.

    Keyed by script path -- one identity per tool, however many aliases it
    declares. This is what makes the multi-alias case safe.
    """
    tools = {}
    by_alias = {}
    by_basename = {}

    for app in apps:
        for script_path, entry in load_knowledge(app).items():
            if not isinstance(entry, dict):
                continue
            lowered = str(script_path).lower()
            if any(marker in lowered for marker in _EXCLUDED_PATH_MARKERS):
                continue

            aliases = _aliases_of(entry)
            record = {
                "script": script_path,
                "app": app,
                # Display name: the longest alias, matching what LOG.log records
                # (it stores max(aliases, key=len) when a script declares several).
                "alias": max(aliases, key=len) if aliases else script_path,
                "aliases": aliases,
                "doc": (entry.get("doc") or "").strip(),
                "tab": entry.get("tab") or "",
                "icon": entry.get("icon") or "",
                "is_popular": bool(entry.get("is_popular")),
            }
            tools[script_path] = record

            for alias in record["aliases"]:
                by_alias.setdefault(recap_stats.normalize_tool_key(alias), script_path)
            basename = recap_stats.script_basename(script_path)
            if basename:
                by_basename.setdefault(basename, script_path)

    return {"tools": tools, "by_alias": by_alias, "by_basename": by_basename}


# ----------------------------------------------------------------------- join

def _resolve_script(catalog, key, basename):
    """A normalized log key -> catalog script_path, via alias then basename."""
    script_path = catalog["by_alias"].get(key)
    if script_path is None and basename:
        script_path = catalog["by_basename"].get(basename)
    return script_path


def join_usage(catalog, runs_by_tool, basenames_by_tool=None, seconds_by_tool=None):
    """Map normalized log keys onto catalog script paths.

    Returns {"runs": {script_path: count},
             "seconds_by_script": {script_path: seconds},
             "unknown": {key: count}, "coverage": float}. Coverage below ~0.9
    means the join has rotted (usually a knowledge file lagging the log by a
    release) and comparative claims should be suppressed rather than computed on
    a bad denominator.

    `seconds_by_tool` (from recap_stats, keyed by NORMALIZED LOG ALIAS) is folded
    into script space here -- summing across a multi-alias tool's aliases the same
    way run counts are -- so recap_savings can pair runtime against a
    script_path-keyed baseline. Without this fold the two live in different key
    spaces and every runtime lookup silently misses.
    """
    basenames_by_tool = basenames_by_tool or {}
    runs = {}
    seconds_by_script = {}
    unknown = {}
    matched = 0
    total = 0

    for key, count in (runs_by_tool or {}).items():
        total += count
        script_path = _resolve_script(catalog, key, basenames_by_tool.get(key))
        if script_path is None:
            unknown[key] = unknown.get(key, 0) + count
            continue
        runs[script_path] = runs.get(script_path, 0) + count
        matched += count

    for key, seconds in (seconds_by_tool or {}).items():
        script_path = _resolve_script(catalog, key, basenames_by_tool.get(key))
        if script_path is None:
            continue
        seconds_by_script[script_path] = seconds_by_script.get(script_path, 0.0) + seconds

    coverage = (float(matched) / total) if total else 1.0
    return {"runs": runs, "seconds_by_script": seconds_by_script,
            "unknown": unknown, "coverage": coverage}


# ------------------------------------------------------------ recommendations

def _tab_affinity(catalog, used_scripts, tool):
    """Share of the user's runs that fall in this tool's tab.

    Recommending a Sheet tool to someone who lives in the Sheet panel
    converts; recommending a Rhino block tool to a Revit documenter does not.
    """
    tab = tool.get("tab")
    if not tab:
        return 0.0
    total = sum(used_scripts.values())
    if not total:
        return 0.0
    same = 0
    for script_path, count in used_scripts.items():
        entry = catalog["tools"].get(script_path)
        if entry and entry.get("tab") == tab:
            same += count
    return float(same) / total


def recommend(catalog, used_scripts, active_apps, state=None,
              team_adoption=None, limit=3, recently_used=None):
    """Rank never-used tools. Returns up to `limit` catalog entries.

    Weights follow the plan; team_adoption is absent until the peer phase, in
    which case the remaining terms are renormalized so the score stays on the
    same scale rather than silently shrinking.
    """
    from recap_state import is_burned_out

    team_adoption = team_adoption or {}
    recently_used = set(recently_used or used_scripts.keys())
    has_team = bool(team_adoption)

    if has_team:
        w_team, w_pop, w_tab, w_fresh = 0.45, 0.25, 0.20, 0.10
    else:
        # Renormalized 0.25/0.20/0.10 -> sums to 1.0
        w_team, w_pop, w_tab, w_fresh = 0.0, 0.455, 0.364, 0.181

    scored = []
    for script_path, tool in catalog["tools"].items():
        # Hard filter: never recommend something the user has used.
        if script_path in recently_used:
            continue
        # Never recommend into an app the user does not touch.
        if active_apps and tool.get("app") not in active_apps:
            continue
        # A tool ignored three times is dropped permanently for this user.
        if state is not None and is_burned_out(state, script_path):
            continue
        if not tool.get("doc"):
            continue

        strikes = 0
        if state is not None:
            strikes = (state.get("recommend_history") or {}).get(script_path, 0)
        freshness = max(0.0, 1.0 - (0.34 * strikes))

        score = (
            w_team * float(team_adoption.get(script_path, 0.0))
            + w_pop * (1.0 if tool.get("is_popular") else 0.0)
            + w_tab * _tab_affinity(catalog, used_scripts, tool)
            + w_fresh * freshness
        )
        scored.append((score, script_path, tool))

    scored.sort(key=lambda item: (-item[0], item[1]))

    # Diversity pass: at most one pick per tab on the first sweep. Three tools
    # from the same panel reads as one suggestion repeated, and tab_affinity
    # actively pushes toward that clustering. Backfill from the remainder if
    # the spread cannot be filled.
    chosen = []
    used_tabs = set()
    for score, script_path, tool in scored:
        if len(chosen) >= limit:
            break
        tab = tool.get("tab") or ""
        if tab in used_tabs:
            continue
        used_tabs.add(tab)
        chosen.append((score, script_path, tool))

    if len(chosen) < limit:
        already = {item[1] for item in chosen}
        for candidate in scored:
            if len(chosen) >= limit:
                break
            if candidate[1] not in already:
                chosen.append(candidate)

    return [
        dict(tool, script=script_path, score=round(score, 4))
        for score, script_path, tool in chosen[:limit]
    ]


def first_line_of_doc(doc, max_chars=160):
    """One-line summary for the recap. Docs are multi-paragraph in the catalog."""
    if not doc:
        return ""
    line = str(doc).strip().split("\n")[0].strip()
    if len(line) > max_chars:
        # ASCII only: this string is written into the pending-digest JSON that
        # IronPython 2.7 reads back, and non-ASCII there is a decode hazard.
        line = line[: max_chars - 3].rstrip() + "..."
    return line

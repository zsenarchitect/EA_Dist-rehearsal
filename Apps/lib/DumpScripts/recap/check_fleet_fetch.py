"""Tests for recap_fleet_fetch -- the fleet-baseline HTTP refresh (producer side).

Run: python check_fleet_fetch.py   (CPython 3; no EnneadTab, no network)

The whole point of this module is fail-soft: a network hiccup must never crash
the recap and must never destroy a previously-good file. These tests fake urlopen
so every failure branch is exercised offline, then round-trip the written file
through the real recap_savings.load_fleet_baselines reader to prove the two agree
on schema.
"""

import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import recap_fleet_fetch
import recap_savings


_FAILURES = []


def check(label, condition):
    mark = "ok  " if condition else "FAIL"
    if not condition:
        _FAILURES.append(label)
    print("  {} {}".format(mark, label))


class _FakeResponse(object):
    def __init__(self, body, code=200):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self._code = code

    def getcode(self):
        return self._code

    def read(self):
        return self._body


def _patch_urlopen(func):
    """Swap recap_fleet_fetch.urlopen for the duration of a call. Returns a restorer."""
    original = recap_fleet_fetch.urlopen
    recap_fleet_fetch.urlopen = func
    return lambda: setattr(recap_fleet_fetch, "urlopen", original)


def _tmp_dest():
    fd, path = tempfile.mkstemp(suffix=".json", prefix="fleet_")
    os.close(fd)
    os.remove(path)          # we want the NAME, not a pre-existing empty file
    return path


# ---------------------------------------------------------------- happy path

def test_success_writes_and_roundtrips():
    print("test_success_writes_and_roundtrips")
    dest = _tmp_dest()
    body = {
        "_generated_at": "2026-08-12T00:00:00Z",
        "_n_min": 5,
        "_tool_count": 2,
        "C:\\a\\Family RePath.pushbutton\\x.py": {"manual_seconds": 14400, "n": 7},
        "C:\\a\\Merge Family.pushbutton\\y.py": {"manual_seconds": 600, "n": 5},
    }
    restore = _patch_urlopen(lambda req, timeout=None: _FakeResponse(json.dumps(body)))
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok true", status["ok"] is True)
    check("written true", status["written"] is True)
    check("tool_count counts only non-underscore keys (2)", status["tool_count"] == 2)
    check("file exists on disk", os.path.exists(dest))

    # The reader and writer must agree: load exactly what we wrote.
    fleet, rejected = recap_savings.load_fleet_baselines(dest)
    check("reader sees 2 tools", len(fleet) == 2)
    check("reader dropped no entries", rejected == {})
    key = "C:\\a\\Family RePath.pushbutton\\x.py"
    check("reader preserved manual_seconds", fleet.get(key, {}).get("manual_seconds") == 14400.0)
    check("reader preserved n", fleet.get(key, {}).get("n") == 7)

    # And the merge picks fleet (n>=5) over a seed value, graded 'med'.
    seed = {key: {"manual_seconds": 60.0, "confidence": "high", "basis": "seed"}}
    merged = recap_savings.merge_baselines(seed, fleet)
    check("merge prefers fleet quorum over seed", merged[key]["manual_seconds"] == 14400.0)
    check("fleet-sourced entry graded med", merged[key]["confidence"] == "med")
    os.remove(dest)


def test_metadata_only_body_is_valid_and_inert():
    print("test_metadata_only_body_is_valid_and_inert")
    dest = _tmp_dest()
    # Exactly what the live endpoint returns with no fleet data yet.
    body = {"_generated_at": "2026-08-12T00:00:00Z", "_n_min": 5, "_tool_count": 0}
    restore = _patch_urlopen(lambda req, timeout=None: _FakeResponse(json.dumps(body)))
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok true on empty fleet", status["ok"] is True)
    check("written true", status["written"] is True)
    check("tool_count 0", status["tool_count"] == 0)
    fleet, rejected = recap_savings.load_fleet_baselines(dest)
    check("reader yields empty fleet (inert)", fleet == {})
    # merge with an empty fleet is byte-identical to the seed -- the inertness guarantee.
    seed = {"S": {"manual_seconds": 30.0, "confidence": "med", "basis": "seed"}}
    check("merge == seed when fleet empty", recap_savings.merge_baselines(seed, fleet) == seed)
    os.remove(dest)


# ---------------------------------------------------------------- failure paths

def test_non_dict_body_does_not_overwrite():
    print("test_non_dict_body_does_not_overwrite")
    dest = _tmp_dest()
    good = {"S": {"manual_seconds": 120, "n": 9}}
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(good, handle)

    restore = _patch_urlopen(lambda req, timeout=None: _FakeResponse(json.dumps([1, 2, 3])))
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok false on non-object body", status["ok"] is False)
    check("not written", status["written"] is False)
    check("reason mentions object", "object" in (status["reason"] or ""))
    # The prior good file survives untouched.
    with open(dest, "r", encoding="utf-8") as handle:
        check("prior good file preserved", json.load(handle) == good)
    os.remove(dest)


def test_http_error_preserves_existing_file():
    print("test_http_error_preserves_existing_file")
    dest = _tmp_dest()
    good = {"S": {"manual_seconds": 120, "n": 9}}
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(good, handle)

    def _raise(req, timeout=None):
        raise recap_fleet_fetch.HTTPError(req, 503, "Service Unavailable", {}, None)

    restore = _patch_urlopen(_raise)
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok false on HTTP error", status["ok"] is False)
    check("reason starts HTTP", (status["reason"] or "").startswith("HTTP"))
    check("not written", status["written"] is False)
    with open(dest, "r", encoding="utf-8") as handle:
        check("existing file untouched on HTTP error", json.load(handle) == good)
    os.remove(dest)


def test_network_error_is_soft():
    print("test_network_error_is_soft")
    dest = _tmp_dest()   # no file exists

    def _raise(req, timeout=None):
        raise recap_fleet_fetch.URLError("connection refused")

    restore = _patch_urlopen(_raise)
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok false when offline", status["ok"] is False)
    check("reason mentions network", "network" in (status["reason"] or ""))
    check("no file created", not os.path.exists(dest))


def test_unparseable_body_does_not_overwrite():
    print("test_unparseable_body_does_not_overwrite")
    dest = _tmp_dest()
    good = {"S": {"manual_seconds": 120, "n": 9}}
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(good, handle)

    restore = _patch_urlopen(lambda req, timeout=None: _FakeResponse("{not json"))
    try:
        status = recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()

    check("ok false on bad JSON", status["ok"] is False)
    check("not written", status["written"] is False)
    with open(dest, "r", encoding="utf-8") as handle:
        check("existing file survives unparseable response", json.load(handle) == good)
    os.remove(dest)


def test_no_tmp_file_left_behind():
    print("test_no_tmp_file_left_behind")
    dest = _tmp_dest()
    body = {"S": {"manual_seconds": 60, "n": 5}}
    restore = _patch_urlopen(lambda req, timeout=None: _FakeResponse(json.dumps(body)))
    try:
        recap_fleet_fetch.refresh_fleet_baselines(dest=dest)
    finally:
        restore()
    check("no .tmp sidecar left", not os.path.exists(dest + ".tmp"))
    os.remove(dest)


def test_fleet_fetch_report_line():
    print("test_fleet_fetch_report_line")
    # recap_main's module-level imports do NOT bootstrap EnneadTab, so this
    # imports clean headless and lets us render the fleet-only report line.
    import recap_main
    check("None fetch -> no line", recap_main._fleet_fetch_line(None) is None)

    ok_written = recap_main._fleet_fetch_line(
        {"ok": True, "written": True, "tool_count": 3})
    check("ok+written renders count", ok_written == "FLEET FETCH      : ok, 3 tool(s)")

    ok_unwritten = recap_main._fleet_fetch_line(
        {"ok": True, "written": False, "tool_count": 0})
    check("ok-not-written flags it",
          ok_unwritten == "FLEET FETCH      : ok, 0 tool(s) (not written)")

    skipped = recap_main._fleet_fetch_line(
        {"ok": False, "written": False, "reason": "network: refused"})
    check("failure renders reason",
          skipped == "FLEET FETCH      : skipped -- network: refused (used file on disk)")


def main():
    for test in (
        test_success_writes_and_roundtrips,
        test_metadata_only_body_is_valid_and_inert,
        test_non_dict_body_does_not_overwrite,
        test_http_error_preserves_existing_file,
        test_network_error_is_soft,
        test_unparseable_body_does_not_overwrite,
        test_no_tmp_file_left_behind,
        test_fleet_fetch_report_line,
    ):
        test()
    print("-" * 50)
    if _FAILURES:
        print("FAILED {} check(s):".format(len(_FAILURES)))
        for label in _FAILURES:
            print("  - {}".format(label))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Guardrail tests for the fleet-aggregated baseline source (phase 1).

Stdlib unittest, discovered alongside check_recap.py / check_savings.py:

    python -m unittest discover -s Apps/lib/DumpScripts/recap -p "check_*.py"

The load-bearing property here is INERTNESS: with no fleet data, the merge must
be byte-identical to the seed-only path shipped in PR #134. The rest pin the
precedence (fleet-quorum -> seed -> contribute-0) and confirm a fleet median is
actually claim-eligible.
"""

import json
import os
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import recap_savings
import recap_state


class LoadFleetBaselines(unittest.TestCase):
    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(obj, handle)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_file_is_absent_not_fatal(self):
        fleet, rejected = recap_savings.load_fleet_baselines(
            os.path.join(os.path.dirname(__file__), "no_such_fleet_file.json"))
        self.assertEqual(fleet, {})
        self.assertEqual(rejected, {})

    def test_valid_entries_carry_n(self):
        path = self._write({"_comment": "x",
                            "S": {"manual_seconds": 600, "n": 7, "basis": "b"}})
        fleet, _ = recap_savings.load_fleet_baselines(path)
        self.assertEqual(set(fleet), {"S"})
        self.assertEqual(fleet["S"]["n"], 7)
        self.assertAlmostEqual(fleet["S"]["manual_seconds"], 600.0)

    def test_bad_median_rejected_not_kept(self):
        # A valid-JSON bad median would KeyError inside estimate_saved; it must be
        # rejected the same way the seed loader rejects one.
        path = self._write({
            "ok": {"manual_seconds": 90, "n": 5},
            "nan": {"manual_seconds": "soon", "n": 5},
            "neg": {"manual_seconds": -5, "n": 5},
        })
        fleet, rejected = recap_savings.load_fleet_baselines(path)
        self.assertEqual(set(fleet), {"ok"})
        self.assertEqual(set(rejected), {"nan", "neg"})

    def test_missing_or_bad_n_defaults_zero(self):
        path = self._write({"a": {"manual_seconds": 60},
                            "b": {"manual_seconds": 60, "n": "lots"},
                            "c": {"manual_seconds": 60, "n": -3}})
        fleet, _ = recap_savings.load_fleet_baselines(path)
        self.assertEqual(fleet["a"]["n"], 0)
        self.assertEqual(fleet["b"]["n"], 0)
        self.assertEqual(fleet["c"]["n"], 0)


class MergeBaselines(unittest.TestCase):
    SEED = {
        "A": {"manual_seconds": 60.0, "confidence": "low", "basis": "seedA"},
        "B": {"manual_seconds": 120.0, "confidence": "med", "basis": "seedB"},
    }

    def test_empty_fleet_is_identical_to_seed(self):
        # THE inertness guarantee: no fleet data -> exactly the PR #134 behavior.
        merged = recap_savings.merge_baselines(self.SEED, {})
        self.assertEqual(merged, self.SEED)

    def test_empty_everything_no_keyerror(self):
        self.assertEqual(recap_savings.merge_baselines({}, {}), {})
        self.assertEqual(recap_savings.merge_baselines(None, None), {})

    def test_fleet_quorum_overrides_seed_and_grades_med(self):
        fleet = {"A": {"manual_seconds": 600.0, "n": 5, "basis": "fleetA"}}
        merged = recap_savings.merge_baselines(self.SEED, fleet, n_min=5)
        self.assertAlmostEqual(merged["A"]["manual_seconds"], 600.0)
        self.assertEqual(merged["A"]["confidence"], "med")
        # B untouched (no fleet entry)
        self.assertEqual(merged["B"], self.SEED["B"])

    def test_fleet_below_quorum_falls_back_to_seed(self):
        fleet = {"A": {"manual_seconds": 600.0, "n": 4}}
        merged = recap_savings.merge_baselines(self.SEED, fleet, n_min=5)
        self.assertEqual(merged["A"], self.SEED["A"])

    def test_fleet_only_key_with_quorum_included(self):
        fleet = {"Z": {"manual_seconds": 300.0, "n": 9}}
        merged = recap_savings.merge_baselines(self.SEED, fleet, n_min=5)
        self.assertEqual(merged["Z"]["confidence"], "med")

    def test_fleet_only_below_quorum_and_no_seed_is_omitted(self):
        # Omitted -> estimate_saved contributes 0 (no imputation).
        fleet = {"Z": {"manual_seconds": 300.0, "n": 2}}
        merged = recap_savings.merge_baselines({}, fleet, n_min=5)
        self.assertNotIn("Z", merged)

    def test_seed_only_key_never_keyerrors(self):
        # The bug the review caught: fleet[s] on a seed-only key with empty fleet.
        merged = recap_savings.merge_baselines(self.SEED, {"other": {
            "manual_seconds": 1.0, "n": 99}}, n_min=5)
        self.assertEqual(merged["A"], self.SEED["A"])


class FleetMedianIsClaimEligible(unittest.TestCase):
    """A merged fleet median (med) must clear the min_rank=2 claim path; a seed
    'low' must not -- the whole point of grading."""

    def test_med_counts_low_excluded(self):
        seed = {"L": {"manual_seconds": 100.0, "confidence": "low", "basis": ""}}
        fleet = {"M": {"manual_seconds": 100.0, "n": 5, "basis": ""}}
        baselines = recap_savings.merge_baselines(seed, fleet, n_min=5)
        runs = {"L": 10, "M": 10}
        claim = recap_savings.estimate_saved(runs, {}, baselines, 20, min_rank=2)
        self.assertEqual(claim["distinct_tools"], 1)          # only M (med)
        self.assertEqual(claim["contributors"][0]["script"], "M")


class AskedBaselineState(unittest.TestCase):
    def test_empty_state_has_asked_baseline(self):
        self.assertIn("asked_baseline", recap_state._empty_state())

    def test_record_and_check_dedup(self):
        state = recap_state._empty_state()
        self.assertFalse(recap_state.already_asked_baseline(state, "s.py"))
        recap_state.record_baseline_asked(state, "s.py", "2026-08-12")
        self.assertTrue(recap_state.already_asked_baseline(state, "s.py"))

    def test_record_keeps_first_date(self):
        state = recap_state._empty_state()
        recap_state.record_baseline_asked(state, "s.py", "2026-08-12")
        recap_state.record_baseline_asked(state, "s.py", "2026-09-01")
        self.assertEqual(state["asked_baseline"]["s.py"], "2026-08-12")


if __name__ == "__main__":
    unittest.main()

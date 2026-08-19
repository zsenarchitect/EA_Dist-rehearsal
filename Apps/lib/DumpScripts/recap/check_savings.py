"""Guardrail tests for the estimated time-saved feature.

Stdlib unittest, discovered alongside check_recap.py:

    python -m unittest discover -s Apps/lib/DumpScripts/recap -p "check_*.py"

Each test pins a specific way the time-saved estimate could become dishonest:
an authored number leaking past its gates, a silent join miss, a runtime not
subtracted, or a division that swallows a bad denominator.
"""

import json
import os
import tempfile
import unittest
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import recap_catalog
import recap_claims
import recap_savings


HERE = os.path.dirname(os.path.abspath(__file__))
SHIPPED_BASELINES = os.path.join(HERE, "time_baselines.json")


# --------------------------------------------------------------- load_baselines

class LoadBaselines(unittest.TestCase):
    def _write(self, obj):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(obj, handle)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_file_is_absent_not_fatal(self):
        baselines, rejected = recap_savings.load_baselines(
            os.path.join(HERE, "does_not_exist_xyz.json"))
        self.assertEqual(baselines, {})
        self.assertEqual(rejected, {})

    def test_comment_keys_ignored(self):
        path = self._write({"_comment": "hi", "S": {"manual_seconds": 60}})
        baselines, _ = recap_savings.load_baselines(path)
        self.assertEqual(set(baselines), {"S"})

    def test_bad_entries_rejected_not_silently_kept(self):
        # A valid-JSON bad entry is exactly what "missing file -> {}" cannot catch.
        path = self._write({
            "ok": {"manual_seconds": 90, "confidence": "med"},
            "nan": {"manual_seconds": "soon"},
            "neg": {"manual_seconds": -5},
            "zero": {"manual_seconds": 0},
            "notobj": 42,
        })
        baselines, rejected = recap_savings.load_baselines(path)
        self.assertEqual(set(baselines), {"ok"})
        self.assertEqual(set(rejected), {"nan", "neg", "zero", "notobj"})

    def test_unknown_confidence_defaults_low(self):
        path = self._write({"S": {"manual_seconds": 60, "confidence": "wild"}})
        baselines, _ = recap_savings.load_baselines(path)
        self.assertEqual(baselines["S"]["confidence"], "low")


# ----------------------------------------------------- join folds seconds to script

class JoinFoldsSeconds(unittest.TestCase):
    """seconds_by_tool is keyed by normalized alias; join must fold it into
    script space or every runtime lookup silently misses."""

    def _catalog(self):
        return {
            "tools": {"script_a.py": {"alias": "Alpha"}},
            "by_alias": {"alpha": "script_a.py", "alpha alias two": "script_a.py"},
            "by_basename": {},
        }

    def test_seconds_summed_across_aliases_into_script_space(self):
        catalog = self._catalog()
        joined = recap_catalog.join_usage(
            catalog,
            runs_by_tool={"alpha": 3, "alpha alias two": 2},
            seconds_by_tool={"alpha": 30.0, "alpha alias two": 20.0})
        self.assertEqual(joined["runs"], {"script_a.py": 5})
        self.assertEqual(joined["seconds_by_script"], {"script_a.py": 50.0})

    def test_backward_compatible_without_seconds(self):
        joined = recap_catalog.join_usage(
            self._catalog(), runs_by_tool={"alpha": 1})
        self.assertEqual(joined["seconds_by_script"], {})


# --------------------------------------------------------------- estimate_saved

class EstimateSaved(unittest.TestCase):
    BASE = {"script_a.py": {"manual_seconds": 100.0, "basis": "", "confidence": "med"}}

    def test_gross_when_no_runtime(self):
        out = recap_savings.estimate_saved(
            {"script_a.py": 10}, {}, self.BASE, window_total_runs=10)
        self.assertAlmostEqual(out["seconds_saved"], 1000.0)

    def test_nets_out_observed_runtime_per_tool(self):
        # observed avg = 200/10 = 20; net per run = 100 - 20 = 80.
        out = recap_savings.estimate_saved(
            {"script_a.py": 10}, {"script_a.py": 200.0}, self.BASE,
            window_total_runs=10, duration_coverage_ok=True)
        self.assertAlmostEqual(out["seconds_saved"], 800.0)

    def test_runtime_ignored_when_coverage_untrusted(self):
        out = recap_savings.estimate_saved(
            {"script_a.py": 10}, {"script_a.py": 200.0}, self.BASE,
            window_total_runs=10, duration_coverage_ok=False)
        self.assertAlmostEqual(out["seconds_saved"], 1000.0)

    def test_tool_slower_than_baseline_nets_to_zero_and_drops(self):
        base = {"script_a.py": {"manual_seconds": 30.0, "confidence": "med"}}
        out = recap_savings.estimate_saved(
            {"script_a.py": 10}, {"script_a.py": 500.0}, base,
            window_total_runs=10, duration_coverage_ok=True)
        self.assertEqual(out["seconds_saved"], 0.0)
        self.assertEqual(out["distinct_tools"], 0)

    def test_zero_runs_no_division_error(self):
        out = recap_savings.estimate_saved(
            {"script_a.py": 0}, {"script_a.py": 200.0}, self.BASE,
            window_total_runs=0)
        self.assertEqual(out["seconds_saved"], 0.0)
        self.assertEqual(out["baseline_coverage"], 0.0)

    def test_no_baseline_contributes_nothing(self):
        out = recap_savings.estimate_saved(
            {"unbaselined.py": 100}, {}, self.BASE, window_total_runs=100)
        self.assertEqual(out["seconds_saved"], 0.0)

    def test_coverage_denominator_includes_unmatched_activity(self):
        # 10 baselined runs out of a 100-run window -> 0.10, NOT 1.0. An
        # under-matched window must not read as fully covered.
        out = recap_savings.estimate_saved(
            {"script_a.py": 10}, {}, self.BASE, window_total_runs=100)
        self.assertAlmostEqual(out["baseline_coverage"], 0.10)

    def test_min_rank_excludes_low_confidence(self):
        base = {"lo.py": {"manual_seconds": 100.0, "confidence": "low"},
                "md.py": {"manual_seconds": 100.0, "confidence": "med"}}
        runs = {"lo.py": 10, "md.py": 10}
        diag = recap_savings.estimate_saved(runs, {}, base, 20, min_rank=1)
        claim = recap_savings.estimate_saved(runs, {}, base, 20, min_rank=2)
        self.assertEqual(diag["distinct_tools"], 2)
        self.assertEqual(claim["distinct_tools"], 1)

    def test_max_share_reported(self):
        base = {"a.py": {"manual_seconds": 100.0, "confidence": "med"},
                "b.py": {"manual_seconds": 100.0, "confidence": "med"}}
        out = recap_savings.estimate_saved(
            {"a.py": 8, "b.py": 2}, {}, base, window_total_runs=10)
        self.assertAlmostEqual(out["max_share"], 0.8)


# ------------------------------------------------------- claim gating

class TimeSavedClaimGates(unittest.TestCase):
    def _fixtures(self, **savings_overrides):
        savings = {
            "seconds_saved": 6 * 3600.0,
            "baseline_coverage": 0.6,
            "distinct_tools": 6,
            "max_share": 0.3,
            "contributors": [
                {"script": "s1.py", "seconds": 2 * 3600.0, "runs": 40,
                 "assumed_seconds": 180.0}],
        }
        savings.update(savings_overrides)
        metrics = {"savings_claim": savings, "month": {"total_runs": 100},
                   "month_label": "July"}
        catalog = {"tools": {"s1.py": {"alias": "Tool One"}}}
        joined = {"coverage": 0.95}
        return metrics, catalog, joined

    def test_fires_when_all_gates_pass(self):
        claim = recap_claims._build_time_saved(*self._fixtures())
        self.assertIsNotNone(claim)
        self.assertEqual(claim.type, "time_saved")

    def test_surface_withholds_tool_body_reveals_it(self):
        claim = recap_claims._build_time_saved(*self._fixtures())
        self.assertNotIn("Tool One", claim.render_surface())  # curiosity gap
        self.assertIn("Tool One", claim.render_body())
        self.assertIn("July", claim.render_surface())

    def test_no_decimal_hours_in_output(self):
        claim = recap_claims._build_time_saved(*self._fixtures())
        # A banded range, never "6.0 hours" -- a decimal reads as measured.
        self.assertNotIn(".0 hour", claim.render_surface())
        self.assertIn("hours", claim.render_surface())

    def test_suppressed_below_distinct_tool_floor(self):
        m, c, j = self._fixtures(distinct_tools=4)
        self.assertIsNone(recap_claims._build_time_saved(m, c, j))

    def test_suppressed_when_one_tool_dominates(self):
        m, c, j = self._fixtures(max_share=0.7)
        self.assertIsNone(recap_claims._build_time_saved(m, c, j))

    def test_suppressed_on_thin_baseline_coverage(self):
        m, c, j = self._fixtures(baseline_coverage=0.3)
        self.assertIsNone(recap_claims._build_time_saved(m, c, j))

    def test_suppressed_below_materiality_floor(self):
        m, c, j = self._fixtures(seconds_saved=600.0)
        self.assertIsNone(recap_claims._build_time_saved(m, c, j))

    def test_suppressed_on_rotted_join(self):
        m, c, _ = self._fixtures()
        self.assertIsNone(recap_claims._build_time_saved(m, c, {"coverage": 0.5}))

    def test_suppressed_below_month_run_floor(self):
        m, c, j = self._fixtures()
        m["month"]["total_runs"] = 10
        self.assertIsNone(recap_claims._build_time_saved(m, c, j))


class BandHours(unittest.TestCase):
    def test_bands_are_coarse_ranges(self):
        self.assertEqual(recap_claims._band_hours(37 * 3600), "35-40 hours")
        self.assertEqual(recap_claims._band_hours(63 * 3600), "60-70 hours")

    def test_tiny_is_worded_not_numeric(self):
        self.assertEqual(recap_claims._band_hours(1800), "a couple of hours")


# ---------------------------------------------- the SHIPPED baseline file itself

class ShippedBaselineFile(unittest.TestCase):
    """The A5 backstop: a transcription slip in a full-path key is a silent
    miss. Every shipped key MUST resolve to a real catalog tool."""

    def test_every_key_resolves_and_is_positive(self):
        if not os.path.exists(SHIPPED_BASELINES):
            self.skipTest("no shipped baseline file")
        baselines, rejected = recap_savings.load_baselines(SHIPPED_BASELINES)
        self.assertEqual(rejected, {}, "shipped file has malformed entries")
        self.assertTrue(baselines, "shipped file has no usable baselines")
        catalog = recap_catalog.build_catalog()
        unresolved = recap_savings.unresolved_baseline_keys(baselines, catalog)
        self.assertEqual(
            unresolved, [],
            "shipped baseline keys that do not resolve to a tool: {}".format(unresolved))

    def test_has_enough_med_confidence_to_ever_fire(self):
        if not os.path.exists(SHIPPED_BASELINES):
            self.skipTest("no shipped baseline file")
        baselines, _ = recap_savings.load_baselines(SHIPPED_BASELINES)
        med = [k for k, v in baselines.items()
               if recap_savings.CONFIDENCE_RANK.get(v["confidence"], 1) >= 2]
        self.assertGreaterEqual(len(med), recap_claims.MIN_BASELINE_TOOLS)


if __name__ == "__main__":
    unittest.main()

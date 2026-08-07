"""Guardrail tests for the sync-time session card and the Bank client.

STATUS: the feature these cover is merged but has NEVER RUN in Revit or Rhino, and
every Bank call 401s until DESKTOP_TOKEN_SECRET is provisioned. Green tests here do
not mean the feature works. Read
docs/plans/2026-08-07-session-card-bank-desktop-handoff.md before trusting it.

Stdlib unittest on purpose -- pytest is not installed in the project venv and
the repo's pytest.ini scopes testpaths elsewhere. Run:

    python -m unittest discover -s Apps/lib/DumpScripts/session_card -p "check_*.py"

These are not coverage tests. Each one pins a specific way the card could become
wrong, misleading, or insulting -- the same job check_recap.py does for the
weekly digest. The two that matter most:

  * `test_no_bank_data_produces_no_coin_or_rank_line` is this feature's version
    of recap's `test_peer_claims_are_unbuildable_without_peer_data`. If the Bank
    is unreachable or the desktop token is not yet provisioned, the coin and rank
    lines must be ABSENT, never a zero or a stale-looking placeholder.
  * `test_warning_increase_never_produces_a_line` pins the positivity rule at the
    source rather than trusting the copy layer to remember it.
"""

import os
import sys
import tempfile
import time
import unittest

# The EnneadTab library is Windows-shaped (ENVIRONMENT reads USERPROFILE at
# import time). Provide one before importing so these tests run anywhere,
# including a Linux CI box.
if not os.environ.get("USERPROFILE"):
    os.environ["USERPROFILE"] = tempfile.mkdtemp(prefix="ea_session_card_test_")
if not os.environ.get("COMPUTERNAME"):
    os.environ["COMPUTERNAME"] = "test-machine"

_REPO_LIB = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _REPO_LIB not in sys.path:
    sys.path.insert(0, _REPO_LIB)

from EnneadTab import LEADER_BOARD  # noqa: E402
from EnneadTab import LOG  # noqa: E402
from EnneadTab import SESSION_STATS  # noqa: E402
from EnneadTab import SYNC_SUMMARY  # noqa: E402
from EnneadTab import WEB_GUARD  # noqa: E402


def _render(stats, balance=None, rank=None, earned=None, wallet=None):
    """Build the card text the way build_card would, without touching disk."""
    lines = SYNC_SUMMARY._candidates(stats, balance, rank)
    card = {
        "lines": [text for _score, text in lines],
        "coin_line": SYNC_SUMMARY._coin_line(balance, earned),
        "recommendation": None,
        "actions": [],
    }
    return SYNC_SUMMARY.render_text(card)


FULL_STATS = {
    "warnings_cleared": 12,
    "views_touched": 34,
    "tool_runs": 21,
    "distinct_tools": 7,
    "session_seconds": 9600,
}


class HonestyTests(unittest.TestCase):
    """A number on this card must be real or absent. There is no third option."""

    def test_no_bank_data_produces_no_coin_or_rank_line(self):
        text = _render(FULL_STATS, balance=None, rank=None, earned=None)
        self.assertNotIn("quack", text.lower())
        self.assertNotIn("board", text.lower())
        self.assertNotIn("#", text)
        # ...but the session facts still ship. Losing the Bank must not blank
        # the whole card.
        self.assertIn("12 warnings", text)

    def test_zero_balance_is_never_rendered_as_a_fact(self):
        """`hasBankData: False` means "no ledger rows", NOT "you have zero"."""
        self.assertIsNone(
            LEADER_BOARD.balance_from_wallet({"hasBankData": False, "spendable": 0}))
        self.assertIsNone(LEADER_BOARD.balance_from_wallet(None))
        self.assertIsNone(LEADER_BOARD.balance_from_wallet({}))

    def test_unranked_user_has_no_rank(self):
        """`self` is None until the caller has a positive score -- unranked is
        not last place, so there is nothing to show."""
        self.assertIsNone(LEADER_BOARD.rank_from_leaderboard({"self": None}))
        self.assertIsNone(LEADER_BOARD.rank_from_leaderboard({}))
        self.assertEqual(
            LEADER_BOARD.rank_from_leaderboard({"self": {"rank": 4}}), 4)

    def test_earned_today_counts_only_todays_credits(self):
        today = time.strftime("%Y-%m-%d")
        wallet = {"recent": [
            {"delta": 15, "created_at": today + "T09:00:00Z"},
            {"delta": 50, "created_at": today + "T10:00:00Z"},
            {"delta": -40, "created_at": today + "T11:00:00Z"},   # a cost
            {"delta": 99, "created_at": "2020-01-01T10:00:00Z"},  # not today
        ]}
        self.assertEqual(SYNC_SUMMARY._earned_today(wallet), 65)

    def test_earned_today_is_none_when_nothing_was_earned(self):
        """None, not 0 -- so the line reads "Balance: N" with no "+0 today"."""
        self.assertIsNone(SYNC_SUMMARY._earned_today({"recent": []}))
        self.assertIsNone(SYNC_SUMMARY._earned_today({}))
        self.assertIsNone(SYNC_SUMMARY._earned_today(None))


class PositivityTests(unittest.TestCase):
    """The card may never scold. Enforced at the source, not in the copy."""

    def test_warning_increase_never_produces_a_line(self):
        """SESSION_STATS returns None when warnings went UP, so there is no
        value the copy layer could turn into a complaint even by accident."""
        stats = dict(FULL_STATS)
        stats["warnings_cleared"] = None
        text = _render(stats)
        self.assertNotIn("warning", text.lower())

    def test_card_is_never_empty_for_a_real_session(self):
        """A session with nothing but time on the clock still says something."""
        stats = {"warnings_cleared": None, "views_touched": None,
                 "tool_runs": None, "distinct_tools": None,
                 "session_seconds": 3720}
        lines = SYNC_SUMMARY._candidates(stats, None, None)
        self.assertTrue(lines)

    def test_missing_metrics_are_omitted_not_zeroed(self):
        stats = {"warnings_cleared": None, "views_touched": None,
                 "tool_runs": 3, "distinct_tools": 1, "session_seconds": 600}
        text = _render(stats)
        self.assertNotIn("0 views", text)
        self.assertNotIn("0 warnings", text)
        self.assertIn("3 EnneadTab tools", text)


class BankEnvelopeTests(unittest.TestCase):
    """The server rejects a malformed envelope outright, so the client must not
    build one -- a 400 would silently cost the user the coins."""

    def test_non_numeric_metrics_are_dropped(self):
        cleaned = LEADER_BOARD._clean_metrics(
            {"good": 3, "text": "nope", "none": None, "float": 1.5})
        self.assertEqual(cleaned, {"good": 3, "float": 1.5})

    def test_booleans_are_refused_rather_than_coerced(self):
        """bool is an int subclass; True would post as 1 and read as a
        measurement. Refuse it rather than quietly turn a flag into a metric."""
        self.assertEqual(LEADER_BOARD._clean_metrics({"flag": True}), {})

    def test_metrics_must_be_a_flat_mapping(self):
        self.assertEqual(LEADER_BOARD._clean_metrics({"nested": {"a": 1}}), {})
        self.assertEqual(LEADER_BOARD._clean_metrics([1, 2, 3]), {})
        self.assertEqual(LEADER_BOARD._clean_metrics(None), {})

    def test_outbox_drops_events_the_server_would_reject_as_too_old(self):
        now = time.time()
        items = [
            {"event_id": "fresh", "_queued_at": now - 60},
            {"event_id": "stale", "_queued_at": now - (72 * 60 * 60)},
            {"event_id": "unstamped"},
        ]
        kept = [x.get("event_id") for x in LEADER_BOARD._prune(items)]
        self.assertEqual(kept, ["fresh"])

    def test_outbox_is_bounded(self):
        now = time.time()
        items = [{"event_id": str(i), "_queued_at": now}
                 for i in range(LEADER_BOARD.MAX_OUTBOX_ITEMS + 50)]
        pruned = LEADER_BOARD._prune(items)
        self.assertEqual(len(pruned), LEADER_BOARD.MAX_OUTBOX_ITEMS)
        # The newest survive -- an offline fortnight must not pin the queue to
        # the oldest, least relevant events.
        self.assertEqual(pruned[-1]["event_id"],
                         str(LEADER_BOARD.MAX_OUTBOX_ITEMS + 49))

    def test_event_ids_are_unique(self):
        """event_id is the Bank's primary key and dedupe is ON CONFLICT DO
        NOTHING -- a collision would silently discard a real event."""
        ids = set(LEADER_BOARD._new_event_id() for _ in range(500))
        self.assertEqual(len(ids), 500)


class SessionCounterTests(unittest.TestCase):

    def test_views_are_deduped(self):
        SESSION_STATS.store_set(SESSION_STATS.KEY_VIEWS, "")
        for view_id in ["101", "102", "101", "103", "102"]:
            SESSION_STATS.note_view(view_id)
        self.assertEqual(SESSION_STATS.get_views_touched(), 3)

    def test_unarmed_counter_reads_as_unknown_not_zero(self):
        """An unregistered handler and an idle session are different facts;
        only the second deserves to be shown."""
        SESSION_STATS.store_set(SESSION_STATS.KEY_VIEWS, None)
        SESSION_STATS._MEMORY_STORE.pop(SESSION_STATS.KEY_VIEWS, None)
        self.assertIsNone(SESSION_STATS.get_views_touched())


class CardLifetimeTests(unittest.TestCase):

    def test_card_expires_before_the_arcade_takes_over(self):
        """The two surfaces hand over; they must never stack. If one threshold
        moves, this fails and reminds you to move the other."""
        from EnneadTab import ARCADE
        self.assertLessEqual(
            SYNC_SUMMARY.CARD_STAY_SECONDS, ARCADE.WAIT_THRESHOLD_SECONDS)


class ToolRunGateTests(unittest.TestCase):
    """LOG.log is applied to things that are not tools. Reporting those as
    `tool_run` would mis-state a firm-wide auditable ledger AND burn the daily
    earn cap that real tool use is meant to fill."""

    def test_button_bundles_are_reported(self):
        for path in [
            r"C:\dev\Apps\_revit\EnneaDuck.extension\EnneadTab.tab\ACE.panel\x.pushbutton\x_script.py",
            "/dev/Apps/_rhino/Render.tab/ai_render.button/view2render_left.py",
            r"C:\dev\Apps\_revit\x.extension\y.tab\z.panel\w.smartbutton\w_script.py",
            r"C:\dev\Apps\_revit\x.extension\y.tab\z.panel\v.splitbutton\v_script.py",
            # Inside a pulldown, but still within its own pushbutton bundle.
            r"C:\dev\y.tab\z.panel\group.pulldown\thing.pushbutton\thing_script.py",
        ]:
            self.assertTrue(LOG._is_button_script(path), path)

    def test_hooks_and_startup_are_not_reported(self):
        """The regression this gate exists for. Both sync hooks and
        plugin_startup.py carry @LOG.log; wiring blindly would emit a tool_run on
        every sync and every Revit launch."""
        for path in [
            r"C:\dev\Apps\_revit\EnneaDuck.extension\hooks\doc-syncing.py",
            r"C:\dev\Apps\_revit\EnneaDuck.extension\hooks\doc-synced.py",
            r"C:\dev\Apps\_revit\EnneaDuck.extension\plugin_startup.py",
            "/dev/Apps/lib/DumpScripts/recap/recap_main.py",
        ]:
            self.assertFalse(LOG._is_button_script(path), path)

    def test_missing_or_junk_path_is_denied_not_crashed(self):
        for path in [None, "", 0, "script.py"]:
            self.assertFalse(LOG._is_button_script(path))

    def test_script_path_becomes_subject(self):
        """__title__ is display copy a designer can rename; the script file is
        the durable key. Both are sent so Bank rules can be curated on either."""
        LEADER_BOARD._write_outbox([])
        LEADER_BOARD.report_tool_run(
            "Batch Format Family Name",
            duration_seconds=1.5,
            script_path=r"C:\dev\x.pushbutton\batch_fix_family_name_script.py")
        queued = LEADER_BOARD._read_outbox()
        self.assertEqual(len(queued), 1)
        envelope = queued[0]
        self.assertEqual(envelope["event_type"], "tool_run")
        self.assertEqual(envelope["action"], "Batch Format Family Name")
        self.assertEqual(envelope["subject"], "batch_fix_family_name_script.py")
        self.assertEqual(envelope["metrics"], {"duration_s": 1.5})
        self.assertEqual(envelope["result"], "success")
        LEADER_BOARD._write_outbox([])


class FlushBudgetTests(unittest.TestCase):

    def test_flush_budget_exceeds_a_days_volume(self):
        """One event per button click means the drain must out-pace a heavy
        day, or events age out at 47h having never been sent -- invisibly."""
        self.assertGreaterEqual(
            LEADER_BOARD.FLUSH_MAX_ITEMS, LEADER_BOARD.MAX_OUTBOX_ITEMS)

    def test_wall_clock_budget_stops_a_hung_flush(self):
        """A dead network must not leave the daemon thread grinding through
        hundreds of 8s timeouts. Whatever is untried stays queued."""
        now = time.time()
        LEADER_BOARD._write_outbox([
            {"event_id": "e{}".format(i), "source_app": "t", "event_type": "tool_run",
             "action": "a", "result": "success", "occurred_at": "x",
             "_queued_at": now}
            for i in range(10)
        ])
        calls = []

        def _slow_request(method, url, headers, body=None):
            calls.append(body)
            time.sleep(0.05)
            return 200, {}

        original_request = LEADER_BOARD._request
        original_headers = LEADER_BOARD._auth_headers
        try:
            LEADER_BOARD._request = _slow_request
            LEADER_BOARD._auth_headers = lambda: {"Authorization": "Bearer x"}
            sent = LEADER_BOARD.flush_outbox(max_seconds=0.12)
        finally:
            LEADER_BOARD._request = original_request
            LEADER_BOARD._auth_headers = original_headers

        self.assertLess(sent, 10, "budget should have stopped the run early")
        # Stopping is a pause, never a loss: everything unsent is still queued.
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 10 - sent)
        LEADER_BOARD._write_outbox([])

    def test_flush_drops_permanently_rejected_events(self):
        """A poison envelope must not block the queue behind it forever."""
        now = time.time()
        LEADER_BOARD._write_outbox([
            {"event_id": "bad", "source_app": "t", "event_type": "tool_run",
             "action": "a", "result": "success", "occurred_at": "x",
             "_queued_at": now}
        ])
        original_request = LEADER_BOARD._request
        original_headers = LEADER_BOARD._auth_headers
        try:
            LEADER_BOARD._request = lambda *a, **k: (400, {"error": "bad envelope"})
            LEADER_BOARD._auth_headers = lambda: {"Authorization": "Bearer x"}
            sent = LEADER_BOARD.flush_outbox()
        finally:
            LEADER_BOARD._request = original_request
            LEADER_BOARD._auth_headers = original_headers

        self.assertEqual(sent, 0)
        self.assertEqual(LEADER_BOARD._read_outbox(), [])


class DecoratorSafetyTests(unittest.TestCase):
    """LOG.log wraps all 340 instrumented buttons. Breaking it breaks every
    button fleet-wide, and its bare `except:` re-runs the wrapped function --
    so "ran exactly once" is the property that matters most here."""

    def _run(self, script_path, func):
        LEADER_BOARD._write_outbox([])
        wrapped = LOG.log(script_path, "Test Tool")(func)
        return wrapped

    def test_button_run_executes_once_and_queues_once(self):
        calls = []
        wrapped = self._run(r"C:\dev\x.pushbutton\x_script.py",
                            lambda: calls.append(1))
        wrapped()
        self.assertEqual(len(calls), 1, "the tool must run exactly once")
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 1)
        LEADER_BOARD._write_outbox([])

    def test_hook_run_executes_once_and_queues_nothing(self):
        calls = []
        wrapped = self._run(r"C:\dev\EnneaDuck.extension\hooks\doc-syncing.py",
                            lambda: calls.append(1))
        wrapped()
        self.assertEqual(len(calls), 1)
        self.assertEqual(LEADER_BOARD._read_outbox(), [])

    def test_a_raising_tool_queues_nothing(self):
        """We only reach the emit when func returned normally, so
        result="success" is true by construction rather than by assertion."""
        def boom():
            raise ValueError("tool blew up")

        wrapped = self._run(r"C:\dev\x.pushbutton\x_script.py", boom)
        try:
            wrapped()
        except Exception:
            pass
        self.assertEqual(LEADER_BOARD._read_outbox(), [])


class _FakeDoc(object):
    """Minimal stand-in for a Revit Document. Only GetWarnings and Title are
    touched by anything under test."""

    def __init__(self, warnings=0, title="Fake Model", raises=False):
        self._warnings = warnings
        self.Title = title
        self._raises = raises

    def GetWarnings(self):
        if self._raises:
            raise RuntimeError("Revit said no")
        return [object() for _ in range(self._warnings)]


class ModelOpenChargeTests(unittest.TestCase):
    """cost_open_many_warnings is the ONE seeded rule with no dailyCap and no
    cooldown. Opening is passive and repeatable, so the client is the only thing
    standing between a user and being charged the cap once per open."""

    def setUp(self):
        LEADER_BOARD._write_outbox([])
        LEADER_BOARD.DATA_FILE.set_data({}, LEADER_BOARD.OPEN_CHARGED_FILE)

    def tearDown(self):
        LEADER_BOARD._write_outbox([])
        LEADER_BOARD.DATA_FILE.set_data({}, LEADER_BOARD.OPEN_CHARGED_FILE)

    def test_same_document_is_only_charged_once_a_day(self):
        first = LEADER_BOARD.report_model_opened(200, "Tower A")
        second = LEADER_BOARD.report_model_opened(200, "Tower A")
        self.assertTrue(first)
        self.assertFalse(second, "reopening the same model must not charge again")
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 1)

    def test_a_different_document_still_charges(self):
        LEADER_BOARD.report_model_opened(200, "Tower A")
        self.assertTrue(LEADER_BOARD.report_model_opened(50, "Tower B"))
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 2)

    def test_a_new_day_charges_again(self):
        LEADER_BOARD.report_model_opened(200, "Tower A")
        # Age the stamp rather than the clock.
        LEADER_BOARD.DATA_FILE.set_data({"Tower A": "2020-01-01"},
                                        LEADER_BOARD.OPEN_CHARGED_FILE)
        self.assertTrue(LEADER_BOARD.report_model_opened(200, "Tower A"))

    def test_record_keeps_only_today(self):
        """Pruning on write is what stops the file growing forever."""
        LEADER_BOARD.DATA_FILE.set_data(
            {"Old A": "2020-01-01", "Old B": "2021-06-30"},
            LEADER_BOARD.OPEN_CHARGED_FILE)
        LEADER_BOARD.report_model_opened(10, "Tower A")
        kept = LEADER_BOARD.DATA_FILE.get_data(LEADER_BOARD.OPEN_CHARGED_FILE)
        self.assertEqual(sorted(kept.keys()), ["Tower A"])

    def test_unknown_warning_count_charges_nothing(self):
        self.assertFalse(LEADER_BOARD.report_model_opened(None, "Tower A"))
        self.assertEqual(LEADER_BOARD._read_outbox(), [])

    def test_envelope_shape(self):
        LEADER_BOARD.report_model_opened(37, "Tower A")
        envelope = LEADER_BOARD._read_outbox()[0]
        self.assertEqual(envelope["event_type"], "model_metric")
        self.assertEqual(envelope["action"], "open_model")
        self.assertEqual(envelope["metrics"], {"warnings": 37})
        self.assertEqual(envelope["subject"], "Tower A")


class WarningCountTests(unittest.TestCase):

    def test_counts_warnings(self):
        self.assertEqual(SESSION_STATS.count_warnings(_FakeDoc(warnings=12)), 12)
        self.assertEqual(SESSION_STATS.count_warnings(_FakeDoc(warnings=0)), 0)

    def test_unreadable_document_is_unknown_not_zero(self):
        """None, not 0 -- a failed read must not be reported as a clean model."""
        self.assertIsNone(SESSION_STATS.count_warnings(_FakeDoc(raises=True)))
        self.assertIsNone(SESSION_STATS.count_warnings(None))

    def test_baseline_seeded_at_open_lets_the_first_sync_report(self):
        """The payoff of counting at document-open.

        Without a baseline, the first get_warnings_cleared of a session returns
        None because it has nothing to compare against -- so the card could never
        mention warnings cleared before the SECOND sync.
        """
        doc = _FakeDoc(warnings=40, title="Baseline Model")
        SESSION_STATS.note_warning_baseline(doc, 40)

        doc._warnings = 25
        self.assertEqual(SESSION_STATS.get_warnings_cleared(doc), 15)

    def test_without_seeding_the_first_read_is_silent(self):
        """The behaviour being fixed, pinned so the payoff above stays real."""
        doc = _FakeDoc(warnings=40, title="Unseeded Model")
        SESSION_STATS.store_set(SESSION_STATS._baseline_key(doc), None)
        SESSION_STATS._MEMORY_STORE.pop(SESSION_STATS._baseline_key(doc), None)
        self.assertIsNone(SESSION_STATS.get_warnings_cleared(doc))

    def test_more_warnings_than_before_still_reports_nothing(self):
        doc = _FakeDoc(warnings=10, title="Worsening Model")
        SESSION_STATS.note_warning_baseline(doc, 10)
        doc._warnings = 30
        self.assertIsNone(SESSION_STATS.get_warnings_cleared(doc))


class LoginPageIsNotSuccessTests(unittest.TestCase):
    """The 2026-08-07 production bug, pinned.

    EnneadTab-Home's middleware answers a gated API path with a 302 to an SSO
    login page. Every HTTP library here followed it, landed on a 200 with an HTML
    body, and `flush_outbox` scored that as a delivered event and DELETED it.
    Nothing raised, nothing logged, and the "sent" count went up.

    These are the tests that would have caught it. None of them touch the
    network -- the point is that the client's own success test must reject a
    response the Bank did not send, regardless of what the transport reports.
    """

    def setUp(self):
        LEADER_BOARD._write_outbox([])

    def tearDown(self):
        LEADER_BOARD._write_outbox([])

    def _queue_one(self):
        LEADER_BOARD.report_event("tool_run", "Some Tool")
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 1)

    def _flush_with(self, status, payload):
        original_request = LEADER_BOARD._request
        original_headers = LEADER_BOARD._auth_headers
        try:
            LEADER_BOARD._request = lambda *a, **k: (status, payload)
            LEADER_BOARD._auth_headers = lambda: {"Authorization": "Bearer x"}
            return LEADER_BOARD.flush_outbox()
        finally:
            LEADER_BOARD._request = original_request
            LEADER_BOARD._auth_headers = original_headers

    def test_a_200_with_an_unparseable_body_does_not_consume_the_event(self):
        """THE regression. A login page is a 200 whose body is not JSON."""
        self._queue_one()
        sent = self._flush_with(200, None)
        self.assertEqual(sent, 0, "an HTML login page must not count as delivered")
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 1,
                         "the event must survive a response the Bank did not send")

    def test_a_redirect_does_not_consume_the_event(self):
        self._queue_one()
        sent = self._flush_with(302, None)
        self.assertEqual(sent, 0)
        self.assertEqual(len(LEADER_BOARD._read_outbox()), 1)

    def test_a_real_200_still_delivers(self):
        """The guard must not break the working path."""
        self._queue_one()
        sent = self._flush_with(200, {"event_id": "x", "deduped": False, "entries": 1})
        self.assertEqual(sent, 1)
        self.assertEqual(LEADER_BOARD._read_outbox(), [])

    def test_a_deduped_replay_still_delivers(self):
        self._queue_one()
        sent = self._flush_with(200, {"deduped": True, "entries": 0})
        self.assertEqual(sent, 1, "a replay IS success")
        self.assertEqual(LEADER_BOARD._read_outbox(), [])


class WebGuardTests(unittest.TestCase):

    def test_redirect_classification(self):
        for status in (300, 301, 302, 307, 308, 399):
            self.assertTrue(WEB_GUARD.is_redirect(status), status)
        for status in (200, 204, 400, 401, 429, 500, None):
            self.assertFalse(WEB_GUARD.is_redirect(status), status)

    def test_delivery_requires_a_parsed_body(self):
        self.assertTrue(WEB_GUARD.is_delivered(200, {"ok": True}))
        self.assertTrue(WEB_GUARD.is_delivered(200, []), "an empty list is still parsed JSON")
        self.assertFalse(WEB_GUARD.is_delivered(200, None))
        self.assertFalse(WEB_GUARD.is_delivered(302, {"ok": True}))
        self.assertFalse(WEB_GUARD.is_delivered(401, None))
        self.assertFalse(WEB_GUARD.is_delivered(None, None))

    def test_describe_names_the_real_problem(self):
        """A log line should say 'proxy', not 'auth' or 'network' -- those send
        whoever reads it looking in the wrong place."""
        note = WEB_GUARD.describe(302)
        self.assertIn("login page", note)
        self.assertIn("configuration", note)
        self.assertIsNone(WEB_GUARD.describe(200))


class LogDecoratorPlacementTests(unittest.TestCase):

    def test_log_still_carries_its_backup_decorator(self):
        """Inserting a helper between @FOLDER.backup_data and `def log` silently
        moved the decorator onto the helper, so log_<user>.sexyDuck stopped being
        backed up. Nothing failed; the backup just stopped. Pin the wiring."""
        # backup_data does not use functools.wraps, so a decorated function
        # reports its inner name. That asymmetry is what makes this checkable:
        # decorated -> "wrapper", undecorated -> its own name.
        self.assertEqual(
            LOG.log.__name__, "wrapper",
            "log() lost its @FOLDER.backup_data decorator")
        self.assertEqual(
            LOG._is_button_script.__name__, "_is_button_script",
            "_is_button_script must NOT be wrapped in backup_data")


if __name__ == "__main__":
    unittest.main()

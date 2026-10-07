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
import json
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


class ArcadeActionTests(unittest.TestCase):
    """Session-card Arcade CTA: Play when installed, soft Get when not,
    never when opted out, and Get is independently 7-day throttled."""

    def setUp(self):
        from EnneadTab import ARCADE
        self._ARCADE = ARCADE
        self._orig_hate = ARCADE.is_hate_arcade
        self._orig_exe = ARCADE.get_installed_arcade_exe
        SESSION_STATS.store_set(SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)
        SESSION_STATS._MEMORY_STORE.pop(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)

    def tearDown(self):
        self._ARCADE.is_hate_arcade = self._orig_hate
        self._ARCADE.get_installed_arcade_exe = self._orig_exe
        SESSION_STATS.store_set(SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)
        SESSION_STATS._MEMORY_STORE.pop(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)

    def _set_arcade(self, installed=False, hate=False):
        self._ARCADE.is_hate_arcade = lambda: hate
        self._ARCADE.get_installed_arcade_exe = (
            lambda: r"C:\Users\test\AppData\Local\Programs\EnneadTab-Arcade\EnneadTab-Arcade.exe"
            if installed else None)

    def _arcade_action(self, actions):
        for action in actions:
            if action.get("id") in (
                    SYNC_SUMMARY.ACTION_ID_ARCADE_PLAY,
                    SYNC_SUMMARY.ACTION_ID_ARCADE_GET):
                return action
        return None

    def test_not_installed_offers_get_arcade_open_url(self):
        self._set_arcade(installed=False, hate=False)
        actions = SYNC_SUMMARY._actions(balance=100)
        arcade = self._arcade_action(actions)
        self.assertIsNotNone(arcade)
        self.assertEqual(arcade["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_GET)
        self.assertEqual(arcade["label"], "Get Arcade")
        self.assertEqual(arcade["type"], "open_url")
        self.assertEqual(arcade["payload"], self._ARCADE.ARCADE_LANDING_URL)
        self.assertTrue(arcade["payload"].startswith("https://enneadtab.com/arcade"))
        self.assertEqual(actions[0]["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_GET)
        self.assertEqual(actions[1]["id"], "sync_card_bank")

    def test_hate_opt_out_omits_arcade_action(self):
        self._set_arcade(installed=False, hate=True)
        actions = SYNC_SUMMARY._actions(balance=100)
        self.assertIsNone(self._arcade_action(actions))
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["id"], "sync_card_bank")

        self._set_arcade(installed=True, hate=True)
        actions = SYNC_SUMMARY._actions(balance=100)
        self.assertIsNone(self._arcade_action(actions))

    def test_installed_offers_play_arcade_open_path(self):
        self._set_arcade(installed=True, hate=False)
        actions = SYNC_SUMMARY._actions(balance=100)
        arcade = self._arcade_action(actions)
        self.assertIsNotNone(arcade)
        self.assertEqual(arcade["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_PLAY)
        self.assertEqual(arcade["label"], "Play arcade")
        self.assertEqual(arcade["type"], "open_path")
        self.assertTrue(arcade["payload"].endswith("EnneadTab-Arcade.exe"))
        self.assertEqual(actions[0]["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_PLAY)

    def test_install_cta_suppressed_within_seven_day_cooldown(self):
        self._set_arcade(installed=False, hate=False)
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, time.time())
        actions = SYNC_SUMMARY._actions(balance=100)
        self.assertIsNone(self._arcade_action(actions))
        self.assertEqual(actions[0]["id"], "sync_card_bank")

    def test_install_cta_returns_after_cooldown(self):
        self._set_arcade(installed=False, hate=False)
        aged = time.time() - SYNC_SUMMARY.ARCADE_INSTALL_CTA_COOLDOWN_SECONDS - 1
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, aged)
        actions = SYNC_SUMMARY._actions(balance=None)
        arcade = self._arcade_action(actions)
        self.assertIsNotNone(arcade)
        self.assertEqual(arcade["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_GET)

    def test_play_arcade_ignores_install_cta_cooldown(self):
        """Cooldown gates Get only; installed Play must still appear."""
        self._set_arcade(installed=True, hate=False)
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, time.time())
        actions = SYNC_SUMMARY._actions(balance=100)
        arcade = self._arcade_action(actions)
        self.assertEqual(arcade["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_PLAY)

    def test_show_session_card_stamps_install_cta_cooldown(self):
        """Timestamp is recorded when the card is shown with Get Arcade, not
        merely when _actions is computed (same pattern as KEY_LAST_SHOWN)."""
        self._set_arcade(installed=False, hate=False)
        self.assertTrue(SYNC_SUMMARY._arcade_install_cta_due())

        shown = []

        def _fake_messenger(**kwargs):
            shown.append(kwargs)

        original_messenger = SYNC_SUMMARY.NOTIFICATION.messenger
        original_enabled = SYNC_SUMMARY.is_enabled
        original_should = SYNC_SUMMARY._should_show_now
        original_build = SYNC_SUMMARY.build_card
        try:
            SYNC_SUMMARY.NOTIFICATION.messenger = _fake_messenger
            SYNC_SUMMARY.is_enabled = lambda: True
            SYNC_SUMMARY._should_show_now = lambda: True
            SYNC_SUMMARY.build_card = lambda doc=None: {
                "lines": ["You have been in this session for 10 min."],
                "coin_line": None,
                "recommendation": None,
                "actions": SYNC_SUMMARY._actions(balance=None),
            }
            self.assertTrue(SYNC_SUMMARY.show_session_card())
        finally:
            SYNC_SUMMARY.NOTIFICATION.messenger = original_messenger
            SYNC_SUMMARY.is_enabled = original_enabled
            SYNC_SUMMARY._should_show_now = original_should
            SYNC_SUMMARY.build_card = original_build

        self.assertEqual(len(shown), 1)
        self.assertEqual(
            shown[0]["actions"][0]["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_GET)
        stamped = SESSION_STATS.store_get(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN)
        self.assertIsNotNone(stamped)
        self.assertFalse(SYNC_SUMMARY._arcade_install_cta_due())

    def test_computing_actions_alone_does_not_stamp_cooldown(self):
        self._set_arcade(installed=False, hate=False)
        SYNC_SUMMARY._actions(balance=None)
        self.assertIsNone(SESSION_STATS.store_get(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN))
        self.assertTrue(SYNC_SUMMARY._arcade_install_cta_due())


class ArcadeAfterWaitToastTests(unittest.TestCase):
    """Post-wait Get Arcade toast: long wait + uninstalled only, shares the
    7-day install-CTA cooldown with the session card so card+toast never
    double-nag the same wait or spam twice a week.
    """

    def setUp(self):
        from EnneadTab import ARCADE
        self._ARCADE = ARCADE
        self._orig_hate = ARCADE.is_hate_arcade
        self._orig_exe = ARCADE.get_installed_arcade_exe
        SESSION_STATS.store_set(SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)
        SESSION_STATS._MEMORY_STORE.pop(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)
        self._shown = []
        self._orig_messenger = SYNC_SUMMARY.NOTIFICATION.messenger
        SYNC_SUMMARY.NOTIFICATION.messenger = self._capture_messenger

    def tearDown(self):
        self._ARCADE.is_hate_arcade = self._orig_hate
        self._ARCADE.get_installed_arcade_exe = self._orig_exe
        SYNC_SUMMARY.NOTIFICATION.messenger = self._orig_messenger
        SESSION_STATS.store_set(SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)
        SESSION_STATS._MEMORY_STORE.pop(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, None)

    def _capture_messenger(self, **kwargs):
        self._shown.append(kwargs)

    def _set_arcade(self, installed=False, hate=False):
        self._ARCADE.is_hate_arcade = lambda: hate
        self._ARCADE.get_installed_arcade_exe = (
            lambda: r"C:\Users\test\AppData\Local\Programs\EnneadTab-Arcade\EnneadTab-Arcade.exe"
            if installed else None)

    def test_uninstalled_long_wait_offers_toast(self):
        self._set_arcade(installed=False, hate=False)
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS + 5)
        self.assertTrue(ok)
        self.assertEqual(len(self._shown), 1)
        payload = self._shown[0]
        self.assertEqual(payload["main_text"], SYNC_SUMMARY.ARCADE_TOAST_MAIN_TEXT)
        self.assertEqual(payload["level"], "info")
        action = payload["actions"][0]
        self.assertEqual(action["id"], SYNC_SUMMARY.ACTION_ID_ARCADE_TOAST_GET)
        self.assertEqual(action["label"], "Get Arcade")
        self.assertEqual(action["type"], "open_url")
        self.assertEqual(action["payload"], self._ARCADE.ARCADE_LANDING_URL)
        stamped = SESSION_STATS.store_get(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN)
        self.assertIsNotNone(stamped)
        self.assertFalse(SYNC_SUMMARY._arcade_install_cta_due())

    def test_installed_skips_toast(self):
        self._set_arcade(installed=True, hate=False)
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS + 5)
        self.assertFalse(ok)
        self.assertEqual(self._shown, [])

    def test_opt_out_skips_toast(self):
        self._set_arcade(installed=False, hate=True)
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS + 5)
        self.assertFalse(ok)
        self.assertEqual(self._shown, [])

    def test_short_wait_skips_toast(self):
        self._set_arcade(installed=False, hate=False)
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS - 1)
        self.assertFalse(ok)
        self.assertEqual(self._shown, [])

    def test_none_or_missing_wait_skips_toast(self):
        self._set_arcade(installed=False, hate=False)
        self.assertFalse(SYNC_SUMMARY.offer_arcade_after_wait(None))
        self.assertFalse(SYNC_SUMMARY.offer_arcade_after_wait("nope"))
        self.assertEqual(self._shown, [])

    def test_cooldown_skips_toast(self):
        self._set_arcade(installed=False, hate=False)
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, time.time())
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS + 5)
        self.assertFalse(ok)
        self.assertEqual(self._shown, [])

    def test_card_offer_this_wait_blocks_toast(self):
        """Shared cooldown: Get Arcade on the session card stamps the key, so
        the post-wait toast does not double-nag the same wait."""
        self._set_arcade(installed=False, hate=False)
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, time.time())
        self.assertFalse(SYNC_SUMMARY._arcade_install_cta_due())
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS + 30)
        self.assertFalse(ok)
        self.assertEqual(self._shown, [])

    def test_toast_returns_after_cooldown(self):
        self._set_arcade(installed=False, hate=False)
        aged = time.time() - SYNC_SUMMARY.ARCADE_INSTALL_CTA_COOLDOWN_SECONDS - 1
        SESSION_STATS.store_set(
            SYNC_SUMMARY.KEY_ARCADE_INSTALL_CTA_LAST_SHOWN, aged)
        ok = SYNC_SUMMARY.offer_arcade_after_wait(
            self._ARCADE.WAIT_THRESHOLD_SECONDS)
        self.assertTrue(ok)
        self.assertEqual(len(self._shown), 1)


class ArcadeWaitFlagTests(unittest.TestCase):
    """Flag lifecycle: written even when uninstalled; end returns age before delete."""

    def setUp(self):
        from EnneadTab import ARCADE
        self._ARCADE = ARCADE
        self._tmpdir = tempfile.mkdtemp(prefix="ea_arcade_flag_")
        self._flag_path = os.path.join(self._tmpdir, ARCADE.FLAG_FILE_NAME)
        self._orig_flag_path = ARCADE.get_flag_path
        self._orig_hate = ARCADE.is_hate_arcade
        self._orig_exe = ARCADE.get_installed_arcade_exe
        self._orig_popen = ARCADE.subprocess.Popen
        ARCADE.get_flag_path = lambda: self._flag_path

        def _no_watcher(*a, **k):
            raise AssertionError("watcher must not spawn when uninstalled")

        ARCADE.subprocess.Popen = _no_watcher

    def tearDown(self):
        self._ARCADE.get_flag_path = self._orig_flag_path
        self._ARCADE.is_hate_arcade = self._orig_hate
        self._ARCADE.get_installed_arcade_exe = self._orig_exe
        self._ARCADE.subprocess.Popen = self._orig_popen
        try:
            if os.path.exists(self._flag_path):
                os.remove(self._flag_path)
            os.rmdir(self._tmpdir)
        except Exception:
            pass

    def test_start_writes_flag_when_uninstalled_without_watcher(self):
        self._ARCADE.is_hate_arcade = lambda: False
        self._ARCADE.get_installed_arcade_exe = lambda: None
        self._ARCADE.start_wait_watch("sync", "Tower A")
        self.assertTrue(os.path.exists(self._flag_path))
        with open(self._flag_path, "r") as f:
            flag = json.load(f)
        self.assertEqual(flag["kind"], "sync")
        self.assertEqual(flag["doc"], "Tower A")

    def test_end_returns_age_and_deletes_flag(self):
        self._ARCADE.is_hate_arcade = lambda: False
        self._ARCADE.get_installed_arcade_exe = lambda: None
        self._ARCADE.start_wait_watch("open", "Tower B")
        # Age the flag so end_wait_watch reports a measurable duration.
        past = time.time() - 75
        os.utime(self._flag_path, (past, past))
        age = self._ARCADE.end_wait_watch()
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 70)
        self.assertFalse(os.path.exists(self._flag_path))

    def test_end_with_no_flag_returns_none(self):
        self.assertFalse(os.path.exists(self._flag_path))
        self.assertIsNone(self._ARCADE.end_wait_watch())

    def test_hate_skips_flag_entirely(self):
        self._ARCADE.is_hate_arcade = lambda: True
        self._ARCADE.get_installed_arcade_exe = lambda: None
        self._ARCADE.start_wait_watch("sync", "Tower C")
        self.assertFalse(os.path.exists(self._flag_path))

    def test_installed_watcher_passes_revit_wait_arg(self):
        """OS half of #6050: Arcade offer mode needs --revit-wait (Arcade PR #25)."""
        captured = []
        fake_exe = (
            r"C:\Users\test\AppData\Local\Programs\EnneadTab-Arcade\EnneadTab-Arcade.exe")

        def _capture_popen(args, **kwargs):
            captured.append(args)
            return None

        # start_wait_watch calls the private helper; mock that (public alone is not enough).
        orig_private = self._ARCADE._get_installed_arcade_exe
        self._ARCADE.is_hate_arcade = lambda: False
        self._ARCADE._get_installed_arcade_exe = lambda: fake_exe
        self._ARCADE.subprocess.Popen = _capture_popen
        try:
            self._ARCADE.start_wait_watch("sync", "Tower D")
        finally:
            self._ARCADE._get_installed_arcade_exe = orig_private

        self.assertEqual(len(captured), 1)
        ps_cmd = captured[0][-1]
        self.assertIn("Start-Process", ps_cmd)
        self.assertIn("-ArgumentList '--revit-wait'", ps_cmd)
        self.assertIn("EnneadTab-Arcade.exe", ps_cmd)
        self.assertNotIn("http", ps_cmd.lower())


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

# EnneadTab usage recap

Personal usage recap: a monthly email and a weekly in-app digest that report what
someone actually used and recommend tools they have not tried. The goal is DAU.

**Phase 1 is what ships here.** No email is sent, nothing is written to the shared
drive, and there is no `SYSTEM.APPS` entry yet. The point of this phase is to
validate the *content* — the subjective, risky part — before committing any
infrastructure to it.

## Run it

```bash
# Dry run against your own log: prints the report, writes and opens the preview.
python recap_main.py

# Prove the deployment. This is the real risk -- see "Import surface" below.
python recap_main.py --selftest

# Review claim quality against a heavy user's data without sending them anything.
python recap_main.py --fake-user szhang

# Fully standalone: no EnneadTab import at all. Works on any machine.
python recap_main.py --log-json some_log.json --out-dir ./out --today 2026-08-03
```

```bash
python -m unittest discover -s Apps/lib/DumpScripts/recap -p "check_*.py"
```

`--dry-run` is the default. `--fake-user` forces it — computing against someone
else's log must never be able to mail them.

## Architecture

**CPython produces, IronPython consumes.** Everything here runs under CPython 3.
`Apps/lib/EnneadTab/RECAP.py` reads the resulting handoff file inside Revit/Rhino
and shows a toast; it computes nothing.

That split keeps a full log parse off the Revit UI thread, keeps shared-drive I/O
out of the IronPython-safe library, and means both hosts call the *same* function —
so the Rhino↔Revit parity rule holds by construction rather than by remembering to
mirror an edit.

| Module | Responsibility |
|---|---|
| `recap_env` | The only file that touches EnneadTab. Bootstrap, opt-outs, kill switch. |
| `recap_stats` | Raw log dict → windowed metrics. Pure functions, no I/O, no clock. |
| `recap_catalog` | Three-tier join onto the tool catalog; recommendation ranking. |
| `recap_claims` | Candidate claims, scoring, two-register rendering. |
| `recap_email_html` | Newline-free, inline-styled, JS-free HTML body. |
| `recap_state` | Cadence stamps, claim rotation, recommend strikes, first-seen index. |
| `recap_main` | CLI, orchestration, handoff file. |

## Things that will bite you

**The email body must contain zero newlines.** `EMAIL.email` does
`body.replace("\n", "<br>")`, so a pretty-printed template fills the mail with
stray `<br>`. `recap_email_html.assert_sendable()` is the backstop; do not remove it.

**No `border-left`, anywhere** (CLAUDE.md hard rule). A bar chart's baseline axis is
the obvious place to reach for it. The usual substitute, `box-shadow: inset`, is
ignored by Outlook's Word renderer — use a literal 1px `<td bgcolor>` spacer.

**The join is credibility-critical.** If it under-matches, the recap recommends
tools the user demonstrably already uses. Watch `catalog_join_coverage` in the
dry-run output; below ~0.9 the knowledge file is probably lagging the log.

**Streaks are counted in working days, and idle is too.** Mixing the two units means
a weekend silently pushes people out of the warning window exactly when the warning
matters. `working_day_streak` measures the run ending at the last active day and is
deliberately independent of `today`; combine it with `working_days_since_last_run`.

**Import surface is the real deployment risk.** `ENVIRONMENT` reads
`os.environ["USERPROFILE"]` and creates folders at import time, and `EMAIL` pulls in
`EXE`/`IMAGE`/`SPEAK` (`IMAGE` probes `System.Drawing` via `clr`). Nothing in
`DumpScripts/collectors/` imports EnneadTab at all, so this path is unproven per
machine — run `--selftest` before trusting a scheduled run. `--log-json` / `--out-dir`
bypass the library entirely so claim quality can be reviewed anywhere.

## Content rules

Four principles govern every string this package emits. They are documented at
length in the `recap_claims` module docstring, with the anti-patterns kept beside
them as regression guards.

1. **Specificity over name-personalization.** A mail-merged first name is not
   personalization; the claim must be computed from the reader's own data.
2. **Curiosity gap.** The surface carries the claim's shape and withholds which
   tool; the body resolves it. Both render from one `fields` dict on one `Claim`, so
   a surface structurally cannot exist without its resolution.
3. **A real chart.** Shipped as a declarative payload for NotificationHost to render
   (phase 5), and as an inline CSS bar chart in the email.
4. **Loss aversion over absence-nagging.** Frame the asset at risk, never the
   reader's behaviour — and only warn about a loss that code actually enforces.

The honesty constraint binds all four: a gap must resolve, a superlative must be
computed, and a threatened loss must be real. `coins_at_risk` therefore stays
disabled until the EnneadTab bank is repaired and a decay rule has actually run.

## Not yet built

- Phase 2: monthly email send (needs `is_silent` on `EMAIL.email` — it currently
  calls `SPEAK.speak` unconditionally and would make the machine talk out loud).
- Phase 3: streak claims are implemented; the loss-aversion frequency cap is wired.
- Phase 4: shared rollup, team aggregate, and the peer claim types. Peer claims are
  *unbuildable* today rather than built-and-filtered, so they cannot leak.
- Phase 5: `chart=` on `NOTIFICATION.messenger` and the NotificationHost renderer.
  Requires rebuilding `NotificationHost.exe`.
- ~~Phase 6: the bank / economy / leaderboard.~~ **SHIPPED 2026-08-06** (PR #95) — the
  sync-time session card plus a real EnneadTab-Bank client. But it has never run: no
  live Revit/Rhino test, and every Bank call 401s until `DESKTOP_TOKEN_SECRET` is
  provisioned. Read `docs/plans/2026-08-07-session-card-bank-desktop-handoff.md`
  **before** touching it or assuming the economy works.

`coins_at_risk` (see `recap_claims.LOSS_AVERSION_TYPES`) still has no builder. The
condition on it has moved rather than cleared: the bank now exists, so what it waits on
is a live ledger with a decay rule that has actually run — a threatened loss must be one
the code enforces. Handoff §8 tracks that.

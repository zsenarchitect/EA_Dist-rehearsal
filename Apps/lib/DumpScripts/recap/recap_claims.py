"""Pick the one fact the recap leads with, and render it in two registers.

THE CORE IDEA
-------------
"Specific" and "curiosity gap" only look contradictory. They are resolved by
splitting a claim across two layers:

  * SPECIFIC means the claim is computed from this reader's own data -- the
    opposite of a mail-merged first name. It does NOT mean fully disclosed.
  * The SURFACE (email subject, toast line 1) carries the claim's shape: real
    number, real comparison, real timeframe. It withholds the resolution --
    which tool.
  * The BODY delivers the resolution.

Both renderings come from ONE `fields` dict on ONE Claim object, so a surface
structurally cannot exist without its body. "The gap always resolves" is a
property of the data model here, not a line on a review checklist.

ANTI-PATTERNS (regression guards -- do not let these back in)
------------------------------------------------------------
  BAD  "Sen, your July EnneadTab recap"
       Generic. The only personal token is a mail-merged name. Spam shape.
  BAD  "You used Block Modelization 231x more than average in July"
       Specific but fully resolved. Nothing left to open the email for.
  BAD  "You have not used EnneadTab for 10 days, come back"
       Frames the reader as delinquent and asks for a favour.
  GOOD "One tool you ran 231x more than the rest of the office in July."
  GOOD "You're about to lose your 12-day streak."
"""

import math


# Peer-dependent claim types. These are SUPPRESSED ENTIRELY -- never softened
# into vague wording -- when peer data is unavailable. There is deliberately no
# "you might be the #1 user" copy path.
PEER_CLAIM_TYPES = ("ratio_vs_office", "office_rank_1", "lone_wolf", "rank_slipping")

# Claims that reference inactivity. Only these may do so, and only inside the
# frequency cap enforced by recap_state.loss_aversion_allowed.
LOSS_AVERSION_TYPES = ("streak_at_risk", "streak_lost", "coins_at_risk", "rank_slipping")

# Minimum absolute volume before ANY comparative claim is allowed. Without this
# floor, "3x the average" fires on n=3 -- technically true, reads as a lie.
MIN_RUNS_FOR_COMPARATIVE = 25
MIN_TOOL_RUNS = 10
COLD_START_RUNS = 20

# time_saved is the module's first AUTHORED-magnitude claim (every other number
# is measured from the log or suppressed). Because the multiplier is authored,
# it carries gates the measured claims do not need: a floor on how many distinct
# tools with a trustworthy (med+) baseline contribute, a ceiling on any single
# tool's share of the total so one authored constant cannot become the headline,
# and a materiality floor in hours.
MIN_BASELINE_TOOLS = 5
MIN_BASELINE_COVERAGE = 0.5
MAX_SINGLE_TOOL_SHARE = 0.5
MIN_SAVED_SECONDS = 3600.0

_BASE_SCORE = {
    "ratio_vs_office": 1.00,
    "office_rank_1": 0.95,
    "lone_wolf": 0.90,
    "streak_at_risk": 0.88,
    "streak_lost": 0.80,
    "self_growth": 0.70,
    "time_in_tools": 0.60,
    # Authored magnitude -> scored just below the measured time_in_tools so a
    # real, measured claim wins the headline over an estimated one on a tie.
    "time_saved": 0.58,
    "blind_spot": 0.55,
    "breadth": 0.50,
    "cold_start": 0.20,
}

_MAGNITUDE_CAP = {
    "ratio_vs_office": 50.0,
    "self_growth": 5.0,
    "time_in_tools": 8.0,
    # Monthly saved-hours saturate later than time_in_tools' 8h -- a busy month
    # of batch tools can plausibly clear a working week. Sized for the month
    # figure the claim scores on (not the far larger lifetime number).
    "time_saved": 40.0,
    "breadth": 30.0,
    "streak_at_risk": 30.0,
    "streak_lost": 30.0,
    "blind_spot": 20.0,
}


class Claim(object):
    """One candidate headline. Surface and body share a single fields dict."""

    def __init__(self, claim_type, fields, surface, body, tool=None, chart=None):
        self.type = claim_type
        self.fields = fields
        self._surface = surface
        self._body = body
        self.tool = tool
        self.chart = chart or {}
        self.score = 0.0
        self.rejected_reason = None

    def render_surface(self):
        """Gapped. Goes in the subject line / toast line 1."""
        return self._surface.format(**self.fields)

    def render_body(self):
        """Resolved. Goes in the email body / clicked-through digest."""
        return self._body.format(**self.fields)

    def is_loss_aversion(self):
        return self.type in LOSS_AVERSION_TYPES

    def __repr__(self):
        return "<Claim {} score={:.3f}>".format(self.type, self.score)


# --------------------------------------------------------------------- scoring

def _confidence(count, floor):
    """Caps a claim's score until it has enough underlying volume."""
    if floor <= 0:
        return 1.0
    return min(1.0, float(count) / float(floor))


def _magnitude(delta, claim_type):
    cap = _MAGNITUDE_CAP.get(claim_type, 10.0)
    if delta <= 0:
        return 0.0
    return min(1.0, math.log(1.0 + delta) / math.log(1.0 + cap))


def _rotation(claim_type, recent_types, has_alternatives):
    """Stop the same trick repeating. A gap used twice running is a tell."""
    if claim_type in recent_types[:2] and has_alternatives:
        return 0.0
    if claim_type in recent_types[2:5]:
        return 0.6
    return 1.0


def score_claims(claims, recent_types):
    for claim in claims:
        others = [c for c in claims if c.type != claim.type]
        base = _BASE_SCORE.get(claim.type, 0.5)
        confidence = claim.fields.get("_confidence", 1.0)
        magnitude = claim.fields.get("_magnitude", 1.0)
        rotation = _rotation(claim.type, recent_types, bool(others))
        claim.score = base * confidence * magnitude * rotation
    claims.sort(key=lambda c: (-c.score, c.type))
    return claims


# ------------------------------------------------------------- claim builders

def _build_self_growth(metrics, catalog, joined):
    """One tool's use grew sharply month over month."""
    best = None
    for key, (was, now) in (metrics.get("mom_delta_by_tool") or {}).items():
        if was < 5 or now < 15:
            continue
        growth = float(now) / float(was)
        if growth < 1.6:
            continue
        if best is None or growth > best[1]:
            best = (key, growth, was, now)
    if best is None:
        return None

    key, growth, was, now = best
    name = _display_name(key, catalog, joined)
    if not name:
        return None

    word = "tripled" if growth >= 3 else ("doubled" if growth >= 2 else "jumped")
    fields = {
        "tool": name,
        "was": was,
        "now": now,
        "growth": "{:.1f}".format(growth),
        "word": word,
        "month": metrics["month_label"],
        "_confidence": _confidence(now, MIN_TOOL_RUNS),
        "_magnitude": _magnitude(growth, "self_growth"),
    }
    return Claim(
        "self_growth", fields,
        surface="Your use of one tool {word} in {month}. It probably isn't the one you'd guess.",
        body="{tool} went from {was} runs to {now} -- {growth}x in a single month.",
        tool=name,
        chart={"title": "{} vs the month before".format(name),
               "series": [{"label": "Previous month", "value": was},
                          {"label": metrics["month_label"], "value": now}],
               "highlight": 1},
    )


def _build_time_in_tools(metrics, catalog, joined):
    """One tool consumed a striking amount of wall-clock time."""
    month = metrics["month"]
    if month.get("duration_parse_coverage", 0.0) < 0.8:
        return None  # `duration` is a formatted string; refuse on bad coverage.
    by_tool = month.get("seconds_by_tool") or {}
    if not by_tool:
        return None
    key, seconds = max(by_tool.items(), key=lambda kv: kv[1])
    if seconds < 1800:
        return None
    name = _display_name(key, catalog, joined)
    if not name:
        return None

    hours = seconds / 3600.0
    runs = month["runs_by_tool"].get(key, 0)
    fields = {
        "tool": name,
        "hours": "{:.1f}".format(hours),
        "runs": runs,
        "avg": _readable_seconds(seconds / runs) if runs else "-",
        "month": metrics["month_label"],
        "_confidence": _confidence(runs, MIN_TOOL_RUNS),
        "_magnitude": _magnitude(hours, "time_in_tools"),
    }
    return Claim(
        "time_in_tools", fields,
        surface="One tool quietly ate {hours} hours of your {month}.",
        body="{tool} -- {hours} hours across {runs} runs, averaging {avg} each.",
        tool=name,
    )


def _build_time_saved(metrics, catalog, joined):
    """Estimated time the reader's automation saved them this month.

    The ONLY claim whose magnitude is authored (a curated manual-effort baseline)
    rather than measured. Every guard below exists to keep an authored number
    from overstating: the same volume + join-quality floors the comparative
    claims use, PLUS a distinct-tools floor and a single-tool-share ceiling so the
    figure cannot rest on one hand-authored constant. The number consumed here is
    already graded to med+ confidence (metrics["savings_claim"]).
    """
    savings = metrics.get("savings_claim")
    if not savings:
        return None

    month = metrics["month"]
    if month.get("total_runs", 0) < MIN_RUNS_FOR_COMPARATIVE:
        return None
    # A rotted catalog join understates real activity and would overstate the
    # coverage denominator -- suppress rather than compute on it.
    if joined.get("coverage", 1.0) < 0.9:
        return None
    if savings.get("baseline_coverage", 0.0) < MIN_BASELINE_COVERAGE:
        return None
    if savings.get("distinct_tools", 0) < MIN_BASELINE_TOOLS:
        return None
    if savings.get("seconds_saved", 0.0) < MIN_SAVED_SECONDS:
        return None
    if savings.get("max_share", 1.0) > MAX_SINGLE_TOOL_SHARE:
        return None

    contributors = savings.get("contributors") or []
    if not contributors:
        return None
    top = contributors[0]
    name = _display_name_by_script(top["script"], catalog)
    if not name:
        return None

    fields = {
        "band": _band_hours(savings["seconds_saved"]),
        "month": metrics["month_label"],
        "tools": savings["distinct_tools"],
        "tool": name,
        "tool_runs": top["runs"],
        "assume": _readable_seconds(top["assumed_seconds"]),
        "_confidence": 1.0,
        "_magnitude": _magnitude(savings["seconds_saved"] / 3600.0, "time_saved"),
    }
    # Two-register: the surface discloses the estimated total but WITHHOLDS which
    # tool drove it (the curiosity gap resolves on a tool, never on the number);
    # the body names the tool and surfaces the per-run assumption so the estimate
    # is auditable by the reader, not just in the dry run.
    return Claim(
        "time_saved", fields,
        surface="EnneadTab saved you an estimated {band} in {month} -- one tool did most of it.",
        body=("Roughly {band}, estimated across {tools} tools you used in {month}. "
              "The biggest share was {tool}: {tool_runs} runs, assuming about "
              "{assume} each by hand."),
        tool=name,
    )


def _build_breadth(metrics, catalog, joined, peer_median=None):
    """The user reached for an unusually wide set of tools."""
    month = metrics["month"]
    distinct = month.get("distinct_tools", 0)
    if distinct < 15:
        return None
    fields = {
        "distinct": distinct,
        "month": metrics["month_label"],
        "_confidence": _confidence(month.get("total_runs", 0), MIN_RUNS_FOR_COMPARATIVE),
        "_magnitude": _magnitude(distinct, "breadth"),
    }
    if peer_median:
        fields["median"] = peer_median
        body = ("You used {distinct} different EnneadTab tools in {month}. "
                "The office median is {median}.")
    else:
        body = "You used {distinct} different EnneadTab tools in {month}. Here they are."
    return Claim(
        "breadth", fields,
        surface="You reached for {distinct} different EnneadTab tools in {month}.",
        body=body,
    )


def _build_blind_spot(metrics, recommendations, team_adoption=None):
    """A tool the user has never opened, that others rely on."""
    if not recommendations:
        return None
    top = recommendations[0]
    adoption = (team_adoption or {}).get(top.get("script"))
    fields = {
        "tool": top.get("alias"),
        "doc": top.get("doc_line") or "",
        "tab": top.get("tab") or "",
        "_confidence": 1.0,
        "_magnitude": 0.55,
    }
    if adoption:
        people = int(round(adoption))
        fields["people"] = people
        fields["_magnitude"] = _magnitude(people, "blind_spot")
        surface = "{people} people on your team use a tool you've never opened."
        body = "{tool} -- {doc} Find it under the {tab} panel."
    else:
        surface = "There's a tool in your own toolbar you've never opened once."
        body = "{tool} -- {doc} Find it under the {tab} panel."
    return Claim("blind_spot", fields, surface=surface, body=body,
                 tool=top.get("alias"))


def _build_streak_at_risk(metrics):
    """The streak is alive but idling. Loss aversion, not absence-nagging.

    Idle is measured in WORKING days to match how the streak itself is
    counted -- gating on calendar days would silently skip anyone whose gap
    spanned a weekend.
    """
    streak = metrics.get("streak", 0)
    idle = metrics.get("working_days_idle")
    # idle == 1: today is idle, the run is still alive -- this is the ONLY
    # moment the warning is both true and actionable. idle == 0 means they
    # already worked today (nothing at risk); idle >= 2 means it is already
    # gone, which is `streak_lost`, not `streak_at_risk`.
    if streak < 5 or idle != 1:
        return None
    fields = {
        "streak": streak,
        "_confidence": 1.0,
        "_magnitude": _magnitude(streak, "streak_at_risk"),
    }
    return Claim(
        "streak_at_risk", fields,
        surface="Your {streak}-day EnneadTab streak ends tomorrow.",
        body=("You've used EnneadTab on {streak} working days in a row. "
              "One more working day without it and the streak resets to zero."),
    )


def _build_streak_lost(metrics, previous_streak):
    """The run is over. Report the asset lost, never the reader's absence."""
    idle = metrics.get("working_days_idle")
    if idle is None or idle < 2 or idle > 10:
        return None
    # The run that just ended is the one still sitting in metrics["streak"];
    # `previous_streak` is the persisted best, used only when it is larger.
    lost = max(int(metrics.get("streak", 0)), int(previous_streak or 0))
    if lost < 10:
        return None
    fields = {
        "streak": lost,
        "_confidence": 1.0,
        "_magnitude": _magnitude(lost, "streak_lost"),
    }
    return Claim(
        "streak_lost", fields,
        surface="You just lost a {streak}-day streak.",
        body="Your {streak}-working-day run ended. Current streak: 0.",
    )


def _build_cold_start(recommendations):
    """New user. No comparatives, no invented numbers, no fake superlative."""
    if not recommendations:
        return None
    fields = {
        "count": len(recommendations),
        "_confidence": 1.0,
        "_magnitude": 1.0,
    }
    return Claim(
        "cold_start", fields,
        surface="{count} EnneadTab tools most people wish they'd found sooner.",
        body="You're just getting started. These three are the usual first stops.",
    )


# ----------------------------------------------------------------- entry point

def select(metrics, catalog, joined, recommendations,
           state=None, peer_data=None, allow_loss_aversion=True,
           previous_streak=0):
    """Pick the headline claim. Returns (chosen, all_candidates).

    `peer_data` is None in every phase before the shared rollup exists, which
    is exactly why the peer claim types are absent from the builder list below
    rather than being built and then filtered -- an unbuildable claim cannot
    accidentally be rendered.
    """
    state = state or {}
    recent = []
    if state:
        from recap_state import recent_claim_types
        recent = recent_claim_types(state, count=5)

    candidates = []

    # Cold start short-circuits everything. A near-empty log cannot support a
    # superlative, and fabricating one is the worst thing this module could do.
    if metrics.get("total_runs_ever", 0) < COLD_START_RUNS:
        claim = _build_cold_start(recommendations)
        if claim:
            candidates.append(claim)
        scored = score_claims(candidates, recent)
        return (scored[0] if scored else None), scored

    if allow_loss_aversion:
        for builder in (
            lambda: _build_streak_at_risk(metrics),
            lambda: _build_streak_lost(metrics, previous_streak),
        ):
            claim = builder()
            if claim:
                candidates.append(claim)

    # A lapsing user has no great month to celebrate; leading with a
    # superlative would read as tone-deaf. Loss aversion REPLACES the
    # superlative rather than stacking with it.
    if any(c.is_loss_aversion() for c in candidates):
        scored = score_claims(candidates, recent)
        return (scored[0] if scored else None), scored

    peer_median = None
    if peer_data:
        peer_median = peer_data.get("median_distinct_tools")

    for claim in (
        _build_self_growth(metrics, catalog, joined),
        _build_time_in_tools(metrics, catalog, joined),
        _build_time_saved(metrics, catalog, joined),
        _build_breadth(metrics, catalog, joined, peer_median),
        _build_blind_spot(metrics, recommendations,
                          (peer_data or {}).get("team_adoption")),
    ):
        if claim:
            candidates.append(claim)

    # Guardrail: no comparative claim at all below the volume floor.
    if metrics["month"].get("total_runs", 0) < MIN_RUNS_FOR_COMPARATIVE:
        for claim in candidates:
            if claim.type in ("breadth", "self_growth", "time_saved"):
                claim.rejected_reason = "below MIN_RUNS_FOR_COMPARATIVE"
        candidates = [c for c in candidates if c.rejected_reason is None]

    scored = score_claims(candidates, recent)
    return (scored[0] if scored else None), scored


# --------------------------------------------------------------------- helpers

def _display_name(tool_key, catalog, joined):
    """Human-facing name for a normalized log key, via the catalog join."""
    script_path = catalog["by_alias"].get(tool_key)
    if script_path is None:
        return None
    entry = catalog["tools"].get(script_path)
    return entry.get("alias") if entry else None


def _display_name_by_script(script_path, catalog):
    """Human-facing name for a script_path (savings are already script-keyed)."""
    entry = catalog["tools"].get(script_path)
    return entry.get("alias") if entry else None


def _band_hours(seconds):
    """Coarse, banded hours -- an authored estimate must not wear a decimal.

    A ".1f" hour reads as measured; a range reads as the estimate it is.
    """
    hours = seconds / 3600.0
    if hours < 2:
        return "a couple of hours"
    step = 5 if hours < 40 else 10
    low = int(hours // step) * step
    if low <= 0:
        low = 1
    return "{}-{} hours".format(low, low + step)


def _readable_seconds(seconds):
    if seconds < 60:
        return "{:.0f}s".format(seconds)
    if seconds < 3600:
        return "{:.0f}m".format(seconds / 60.0)
    return "{:.1f}h".format(seconds / 3600.0)

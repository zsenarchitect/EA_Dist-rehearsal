"""EnneadTab usage recap -- fleet-baseline fetch (producer side).

The ONE place the recap producer talks to the network for time-saved baselines.
It GETs the InfraWatch per-tool median of user-reported by-hand times and writes
the response verbatim to ``fleet_time_baselines.json`` next to the curated seed,
where ``recap_savings.load_fleet_baselines`` reads it. Reader and writer are kept
deliberately decoupled: the reader is disk-only (its docstring: "the producer
makes no HTTP call"), so a network hiccup can never crash the recap -- it just
reads a stale-or-absent file and falls back to the seed.

Runs under CPython 3 from Task Scheduler (the producer runtime), so plain
``urllib.request`` is enough -- none of the IronPython urllib fallback ladder that
LOG.py needs inside Revit/Rhino.

Contract, all failure-soft:
  * A valid 200 JSON object OVERWRITES the file (atomically: temp + replace), so a
    crash mid-write can't leave a truncated file -- and even if it did, the reader
    fails soft on a parse error.
  * ANY failure (offline, non-200, non-JSON, not an object) leaves an existing
    good file UNTOUCHED and returns a status dict -- a previous good fetch beats
    nothing, and this run just reuses it.
  * The body is saved byte-for-byte: metadata lives under "_"-prefixed keys the
    reader skips, every other key is a script_path -> {manual_seconds, n}. This
    module does NOT reshape it, so the server owns the schema.
"""

import json
import os

try:                                  # CPython 3 (producer); guarded for safety.
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:                   # pragma: no cover - Py2 path, unused here.
    from urllib2 import Request, urlopen, URLError, HTTPError


# Direct vercel domain, NOT enneadtab.com: the EnneadTab-Home proxy 302-redirects
# GETs to SSO, so every no-auth fleet READ hits the vercel host straight, exactly
# like SYSTEM.py:233 (publish-status/history). Keep this base in lockstep with
# that precedent; the ingest POST (LOG.py) legitimately uses enneadtab.com because
# the proxy passes POSTs through without the SSO redirect.
FLEET_BASELINES_URL = (
    "https://infrawatch-ennead-projects.vercel.app/infra/api/time-baselines"
)

FLEET_FILE = "fleet_time_baselines.json"

DEFAULT_TIMEOUT = 10.0                # seconds; a slow endpoint must not stall Revit startup upstream


def _dest_path(dest=None):
    if dest is not None:
        return dest
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), FLEET_FILE)


def refresh_fleet_baselines(url=None, dest=None, timeout=DEFAULT_TIMEOUT):
    """Fetch the fleet baselines and write them to disk. Never raises.

    Returns a small status dict for the dry-run report / logs:
        {"ok": bool, "written": bool, "tool_count": int|None,
         "path": str, "reason": str|None}
    ``ok`` is whether the fetch+parse succeeded; ``written`` is whether the file
    was (re)written. On failure both the existing file and ``ok=False`` tell the
    operator what happened -- graceful to the recap, never silent to the log.
    """
    target = _dest_path(dest)
    endpoint = url or FLEET_BASELINES_URL
    status = {"ok": False, "written": False, "tool_count": None,
              "path": target, "reason": None}

    try:
        request = Request(endpoint, headers={"User-Agent": "EnneadTab-recap-producer"})
        response = urlopen(request, timeout=timeout)
        code = getattr(response, "getcode", lambda: 200)()
        raw = response.read()
    except HTTPError as error:
        status["reason"] = "HTTP {}".format(getattr(error, "code", "?"))
        return status
    except URLError as error:
        status["reason"] = "network: {}".format(getattr(error, "reason", error))
        return status
    except Exception as error:                       # pragma: no cover - defensive
        status["reason"] = "{}: {}".format(type(error).__name__, error)
        return status

    if code != 200:
        status["reason"] = "non-200: {}".format(code)
        return status

    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        body = json.loads(raw)
    except Exception as error:
        status["reason"] = "unparseable body: {}".format(error)
        return status
    if not isinstance(body, dict):
        status["reason"] = "body is not a JSON object"
        return status

    status["ok"] = True
    status["tool_count"] = sum(1 for key in body if not str(key).startswith("_"))

    # Atomic write: a real tool_path key or none, either way it is a valid file.
    # An all-metadata body (no fleet data yet) writes cleanly and the reader turns
    # it into {} -> merge falls back to the seed. Same-dir temp so os.replace is a
    # rename, not a cross-device copy.
    tmp = target + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(body, handle, indent=2)
        os.replace(tmp, target)
        status["written"] = True
    except Exception as error:
        status["reason"] = "write failed: {}".format(error)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return status

    return status


if __name__ == "__main__":            # manual probe: python recap_fleet_fetch.py
    import sys
    result = refresh_fleet_baselines()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)

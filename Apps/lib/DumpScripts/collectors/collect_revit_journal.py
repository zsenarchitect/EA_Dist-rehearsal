"""Upload stable Revit journal files to InfraWatch (Plane B, weekly).

Stdlib-only CPython 3. Discovers closed-session journals (mtime >= 7 days),
dedupes via local sha256 table, uploads via presigned blob PUT.

Corpus tiers (size-based, server-tagged):
  0-25 MiB  -> healthy_training   (positive LLM / behavior-cloning corpus)
  25 MiB+   -> negative_health    (negative prompts + model-health troubleshooting)

Must NOT be called from run_all() / run_heavy() / run_events_only() during pilot.
"""

import glob
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infrawatch_common import (  # noqa: E402
    INFRAWATCH_BASE,
    get_machine_name,
    get_username,
    report_error,
)

STABILITY_DAYS = 7
MAX_UPLOAD_BYTES = 26_214_400  # 25 MiB — matches server default
DEFAULT_MAX_OVERSIZE_BYTES = 104_857_600  # 100 MiB — bad-session investigation path
CONFIG_TTL_SEC = 86400
CHUNK_BYTES = 1024 * 1024

_JOURNAL_API = INFRAWATCH_BASE + "/journal"


def _enneadtab_data_dir():
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    return os.path.join(appdata, "Ennead+", "EnneadTab")


def _state_path(filename):
    base = _enneadtab_data_dir()
    if not base:
        return None
    if not os.path.isdir(base):
        try:
            os.makedirs(base)
        except OSError:
            return None
    return os.path.join(base, filename)


def _ea_dist_roots():
    """Walk up from this file looking for EA_Dist / EnneadTab-OS roots."""
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    roots = []
    for _ in range(10):
        if os.path.basename(cur) in ("EA_Dist", "EnneadTab-OS"):
            roots.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return roots


def journal_kill_switch_active():
    for root in _ea_dist_roots():
        if os.path.exists(os.path.join(root, ".journal_collect_kill")):
            return True
    return False


def pilot_bucket(machine_name):
    h = hashlib.md5(machine_name.upper().encode("ascii")).hexdigest()
    return int(h[:8], 16) % 100


def _http_json(method, url, payload=None, timeout=30):
    data = None
    headers = {"X-Collector-Protocol": "2026-05-07"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
        except Exception:
            parsed = {"error": str(e.reason)}
        return e.code, parsed
    except Exception as e:
        return 0, {"error": str(e)}


def get_pilot_config():
    """Cached GET journal/config (rollout, allowlist, size caps)."""
    path = _state_path("journal_pilot_config.json")
    now = time.time()
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if now - cached.get("fetched_at", 0) < CONFIG_TTL_SEC:
                return (
                    int(cached.get("rollout_percent", 0)),
                    cached.get("allowlist") or [],
                    int(cached.get("max_journal_bytes", MAX_UPLOAD_BYTES)),
                    int(
                        cached.get(
                            "max_oversize_journal_bytes",
                            DEFAULT_MAX_OVERSIZE_BYTES,
                        )
                    ),
                )
        except Exception as e:
            report_error("collect_revit_journal.get_pilot_config.cache", str(e))

    status, body = _http_json("GET", _JOURNAL_API + "/config", timeout=15)
    if status != 200:
        report_error(
            "collect_revit_journal.get_pilot_config",
            "config HTTP {}: {}".format(status, body),
        )
        return 0, [], MAX_UPLOAD_BYTES, DEFAULT_MAX_OVERSIZE_BYTES

    percent = int(body.get("rollout_percent", 0))
    allowlist = body.get("allowlist") or []
    if not isinstance(allowlist, list):
        allowlist = []
    max_journal = int(body.get("max_journal_bytes", MAX_UPLOAD_BYTES))
    max_oversize = int(
        body.get("max_oversize_journal_bytes", DEFAULT_MAX_OVERSIZE_BYTES)
    )
    if path:
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "rollout_percent": percent,
                        "allowlist": allowlist,
                        "max_journal_bytes": max_journal,
                        "max_oversize_journal_bytes": max_oversize,
                        "fetched_at": now,
                    },
                    f,
                )
            os.replace(tmp, path)
        except Exception as e:
            report_error("collect_revit_journal.get_pilot_config.save", str(e))
    return percent, allowlist, max_journal, max_oversize


def get_rollout_percent():
    """Backward-compatible wrapper."""
    percent, _allowlist, _mj, _mo = get_pilot_config()
    return percent


def _is_allowlisted(machine_name, allowlist):
    upper = machine_name.upper()
    for host in allowlist or []:
        if str(host).upper() == upper:
            return True
    return False


def is_pilot_enrolled(machine_name, rollout_percent, allowlist=None):
    if _is_allowlisted(machine_name, allowlist):
        return True
    if rollout_percent <= 0:
        return False
    if rollout_percent >= 100:
        return True
    return pilot_bucket(machine_name) < rollout_percent


def load_hash_state():
    path = _state_path("journal_upload_hashes.json")
    if not path or not os.path.isfile(path):
        return {"uploaded_hashes": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "uploaded_hashes" not in data:
            data["uploaded_hashes"] = {}
        return data
    except Exception as e:
        report_error("collect_revit_journal.load_hash_state", str(e))
        return {"uploaded_hashes": {}}


def save_hash_state(state):
    path = _state_path("journal_upload_hashes.json")
    if not path:
        return False
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        report_error("collect_revit_journal.save_hash_state", str(e))
        return False


def discover_journal_paths():
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    pattern = os.path.join(local, "Autodesk", "Revit", "*", "Journals", "journal.*.txt")
    return sorted(glob.glob(pattern))


def revit_version_from_path(path):
    normalized = path.replace("\\", "/")
    for part in normalized.split("/"):
        if part.startswith("Autodesk Revit "):
            return part[len("Autodesk Revit ") :].strip()
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_BYTES)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def post_oversize_metadata(machine_name, username, file_size_bytes, revit_version,
                           journal_path_basename, content_sha256):
    """Enqueue metadata-only when journal exceeds the oversize blob cap."""
    payload = {
        "machine_name": machine_name,
        "username": username,
        "file_size_bytes": file_size_bytes,
        "revit_version": revit_version,
        "journal_path_basename": journal_path_basename,
        "content_sha256": content_sha256,
    }
    status, body = _http_json("POST", _JOURNAL_API + "/oversize", payload)
    if status != 200:
        report_error(
            "collect_revit_journal.post_oversize_metadata",
            "oversize HTTP {}: {}".format(status, body),
        )


def _blob_put(upload_url, path, timeout_sec=120):
    with open(path, "rb") as f:
        blob_data = f.read()
    put_req = urllib.request.Request(
        upload_url,
        data=blob_data,
        headers={"Content-Type": "text/plain"},
        method="PUT",
    )
    with urllib.request.urlopen(put_req, timeout=timeout_sec) as resp:
        return resp.status == 200


def upload_oversize_journal_file(path, machine_name, username, state):
    """25 MiB < size <= oversize cap — full blob upload on oversize queue."""
    file_size = os.path.getsize(path)
    revit_version = revit_version_from_path(path)
    basename = os.path.basename(path)

    try:
        content_sha256 = sha256_file(path)
    except Exception as e:
        report_error("collect_revit_journal.oversize.sha256", "{}: {}".format(path, e))
        return

    if content_sha256 in state.get("uploaded_hashes", {}):
        return

    mtime = os.path.getmtime(path)
    init_payload = {
        "machine_name": machine_name,
        "username": username,
        "journal_path_basename": basename,
        "file_size_bytes": file_size,
        "file_mtime": datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revit_version": revit_version,
        "content_sha256": content_sha256,
    }

    status, body = _http_json("POST", _JOURNAL_API + "/oversize/init", init_payload)
    if status == 403 and body.get("pilot_rejected"):
        return
    if status == 200 and body.get("deduplicated"):
        state.setdefault("uploaded_hashes", {})[content_sha256] = {
            "uploaded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "journal_basename": basename,
            "file_size_bytes": file_size,
            "oversize": True,
        }
        save_hash_state(state)
        return
    if status != 200 or not body.get("upload_url"):
        report_error(
            "collect_revit_journal.oversize.init",
            "init HTTP {}: {}".format(status, body),
        )
        return

    queue_id = body["queue_id"]
    try:
        if not _blob_put(body["upload_url"], path, timeout_sec=300):
            report_error(
                "collect_revit_journal.oversize.blob_put",
                "PUT failed for {}".format(queue_id),
            )
            return
    except Exception as e:
        report_error("collect_revit_journal.oversize.blob_put", str(e))
        return

    complete_payload = {"queue_id": queue_id, "machine_name": machine_name}
    status, body = _http_json(
        "POST", _JOURNAL_API + "/oversize/complete", complete_payload
    )
    if status != 200:
        report_error(
            "collect_revit_journal.oversize.complete",
            "complete HTTP {}: {}".format(status, body),
        )
        return

    state.setdefault("uploaded_hashes", {})[content_sha256] = {
        "uploaded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "journal_basename": basename,
        "file_size_bytes": file_size,
        "oversize": True,
    }
    save_hash_state(state)


def upload_journal_file(path, machine_name, username, state, size_caps=None):
    file_size = os.path.getsize(path)
    revit_version = revit_version_from_path(path)
    basename = os.path.basename(path)

    if size_caps is None:
        _r, _a, max_journal, max_oversize = get_pilot_config()
    else:
        max_journal, max_oversize = size_caps

    if file_size > max_journal:
        if file_size > max_oversize:
            try:
                content_sha256 = sha256_file(path)
            except Exception as e:
                report_error("collect_revit_journal.oversize.sha256", "{}: {}".format(path, e))
                return
            if content_sha256 in state.get("uploaded_hashes", {}):
                return
            post_oversize_metadata(
                machine_name, username, file_size, revit_version,
                basename, content_sha256,
            )
            state.setdefault("uploaded_hashes", {})[content_sha256] = {
                "uploaded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "journal_basename": basename,
                "file_size_bytes": file_size,
                "oversize": True,
                "metadata_only": True,
            }
            save_hash_state(state)
            return
        upload_oversize_journal_file(path, machine_name, username, state)
        return

    try:
        content_sha256 = sha256_file(path)
    except Exception as e:
        report_error("collect_revit_journal.sha256", "{}: {}".format(path, e))
        return

    if content_sha256 in state.get("uploaded_hashes", {}):
        return

    mtime = os.path.getmtime(path)
    init_payload = {
        "machine_name": machine_name,
        "username": username,
        "journal_path_basename": basename,
        "file_size_bytes": file_size,
        "file_mtime": datetime.utcfromtimestamp(mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "revit_version": revit_version,
        "content_sha256": content_sha256,
    }

    status, body = _http_json("POST", _JOURNAL_API + "/init", init_payload)
    if status == 403 and body.get("pilot_rejected"):
        return
    if status == 200 and body.get("deduplicated"):
        state.setdefault("uploaded_hashes", {})[content_sha256] = {
            "uploaded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "journal_basename": basename,
            "file_size_bytes": file_size,
        }
        save_hash_state(state)
        return
    if status != 200 or not body.get("upload_url"):
        report_error(
            "collect_revit_journal.init",
            "init HTTP {}: {}".format(status, body),
        )
        return

    ingest_id = body["ingest_id"]
    upload_url = body["upload_url"]

    try:
        if not _blob_put(upload_url, path):
            report_error(
                "collect_revit_journal.blob_put",
                "PUT failed for {}".format(ingest_id),
            )
            return
    except Exception as e:
        report_error("collect_revit_journal.blob_put", str(e))
        return

    complete_payload = {"ingest_id": ingest_id, "machine_name": machine_name}
    status, body = _http_json("POST", _JOURNAL_API + "/complete", complete_payload)
    if status != 200:
        report_error(
            "collect_revit_journal.complete",
            "complete HTTP {}: {}".format(status, body),
        )
        return

    state.setdefault("uploaded_hashes", {})[content_sha256] = {
        "uploaded_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "journal_basename": basename,
        "file_size_bytes": file_size,
    }
    save_hash_state(state)


def main():
    """Scan eligible journals and upload. Always exits 0 (silent to end user)."""
    try:
        if journal_kill_switch_active():
            return 0

        machine_name = get_machine_name()
        username = get_username()
        rollout, allowlist, max_journal, max_oversize = get_pilot_config()
        if not is_pilot_enrolled(machine_name, rollout, allowlist):
            return 0

        cutoff = time.time() - STABILITY_DAYS * 86400
        state = load_hash_state()
        size_caps = (max_journal, max_oversize)

        for path in discover_journal_paths():
            try:
                if not os.path.isfile(path):
                    continue
                if os.path.getmtime(path) > cutoff:
                    continue
                upload_journal_file(
                    path, machine_name, username, state, size_caps=size_caps
                )
            except Exception as e:
                report_error("collect_revit_journal.per_file", "{}: {}".format(path, e))
    except Exception as e:
        report_error("collect_revit_journal.main", str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())

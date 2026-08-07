#!/usr/bin/env python3
"""
Extract pedestrian / agent trajectory frames from EnneadTab *.flowbin simulation dumps.

Part of EnneadTab-OS (Apps/lib/DumpScripts/flowbin/). Not affiliated with Cherrybrew.

Investigation methodology, findings, limits, and follow-ups: see README.md in this folder.

Reverse-engineered layout (May 2026, sample file 2026-05-08_simulation.flowbin):
- Records occur back-to-back in file order; each starts at byte offset `rs`.
- Header: int32 frame_index, int32 agent_slot_count (h2) — both little-endian.
- Primary graph label at rs+69: 0xFF 0x00, then 1-byte ASCII length, then label text.
- Per-agent samples: for slot k in [0, h2), XYZ doubles at rs + 162 + 68*k (little-endian).

Outputs CSV suitable for charts / GIS / slides; optional JSON summary.

Usage:
  python extract_flowbin.py "path/to/simulation.flowbin"
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PRIMARY_MARKER = (0xFF, 0x00)
SLOT0_OFF = 162
SLOT_STRIDE = 68


def _read_primary_label(data: bytes, rs: int) -> tuple[int, str] | None:
    if rs + 72 > len(data):
        return None
    if data[rs + 69] != PRIMARY_MARKER[0] or data[rs + 70] != PRIMARY_MARKER[1]:
        return None
    ln = data[rs + 71]
    if ln < 1 or ln > 120:
        return None
    if rs + 72 + ln > len(data):
        return None
    raw = data[rs + 72 : rs + 72 + ln]
    if not raw:
        return None
    if not all(32 <= b < 127 for b in raw):
        return None
    try:
        return ln, raw.decode("ascii")
    except UnicodeDecodeError:
        return None


def _candidate_records(data: bytes) -> list[tuple[int, int, int, str]]:
    """Return sorted list of (rs, frame_idx, h2, primary_label)."""
    out: list[tuple[int, int, int, str]] = []
    # Heuristic header guard: h2 in 1..50 matches observed simulation exports.
    for rs in range(0, len(data) - 120):
        frame_idx, h2 = struct.unpack_from("<ii", data, rs)
        if h2 < 1 or h2 > 50:
            continue
        if frame_idx < 0 or frame_idx > 50_000_000:
            continue
        lbl = _read_primary_label(data, rs)
        if lbl is None:
            continue
        out.append((rs, frame_idx, h2, lbl[1]))
    out.sort(key=lambda t: t[0])
    return out


def _valid_xyz(x: float, y: float, z: float) -> bool:
    if math.isnan(x) or math.isnan(y) or math.isnan(z):
        return False
    if math.isinf(x) or math.isinf(y) or math.isinf(z):
        return False
    # Building-scale metres (adjust if your models use different units).
    if abs(x) > 10_000 or abs(y) > 10_000 or abs(z) > 10_000:
        return False
    if abs(x) < 1e-3 and abs(y) < 1e-3:
        return False
    return True


def _extract_secondary_ff_ff(data: bytes, rs: int, reclen: int) -> list[tuple[int, str]]:
    """Auxiliary labels: 0xFF 0xFF, 1-byte length, ASCII (e.g. WA 1)."""
    chunk = data[rs : rs + reclen]
    found: list[tuple[int, str]] = []
    i = 0
    while i + 3 < len(chunk):
        if chunk[i] == 0xFF and chunk[i + 1] == 0xFF:
            ln = chunk[i + 2]
            if 1 <= ln <= 80 and i + 3 + ln <= len(chunk):
                raw = chunk[i + 3 : i + 3 + ln]
                if raw and all(32 <= b < 127 for b in raw):
                    found.append((rs + i, raw.decode("ascii")))
                    i += 3 + ln
                    continue
        i += 1
    return found


def extract_flowbin(data: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cand = _candidate_records(data)
    if not cand:
        raise ValueError("No records matched expected header/primary-label pattern.")

    frames: list[dict[str, Any]] = []
    label_ctr: Counter[str] = Counter()
    h2_ctr: Counter[int] = Counter()
    gap_ctr: Counter[int] = Counter()

    for i, (rs, frame_idx, h2, primary_label) in enumerate(cand):
        reclen = cand[i + 1][0] - rs if i + 1 < len(cand) else len(data) - rs
        label_ctr[primary_label] += 1
        h2_ctr[h2] += 1
        if i:
            gap_ctr[cand[i][0] - cand[i - 1][0]] += 1

        secondary = _extract_secondary_ff_ff(data, rs, reclen)

        agents: list[dict[str, Any]] = []
        for k in range(h2):
            off = SLOT0_OFF + SLOT_STRIDE * k
            if off + 24 > reclen:
                agents.append({"slot": k, "x": None, "y": None, "z": None})
                continue
            x, y, z = struct.unpack_from("<ddd", data, rs + off)
            if _valid_xyz(x, y, z):
                agents.append({"slot": k, "x": x, "y": y, "z": z})
            else:
                agents.append({"slot": k, "x": None, "y": None, "z": None})

        frames.append(
            {
                "byte_offset": rs,
                "frame_index": frame_idx,
                "agent_slot_count": h2,
                "primary_label": primary_label,
                "record_length_bytes": reclen,
                "agents": agents,
                "secondary_labels": [s[1] for s in secondary],
            }
        )

    summary = {
        "file_size_bytes": len(data),
        "frame_count": len(frames),
        "frame_index_min": frames[0]["frame_index"],
        "frame_index_max": frames[-1]["frame_index"],
        "primary_label_counts": dict(label_ctr.most_common()),
        "agent_slot_count_distribution": {str(k): v for k, v in sorted(h2_ctr.items())},
        "record_length_gap_top": [[g, c] for g, c in gap_ctr.most_common(12)],
        "notes": [
            "Coordinates are interpreted as little-endian float64 triplets per agent slot.",
            "Primary label uses bytes [rs+69 ..] as FF 00 <len> <ascii>.",
            "Secondary labels use FF FF <len> <ascii> anywhere inside the record.",
        ],
    }
    return frames, summary


def write_agents_csv(rows: Iterable[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "frame_index",
                "byte_offset",
                "record_length_bytes",
                "primary_label",
                "agent_slot_count",
                "agent_slot",
                "x_m",
                "y_m",
                "z_m",
            ],
        )
        w.writeheader()
        for fr in rows:
            base = {
                "frame_index": fr["frame_index"],
                "byte_offset": fr["byte_offset"],
                "record_length_bytes": fr["record_length_bytes"],
                "primary_label": fr["primary_label"],
                "agent_slot_count": fr["agent_slot_count"],
            }
            for ag in fr["agents"]:
                row = dict(base)
                row["agent_slot"] = ag["slot"]
                row["x_m"] = "" if ag["x"] is None else f"{ag['x']:.12g}"
                row["y_m"] = "" if ag["y"] is None else f"{ag['y']:.12g}"
                row["z_m"] = "" if ag["z"] is None else f"{ag['z']:.12g}"
                w.writerow(row)


def write_frames_json(frames: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(frames, f, indent=2)


def write_summary_json(summary: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Extract agent walking data from EnneadTab .flowbin dumps.")
    ap.add_argument("input", type=Path, help="Path to .flowbin file")
    ap.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Output CSV path (default: <input-stem>_agents.csv next to input)",
    )
    ap.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Optional full frames JSON path (default: <input-stem>_frames.json)",
    )
    ap.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="Optional summary JSON path (default: <input-stem>_summary.json)",
    )
    args = ap.parse_args(argv)

    src = args.input.expanduser()
    if not src.is_file():
        print(f"Input not found: {src}", file=sys.stderr)
        return 2

    data = src.read_bytes()
    frames, summary = extract_flowbin(data)

    stem = src.with_suffix("")
    csv_path = args.csv or Path(str(stem) + "_agents.csv")
    json_path = args.json or Path(str(stem) + "_frames.json")
    summary_path = args.summary or Path(str(stem) + "_summary.json")

    write_agents_csv(frames, csv_path)
    write_frames_json(frames, json_path)
    write_summary_json(summary, summary_path)

    filled = sum(
        1 for fr in frames for ag in fr["agents"] if ag["x"] is not None and ag["y"] is not None and ag["z"] is not None
    )
    slot_rows = sum(int(fr["agent_slot_count"]) for fr in frames)
    print(f"Frames: {len(frames)}  ({summary['frame_index_min']}..{summary['frame_index_max']})")
    print(f"CSV rows written: {slot_rows} (slots); filled XYZ samples: {filled}")
    print(f"CSV:  {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

# `.flowbin` simulation dumps — investigation notes

This folder holds `**extract_flowbin.py**`, a best-effort reader for EnneadTab **pedestrian / agent walking** simulation exports (`*.flowbin`). The format is **proprietary**; there is no separate schema file in-repo. Everything below comes from **binary reverse-engineering** (May 2026) on a representative dump:

`2026-05-08_simulation.flowbin` (~6.2 MB, building circulation labels such as “Stair 3”, “Exit 1”, “WA 1”).

Future agents: treat this README as the **handoff** for how we inferred layout, what is reliable, and what is still heuristic.

---

## High-level picture

- File is a **concatenation of frames** (timesteps). Each frame is one **variable-length binary record**.
- No compression or encryption observed at file start; data is mostly **little-endian** structs and **length-prefixed ASCII**.
- Content aligns with **routing graph regions** (stairs, exits, sources) plus **3D positions** in **metre-scale** coordinates (typical ~60–110 m horizontal, ~−7.5 m vertical on one slab).

---

## Investigation process (reproducible mindset)

1. **Inspect size and entropy**
  Confirm non-text (`*.flowbin` not readable as UTF-8). Note total bytes for sanity checks.
2. **Hex / ASCII passes**
  Scan for printable runs; identify recurring tokens (“Stair 3”, “Exit 1”, “WA 1”). Notice **binary prefixes** immediately before strings (`FF 00` + length byte + ASCII; also `FF FF` + length + ASCII).
3. **Anchor on repeating strings**
  Find offsets of the same label (e.g. every occurrence of `FF 00 07 "Stair 3"`). Compute **gaps** between occurrences; dominant gap reveals **nominal record stride** (354 B for early segment) with occasional ±2 B jitter.
4. **Sync record starts**
  Hypothesis: strings sit at **fixed offset inside each record**. Subtract offset from marker position → candidate **record base `rs`**. Validate: at `rs`, first fields look like structured header (two `int32`s), and at `rs + 69` the `FF 00` primary label begins.
5. **Decode header**
  At `rs`:  
   `struct.unpack("<ii", data[rs:rs+8])` → `(frame_index, agent_slot_count)`.  
   Observed: `frame_index` runs **0 … N−1** contiguously across the whole file for one export; second field **correlates with record byte length** (~70 bytes × slot count, ± small constant).
6. **Find floats that look like coordinates**
  Search for `float64` triplets `(x, y, z)` where `z` clusters near slab elevations (e.g. −7.4676 m) and `x,y` sit in plausible building extents. Note **byte offset modulo record** for stable hits → `**162 + 68*k`** for agent slot `k`.
7. **Validate across segments**
  Early frames often use **small** `agent_slot_count` (e.g. 5); later segments grow (10, 14, …, 30). Record length grows accordingly. **Do not assume** one stride tiles the entire file from byte 0 without verifying header + primary label at each boundary — use **scan-for-valid-record** or sequential parse using detected gaps.
8. **Secondary strings**
  Inside each record, scan for `**FF FF`** length-prefixed ASCII (“WA 1”, etc.). These are useful for UX/presentation but are **not** the primary region label.
9. **Document uncertainty**
  Slots beyond the first few may **not** hold `(x,y,z)` doubles at `162+68*k`; higher `agent_slot_count` records likely mix **other fields**. Empty XYZ cells in CSV output are expected until layout for those slots is fully decoded.

---

## Layout summary (as implemented in `extract_flowbin.py`)


| Topic                   | Detail                                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Endianness**          | Little-endian for integers and IEEE-754 doubles.                                                                                  |
| **Record start**        | Byte offset `rs` where a valid frame begins (found by scanning for header + primary marker alignment).                            |
| **Header**              | `int32 frame_index`, `int32 agent_slot_count` (`h2`).                                                                             |
| **Primary label**       | Starts at `**rs + 69`**: bytes `0xFF 0x00`, then `**uint8` length** `L`, then `**L` ASCII bytes** (graph region / waypoint name). |
| **Agent slots**         | For slot index `k` in `[0, h2)`, interpreter tries `**float64 x,y,z`** at `**rs + 162 + 68*k`**.                                  |
| **XYZ validity filter** | Rejects NaN/inf and absurd magnitudes; requires non-trivial `x,y` — reduces garbage from misaligned doubles.                      |
| **Secondary labels**    | Anywhere in `[rs, rs + record_length)`: `0xFF 0xFF`, `uint8` length, ASCII.                                                       |
| **Record length**       | For parsing we use **distance to next record start**: `next_rs - rs` (last record runs to EOF).                                   |


---

## Empirical findings from the sample file

- **Frame count**: 3 733 records (`frame_index` **0 … 3732**).
- **Primary labels** (counts vary by simulation phase): e.g. **Exit 1**, **Stair 1–3**, **Source 5**.
- **Secondary strings**: dominated by **WA 1**, plus **Source 3**, **Exit 1** (embedded occurrences).
- `**agent_slot_count` distribution**: starts at **5** for an initial block (~151 frames), then increases through values such as **10, 14, 18, …, 30**; record size tracks slot count.
- **Filled XYZ rate**: many declared slots do **not** decode as coordinates with the current stride rule — especially when `h2` is large. **Slots 0–2** often decode cleanly during early **h2 = 5** segments (good for trajectories / animations).

---

## Outputs of `extract_flowbin.py`

Default outputs are written **next to the input file** (unless overridden):


| Output                | Contents                                                                              |
| --------------------- | ------------------------------------------------------------------------------------- |
| `<stem>_agents.csv`   | One row per `(frame_index, agent_slot)` with `primary_label`, optional `x_m,y_m,z_m`. |
| `<stem>_frames.json`  | Nested frames including `secondary_labels`.                                           |
| `<stem>_summary.json` | Counts, `agent_slot_count` histogram, top record-length gaps.                         |


---

## Usage

From repo root (adjust paths):

```bash
python Apps/lib/DumpScripts/flowbin/extract_flowbin.py "path/to/simulation.flowbin"
```

Optional: `--csv`, `--json`, `--summary` to set explicit output paths.

---

## Related backlog

- Tracked in `**github/Personal/senzhang-todo**` (`src/data.seed.ts`, org `**ennead-llp**`, item **Flow simulation presentation webapp**, DDL **2026-05-15**).

---

## Follow-ups for future investigation

- Infer **full per-slot struct** when `h2 > 5` (offsets beyond `162+68*k`, or non-double fields).
- Confirm whether `**agent_slot_count`** means physical agents vs capacity vs graph cardinality per timestep.
- Cross-check units (metres vs feet) against Revit export settings for the originating model.
- If newer dumps break parsing, re-run steps **3–6** above on a small hex slice and update offsets/constants in `**extract_flowbin.py`** and this README.


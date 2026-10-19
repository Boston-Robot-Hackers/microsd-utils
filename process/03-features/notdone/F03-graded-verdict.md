# Feature description for feature F03

Feature file name must be `FNN-<slug>.md` where `NN` matches the feature number.
# F03 — Graded health verdict with a random-I/O test
**Priority**: Medium
**Date Created:** 2026-10-18
**Done:** no
**Tasks File Created:** yes
**Tests Written:** yes
**Test Passing:** no
**Description**: Replace F01's single *still OK* with a graded verdict, and
add a short random 4 KB I/O test, which is the most wear-sensitive signal
available without SMART data.

### Grades

The verdict is **EXCELLENT**, **GOOD**, **FAIR** or **RETIRE**. It is the
*worst* of the sequential grade and the random grade.

| Grade | Write | Read | Random read | Random write |
|---|---|---|---|---|
| EXCELLENT | ≥ 30 MB/s | ≥ 60 MB/s | ≥ 4000 IOPS (A2) | ≥ 2000 IOPS (A2) |
| GOOD | ≥ 20 | ≥ 40 | ≥ 1500 (A1) | ≥ 500 (A1) |
| FAIR | ≥ 10 | ≥ 20 | below A1 | below A1 |
| RETIRE | below FAIR, or any error | | — | — |

- **Random I/O never retires a card on its own.** Many older cards predate the
  A1 class; slow random I/O means "sluggish as a Pi system disk", so it caps
  the grade at FAIR.
- **Thresholds are named constants**, to be recalibrated after the TF03.6
  hardware run.

### The random test

- **Random read** (both modes): 4 KB reads at random 4 KB-aligned offsets
  across the whole card for a fixed time (default 30 s). Reports IOPS.
- **Random write** (destructive mode only): 4 KB writes at random offsets in
  a 1 GB scratch region at the start of the card, for a fixed time (default
  30 s), *before* the full write pass, which then overwrites it.
- Offsets come from a seeded generator, so a run is reproducible.
- Read errors and write errors count as errors, which means RETIRE.

### Report

```
Write   : 62,600 MB in 1160 s, 54.0 MB/s, 0 bad chunks
Verify  : 62,600 MB in 870 s, 72.0 MB/s, 0 bad chunks
Random  : read 2,340 IOPS (A1), write 610 IOPS (A1)
Verdict: GOOD
  - sequential: EXCELLENT (write 54.0 MB/s, read 72.0 MB/s)
  - random: GOOD (A1 level)
  - not brand new: 2 partitions, factory has 1
```

- In read-only mode the grade uses read speeds only and says so:
  `Verdict: GOOD (read-only: write not measured)`.
- A factory-fresh card adds the note `Looks brand new` under the verdict.
- Exit codes: 0 for EXCELLENT / GOOD / FAIR, 2 for RETIRE, 1 for errors.

### Out of scope

Reading the card's rated class from the card itself (not available through
the USB reader), and a `--rated-speed` option.

## How to Demo
**Setup**: `uv sync` done; the NORELSYS reader in its port with a card.

**Steps**:
1. `make validate` — the report has a `Random` line (read only) and a graded
   verdict marked read-only.
2. `make stress` on a spare card — the `Random` line has read and write IOPS
   and the verdict lists both the sequential and random grades.

**Expected output**: a graded verdict whose reasons name the measurement that
set the grade. The 64 GB test card (54 MB/s write, 72 MB/s read) grades
EXCELLENT sequentially; its random grade is unknown until measured.

## Process Gate
After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

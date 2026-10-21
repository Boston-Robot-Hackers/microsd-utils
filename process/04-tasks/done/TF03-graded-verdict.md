# TF03 Graded health verdict with a random-I/O test for Feature F03
**Date Created:** 2026-10-18

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

**Builds on F01**: the random passes take the same `read_at` / `write_at`
callables as `passes.py`, all device access still goes through `open_card`,
and the grading replaces `verdict.decide`.

## TF03.0 — Random read pass
**Status**: done
**Description**: In a new `random_io.py`: a seeded generator of 4 KB-aligned
offsets within a region, and `random_read_pass(read_at, region_bytes,
duration_s, clock)` that issues 4 KB reads until the time is up. Returns a
`RandomResult` (operations, seconds, error offsets, IOPS). The clock is
injected so tests don't sleep.

**Test**: offsets are aligned, inside the region, and identical for the same
seed; with a fake clock the pass stops on time and IOPS is computed
correctly; a read error is counted and the pass continues.

## TF03.1 — Random write pass
**Status**: done
**Description**: `random_write_pass(write_at, region_bytes, duration_s,
clock)` writes 4 KB of pattern data at random offsets in the scratch region
(first 1 GB). Same result type. Destructive mode only.

**Test**: writes land only inside the scratch region and are 4 KB-aligned;
write errors are counted; stops on time with a fake clock.

## TF03.2 — Grading
**Status**: done
**Description**: Rework `verdict.py`. Pure functions grade the sequential
results and the random results against named threshold constants (table in
F03); the overall grade is the worst of the two; errors or speed below the
FAIR floor mean RETIRE. Read-only mode grades on read figures only and
flags it. Freshness becomes a separate *looks brand new* note. Reasons name
the measurement that set each grade.

**Test**: table-driven cases at and around every threshold; worst-of
combination; random-only slowness caps at FAIR and never retires; read-only
flag; brand-new note only when fresh and not RETIRE.

## TF03.3 — Wire into the check flow
**Status**: done
**Description**: Read-only: random read, then the sequential read. Destructive
(after confirmation and unmount): random write, then random read, then the
full write and verify, which overwrites the scratch region. All on the one
`open_card` device.

**Test**: check-flow tests with fakes — order of passes, no random writes in
read-only mode, nothing written before confirmation, and random writes stay
inside the scratch region.

## TF03.4 — Report
**Status**: done
**Description**: Add the `Random` line (IOPS with an A1/A2/below-A1 label),
the graded `Verdict` line with `(read-only: write not measured)` when
applicable, the reasons, and the `Looks brand new` note. Exit codes: 0 for
EXCELLENT / GOOD / FAIR, 2 for RETIRE.

**Test**: report text and exit code for each grade, read-only and destructive.

## TF03.5 — Test suite
**Status**: done
**Description**: Fill gaps across `random_io.py`, `verdict.py` and
`check.py`. No new `manual`-marked test: a real random read needs root
for the raw device, and the manual tests run unprivileged (metadata only), so
the real-card random read is exercised by `make validate` in TF03.6.

**Test**: `uv run pytest` passes (108 tests, 2026-10-19).

## TF03.6 — Manual hardware run and calibration
**Status**: done (2026-10-21)
**Description**: Run `make validate` and `make stress` on the test card.
Check that Python's per-call overhead doesn't cap IOPS (compare the 4 KB loop
against the measured rate, e.g. with `iostat`). Record IOPS in
`process/02-doc/notes.md`, and adjust the thresholds if the measurements
show they are off.

**Test**: not automatable — needs the real card, and stress wipes it.
Covered by the `manual`-marked tests from TF03.5.

**Result** (2026-10-21, card R2):

- Python loop overhead is ~0.1% of a 4 KB read, so it doesn't cap IOPS.
  `iostat` showed the same ~1,500 tps the tool reported.

- R2 reads ~1,500 ±2% IOPS, with a ~7% slower first 8 s when cold, so the
  bare A1 line flipped it between GOOD and FAIR on noise.

- **Recalibrated toward GOOD**, per user: `READER_MARGIN = 0.95` on the A1/A2
  thresholds and `WARMUP_SHARE = 0.2` uncounted at the start of each pass.
  Details in `process/02-doc/notes.md`.

**Test**: `uv run pytest` passes (247 tests): new tier boundaries, R2's
numbers grade GOOD, warm-up errors still count.

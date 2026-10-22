# TF05 Stress survives a hung format, a sleeping Mac, and a lost card — for Feature F05

**Date Created:** 2026-10-21

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

## TF05.0 — Spec and issue

**Status**: done

**Description**: Add to the spec's health-check section: stress records its
result before reformatting, a format failure is recorded, and a card that
disconnects stops the run instead of counting bad chunks. Point I01 at F05.

**Test**: none needed — documentation only.

## TF05.1 — Record the stress result before formatting

**Status**: done

**Description**: In `run_check` (`microsd_utils/check.py`), record the
`stress` event in the registry right after `report`, then call `retag` with
that manifest. `retag` adds `formatted` and stores on the card as now; if
`erase_fat32` raises, record a `formatted` event with detail
`failed: <error>` (the existing event kind, so the manifest format is
unchanged) and re-raise.
The card's history ends up `stress` → `formatted`, with no duplicate
`stress` event.

**Test**: with the fake env, (a) a normal stress run records `stress` then
`formatted`, once each; (b) an `erase_fat32` that raises leaves `stress` and
`formatted: failed: …` in the registry and the error propagates.

## TF05.2 — Timeouts on diskutil calls that write to the card

**Status**: done

**Description**: In `microsd_utils/diskutil.py`, pass a timeout to
`subprocess.run` for `erase_fat32` (300 s) and `run_command` / `mount`
(60 s). Turn `subprocess.TimeoutExpired` into one clear error naming the
`diskutil` command and the timeout. Read-only `info`/`list` calls are left
alone.

**Test**: patch `subprocess.run` to raise `TimeoutExpired`; check the raised
error names the command and the timeout, and that each write call passes a
timeout.

## TF05.3 — A lost card aborts the pass

**Status**: done

**Description**: In `passes.py` (read and write chunks) and `random_io.py`,
an `OSError` whose errno is `ENXIO` or `ENODEV` raises a "card disconnected"
error instead of being recorded as a bad chunk. Other `OSError`s (bad
blocks) are still counted. In stress, the existing `stress_passes` handler
records it as `stress failed: card disconnected`.

**Test**: a fake `read_at` / `write_at` raising `OSError(ENXIO)` stops each
pass with the disconnect error; one raising `OSError(EIO)` is still counted
and the pass continues.

## TF05.4 — Keep the Mac awake

**Status**: done

**Description**: Prefix the commands in the Makefile's `validate`, `stress`,
`backup`, `flash` and `copy` targets with `caffeinate -i`, so idle sleep
can't drop the card. `card`, `cards` and `help` are quick and stay as they
are.

**Test**: `make -n <target>` (dry run, runs nothing) for each long target
prints a command starting with `caffeinate -i`.

## TF05.5 — Sizes under 1 GB in MB (chore)

**Status**: done

**Description**: `gigabytes` (renamed `human_size`) in `microsd_utils/session.py` prints
"0.0 GB" for R3's 32 MB card. Below 1 GB, print MB instead. Mark the chore
in `process/04-tasks/chores.md` done.

**Test**: 32 MB prints "32 MB", 62.6 GB still prints "62.6 GB", and the
boundary at 1 GB.

## TF05.6 — Test suite

**Status**: done

**Description**: Write the tests listed in TF05.1–TF05.5 and run the full
suite with `uv run pytest`; all pass.

**Test**: this step is the tests.

## TF05.7 — Hardware check

**Status**: not done

**Description**: On R2: run `make validate` and pull the card out during the
read pass; record the errno and that the run stops with "card disconnected".
If macOS reports a different errno, adjust TF05.3. Then run `make stress` to
the end and check `make history` shows `stress` before `formatted`.

**Test**: not automatable — needs the real card and a physical unplug.
Results recorded in `process/02-doc/notes.md`.

# TF06 Verify a card against an image — for Feature F06

**Date Created:** 2026-10-21

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

## TF06.0 — Spec

**Status**: done

**Description**: Add to the spec's "Backup, flash and copy" tool:

> - *verify*: compare the card with an image, read-only, and report where it
>   differs; differences only inside a FAT partition are flagged as the
>   likely effect of macOS mounting the card.

And under it: flash's read-back uses the same comparison.

**Test**: none needed — documentation only.

## TF06.1 — Chunk-by-chunk comparison

**Status**: done

**Description**: In `microsd_utils/transfer.py`, a `compare_card(read_at,
source, on_progress)` that streams the image (via `open_image`) and the card
in 4 MiB chunks up to the image's length and returns the offsets of chunks
that differ, with the timing. A card read error raises; a lost card raises
`CardDisconnected` (TF06.5).

**Test**: a fake card equal to the image gives no differences; one with two
corrupted chunks gives exactly those two offsets; a `.img.gz` source works
the same as `.img`.

## TF06.2 — Say where the differences are

**Status**: done

**Description**: Map each differing chunk to a partition of the image's own
partition table (read from the image's first sector with the existing
`partitions.py` parser) and print one line per partition: number, type, how
many chunks differ. If every difference falls inside a FAT partition, add:
"All differences are in the FAT boot partition: macOS changes it whenever it
mounts the card. The rest of the card matches." Differences outside any
partition are listed as such.

**Test**: differences only in a FAT partition → the note; differences in the
Linux partition → no note, partition named; a difference before the first
partition (the partition table itself) → reported as "partition table".

## TF06.3 — `verify` command and `make verify`

**Status**: done

**Description**: `microsd verify IMAGE [--dry-run]` in `imaging.py` and
`cli.py`: discover the card, print the card and ID lines, check the image
fits, show the plan ("The card is only read"), re-run under sudo, unmount,
open **read-only**, compare, report. Exit 0 on `Verified: OK`, 1 on any
difference. `make verify IMAGE=...` runs it under `caffeinate -i`, with the
usual usage message when `IMAGE` is missing.

**Test**: with the fake env: a matching card → `Verified: OK`, exit 0; a
differing card → report, exit 1; the device is only ever opened read-only;
dry run touches nothing. `make -n verify IMAGE=x` prints
`caffeinate -i .venv/bin/microsd verify "x"`; `help` lists `verify`.

## TF06.4 — Flash verifies with the same comparison

**Status**: done

**Description**: Replace `verify_card`'s single hash with `compare_card`, so
a failed flash prints the same where-it-differs report and then fails. The
check that the bytes *written* match the image's recorded hash stays.

**Test**: existing flash tests still pass; a fake card that corrupts one
chunk on write makes flash fail with that chunk's partition named.

## TF06.5 — Flash failures recorded, lost reader named

**Status**: done

**Description**:

- In `run_flash` (and `run_copy`, which flashes the same way), a failure
  after the erase is confirmed (write, verify, or manifest restore) is
  recorded as a `flash` (or `copy`) event with detail `failed: <error>` in
  the registry, then re-raised — as `stress_passes` does. Shared helper:
  `flash_and_restore` in `imaging.py`; `record_event` moved from `check.py`
  to `identity.py`.

- `read_exactly` and `write_image` call F05's `raise_if_gone`, so a reader
  that drops mid-flash or mid-verify raises `CardDisconnected` ("card
  disconnected: …") instead of a raw `OSError`.

**Test**: a write that raises records `flash failed: …` and propagates;
an `OSError(ENXIO)` during read-back raises `CardDisconnected`; an
`OSError(EIO)` still raises a plain error.

## TF06.6 — Test suite

**Status**: done

**Description**: Write the tests listed in TF06.1–TF06.5 and run the full
suite with `uv run pytest`; all pass.

**Test**: this step is the tests.

## TF06.7 — Hardware check

**Status**: done (2026-10-22)

**Description**: On R2: `make verify IMAGE=dome-2-master` on the card as it
is now, then re-flash, then verify again. Record time, MB/s and where any
differences were in `process/02-doc/notes.md`.

**Test**: not automatable — needs the real card and reader.

**Results** (R2, image `dome-2-master`):

- R2 was re-flashed rather than verified as left by the interrupted flash;
  the re-flash verified OK (1011 s write, 813 s verify).

- First `make verify` (2026-10-21): 838 s, 74.7 MB/s, 8 chunks differ, one
  labelled "partition table". Cause: the image's FAT32 starts at 1 MiB,
  inside chunk 0, and chunks were labelled by their start. Fixed: label by
  the first and last differing byte (`difference_span`), with a regression
  test on that layout.

- Second `make verify` (2026-10-22): 835 s, 75.0 MB/s, 9 chunks differ, all
  in `partition 1 (FAT32)`, FAT-only note shown. Details in `notes.md`.

# TF02 Back up, flash and copy microSD cards for Feature F02
**Date Created:** 2026-10-18

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

**Builds on F01**: reuses its scaffold, the `diskutil` adapter, the reader
fingerprint and discovery (TF01.1), `open_card`, self-elevation under `sudo`
after the plan is shown, and the erase warning with its two-step
confirmation (`yes`, then the disk identifier).

**Design rule**: same as F01. Partition parsing, the image store, size checks
and the card-swap logic are pure and tested with fixtures and temp files.
Device I/O and `diskutil` calls stay in the adapter. Stdlib only at runtime
(`gzip`, `lzma`, `hashlib`, `json`).

## TF02.0 — Partition table parser
**Status**: done
**Description**: Pure function from the first sectors of a card to the byte
offset where the last partition ends. Handles MBR (Raspberry Pi OS cards) and
GPT; returns "no table" for a blank card so the caller copies the whole card.

**Test**: fixtures for a Pi OS MBR layout, a GPT layout, a protective-MBR-only
GPT, a blank sector, and a corrupt table (raises with the reason).

## TF02.1 — Image store
**Status**: done
**Description**: Resolve image names to paths in `images/` at the repo root,
located from the package, not the current directory (overridable for tests).
Create it if missing. Under `sudo`, chown new files and the directory to
`SUDO_USER`. Write `<name>.img.gz` plus a `<name>.json`
sidecar (source media name and size, bytes copied, SHA-256, date). Open
images for reading as `.img`, `.img.gz` or `.img.xz`. Refuse to overwrite an
existing name; reject names with path separators.

**Test**: temp-dir round trip for each format, sidecar contents, overwrite
refusal, bad names, directory created when missing, chown target taken from
`SUDO_USER` (chown call faked).

## TF02.2 — Backup
**Status**: done
**Description**: Unmount the card, read the first sectors, use TF02.0 to get
the copy length, then stream that many bytes from `/dev/rdiskN` into the
compressed image while computing SHA-256. Record the sidecar. Progress and
throughput printed periodically.

**Test**: a temp file with a Pi-style MBR stands in for the card; the image
decompresses to exactly the bytes up to the last partition end, and the hash
matches. A read error mid-copy raises and leaves no half-written image.

## TF02.3 — Flash and verify
**Status**: done
**Description**: Check the image's data size against the target card size
(refuse if larger, and refuse an image whose size isn't a whole number of
card blocks). Unmount, stream the image to `/dev/rdiskN`, read the same range
back and compare its SHA-256 with the image's. Eject on success.

**Test**: temp-file target: clean flash verifies; a too-small target is
refused before any write; a fake device that corrupts one block fails
verification and reports it.

## TF02.4 — Card-swap detection
**Status**: done
**Description**: Poll the reader using F01's discovery (TF01.1): each poll
says *card present* (with its identifier) or *no card*. Two waits: *for the
card to be removed* and *for a card to be inserted*. A pure state machine
decides, from a sequence of poll results, when the master has gone and a new
card has arrived. Times out with a clear message.

**Test**: scripted poll sequences — normal swap, card never removed (times
out, nothing written), a second matching device appearing (refused), timeout
waiting for the new card.

## TF02.5 — Guided copy flow
**Status**: done
**Description**: `copy <name>`: if the reader has a card, use it as the
master; otherwise ask the user to insert it. Back it up (TF02.2),
eject it, prompt to insert the new card, wait for the swap (TF02.4), show the
new card, confirm, flash and verify (TF02.3). Each prompt says exactly what to
do next.

**Test**: whole flow with the adapter, prompts and disk watcher faked —
happy path, user aborts at confirmation (no write), new card too small.

## TF02.6 — CLI subcommands
**Status**: done
**Description**: `backup <name>`, `flash <image>`,
`copy <name>`, each with `--dry-run`. Move what the commands share out of
`check.py` into a common module: the environment dataclass, `SUDO_NOTE` and
elevation, the erase warning and two-step confirmation, progress printing.
Flash shows the erase warning and asks both questions. Exit 0 on success, 1
on error or refusal.

**Test**: CLI tests with fakes — argument errors, refusals, dry-run does no
I/O, exit codes.

## TF02.7 — Make targets
**Status**: done
**Description**: Add `backup`, `flash` and `copy` with `## description`
comments. Required variables (`NAME`, `IMAGE`) fail with a usage message when
missing. The tool elevates itself, so make doesn't call `sudo`. Update the
README's Usage section.

**Test**: missing variables exit non-zero; `make -n` prints the expected
commands; `make help` lists them.

## TF02.8 — Test suite
**Status**: done
**Description**: Fill gaps so every module above has unit tests. MBR and GPT
layouts are built in code by the tests (`tests/test_partitions.py`,
`tests/fakes.partitioned_card`) rather than stored as fixture files. The
`manual`-marked tests run `backup`, `flash` and `copy` as dry runs against
the real reader (metadata only); real reads and writes need root and are
run by hand in TF02.9.

**Test**: `uv run pytest` passes (181 tests, 2026-10-19).

## TF02.9 — Manual hardware run
**Status**: done (2026-10-22)
**Description**: Run the F02 demo with a real Pi card, boot a Pi from the
copy, and record in `process/02-doc/notes.md`: backup and flash throughput,
whether gzip slows the backup noticeably (switch to plain `.img` if so), and
how macOS behaves on insert/eject during `copy` (auto-mount, "disk not
readable" dialogs), and whether the reader's disk node disappears when the
card is pulled (assumed by TF02.4).

**Test**: not automatable — needs physical cards and a Pi. Covered by the
`manual`-marked tests from TF02.8.

**Results so far** (numbers in `process/02-doc/notes.md`):

- **Backup** (2026-10-21): `dome-2-master` from the user's Pi card, 62.6 GB
  in 1032 s, 60.7 MB/s, 12.1 GB `.img.gz`. gzip costs ~15%; keeping `.img.gz`.

- **Flash** onto R2 (2026-10-21): first attempt lost to a reader reset at 50%
  of verify; re-flash verified OK (61.9 MB/s write, 77.0 MB/s verify).

- **Boot** (2026-10-22): a Pi booted from R2 — confirmed by the user.

- **First `make copy NAME=dome-2-copy`** (2026-10-22): backup OK (62.6 GB,
  1038 s, 60.3 MB/s), then `gave up after 300 s waiting for the card to be
  removed` — the user wasn't at the Mac when the 17-minute backup ended.
  **Changed, per user**: the swap waits have no timeout; `copy` waits until
  the card is swapped or Ctrl-C, and says so. `SwapError` and `Env.clock`
  removed; tests now poll two hours' worth before the swap.

- **Second `make copy NAME=dome-2-copy2`** (2026-10-22): master R1 ("Working
  Dome2 microsd. Master.") backed up (1038 s, 60.3 MB/s); removal and
  insertion both detected — **the reader's disk does vanish from `diskutil`
  when the card is pulled** (TF02.4 assumption confirmed); new card tagged
  R4 at the prompt; the "same size and partitions as the master" caution
  showed (R4 already had R1's layout); flash 1048 s, 59.7 MB/s; verify
  845 s, 74.0 MB/s, OK; manifest written to R4; ejected; `Copy complete.`

- **Boot of the copy** (2026-10-22): a Pi booted from R4, and macOS showed
  nothing unusual on the swap — both confirmed by the user.

- **Left**: `make copy` with the master and a second card, boot the copy,
  and note macOS's behaviour on the swap and whether the reader's disk
  vanishes from `diskutil` when the card is pulled.

# TF01 microSD health check on macOS for Feature F01
**Date Created:** 2026-10-18

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

**Design rule**: pure logic (parsing, safety checks, pattern, verdict) lives in
modules with no `subprocess` or device I/O. `diskutil` calls and raw-device
I/O sit in a thin adapter, so everything else is tested with fixtures and
temp files. Stdlib only at runtime (`argparse`, `plistlib`, `subprocess`).

## TF01.0 — Python project scaffold
**Status**: done
**Description**: Add `pyproject.toml` (uv, Python ≥3.11), package
`microsd_utils/`, `pytest` as a dev dependency, and a `microsd` console
entry point with a `check` subcommand stub. Point `run.bash` at it.

**Test**: `microsd --help` and `microsd check --help` exit 0.

## TF01.1 — Reader fingerprint and card discovery
**Status**: done
**Description**: Tracked `sd_reader.json` at the repo root holds the reader
fingerprint: `IORegistryEntryName` (`NORELSYS 1081CS0 Media`), `DeviceTreePath`
(`IODeviceTree:/arm-io@10F00000/usb-drd2@92280000/usb-drd2-port-ss@02200000`)
and `BusProtocol` (`USB`). A pure matcher accepts a `diskutil info` plist only
if it matches all three **and** is `WholeDisk`, `VirtualOrPhysical: Physical`,
`Internal: false`, `RemovableMedia: true`. A pure parser turns the matched
plist plus its `diskutil list -plist` entry into a `CardInfo` (identifier,
size, block size, media name, partitions with content type and size).

Discovery (adapter): run `diskutil list -plist external physical`, then
`diskutil info -plist` on each listed **whole** disk; exactly one match is
required, otherwise raise naming how many matched. No device node is ever
opened here — metadata only. `recheck(card)` repeats the info call on the
found identifier and re-runs the matcher; every raw open goes through it.

**Test**: matcher and parser against the real capture of this card
(2026-10-18) and variants derived from it — different port path, different
reader name, `Internal: true`, `Virtual`, partition instead of whole disk
(each refused); discovery with a faked adapter — zero, one and two matches;
recheck fails when the identifier now points at a different device.

## TF01.2 — Read-only scan
**Status**: done
**Description**: Read the raw device (`/dev/rdiskN`) in fixed-size chunks from
start to end, counting chunks that fail to read and timing throughput. Reads
are aligned to the device block size. Progress is printed periodically.
Returns a `ScanResult` (bytes read, error count and offsets, MB/s).

**Test**: run against a temp file standing in for the device; inject a read
failure at a known offset via a fake reader and check it is counted and the
scan continues.

## TF01.3 — Destructive write-and-verify
**Status**: done
**Description**: Unmount the disk (`diskutil unmountDisk`), then write a
pattern derived from each chunk's offset (so a wrapped-around fake-capacity
write is detectable), then read it all back and compare. Returns the write
and verify `PassResult`s (failed and mismatched chunk offsets, MB/s). A
wrapping fake card fails verification on the *overwritten early* chunks, not
past the real size, so fake capacity shows up as mismatches rather than a
"last good offset". Only runs after the TF01.6 confirmation.

**Test**: pattern generator is deterministic and differs per offset; full
write-verify on a temp file passes clean; a fake device that wraps writes past
a limit is reported with the right real capacity; a fake device that corrupts
one chunk reports that offset.

## TF01.4 — Factory-fresh signals
**Status**: done
**Description**: Pure function from `DiskInfo` plus a top-level file listing
of the mounted volume to a freshness signal: a single FAT32/exFAT partition
covering the card, and no files besides known system ones (`.Spotlight-V100`,
`.fseventsd`, `System Volume Information`, ...). Read-only mode only; in
destructive mode it is read before wiping.

**Test**: fixtures for a factory card, a Raspberry Pi OS card (two
partitions), and an exFAT card with user files.

## TF01.5 — Verdict
**Status**: done
**Description**: Pure function from the scan/stress results and freshness
signal to `Verdict` (`BRAND_NEW`, `STILL_OK`, `RETIRE`) plus a list of
reasons. Thresholds are named constants at the top of the module (e.g.
minimum write speed, based on Class 10's 10 MB/s).

**Test**: table-driven cases for each verdict, each retire reason on its own,
and edge cases at each threshold.

## TF01.6 — CLI, confirmation and report
**Status**: done
**Description**: Wire `microsd check [--destructive] [--dry-run]` — no disk
argument. Check for root and exit with a clear message if missing. Discover
the card (TF01.1), show its identifier, media name and size; for destructive
mode require typing the identifier. `--dry-run` prints the plan and exits before any I/O. Print the
final report and verdict; exit code 0 for brand new / still OK, 2 for retire,
1 for errors or refusal.

**Test**: CLI tests with the adapter faked — no reader / two readers refused,
wrong confirmation
aborts with no writes, `--dry-run` performs no I/O, report and exit codes per
verdict.

## TF01.7 — Make targets
**Status**: done
**Description**: Add `validate` and `stress` under `##@ Tool` in the
`Makefile`, each with a `## description` for `make help`. No disk variable;
`stress` takes `DRY_RUN=1`, and both run the CLI under `sudo`. Update the README's Usage section to show them.

**Test**: `make -n validate`, `make -n stress` and `make -n stress DRY_RUN=1`
print the expected commands; `make help` lists both under Tool.

## TF01.8 — Test suite
**Status**: done
**Description**: Fill gaps so every module above has unit tests, add the
captured `diskutil` plist fixtures (this card only) under `tests/fixtures/`, and add a
`manual`-marked end-to-end test against a real card, excluded from the plain
`uv run pytest` run.

**Test**: `uv run pytest` passes; `pytest -m manual` is documented in the test file.

## TF01.9 — Manual hardware run
**Status**: done
**Description**: Run the demo steps from F01 on a real card in the designated
reader, both modes, including the wrong-port refusal. Record throughput and
anything surprising in `process/02-doc/notes.md`.

**Progress**:

- [x] Read-only `make validate` on the 64 GB Pi card (2026-10-18): 70.1 MB/s,
  0 bad chunks, STILL OK. Recorded in `notes.md`.
- [x] `make stress` on the same card (2026-10-18): write 54.0 MB/s, verify
  72.0 MB/s, 0 bad chunks, STILL OK. Erase warning and both questions shown.
- [x] Wrong-port refusal: marked done at the user's direction (2026-10-19);
  the refusal output was not captured. The unit tests cover the
  wrong-port refusal against the captured plist.

**Test**: not automatable — needs physical hardware and wipes a real card.
Covered by the `manual`-marked test from TF01.8.

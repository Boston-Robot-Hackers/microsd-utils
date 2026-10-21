# I01 Stress verdict is lost when the format step hangs or fails

## Symptom

- 2026-10-21, card R3 (32 MB): `make stress` finished both passes and printed
  `Verdict: RETIRE` (8 of 8 chunks failed verify), then stuck at
  `Formatting disk4 FAT32 as R3...`.

- `diskutil eraseDisk FAT32 R3 MBRFormat disk4` was still running after more
  than 6 minutes, with no output and no timeout.

- The registry (`.microsd_tools/cards.json`) got no `stress` event. The RETIRE
  verdict was only on the terminal. It was added to R3's registry entry by
  hand.

- 2026-10-21, card R2 (64 GB, 0 bad chunks on 2026-10-18): `make stress`
  wrote cleanly, then verify reported `2740 chunks failed to read` and
  `RETIRE`. `retag` then failed on `diskutil info -plist disk4` (disk gone),
  so again nothing was recorded.

- `pmset -g log`: `10:48:53 Entering Sleep state due to 'Idle Sleep'`,
  about 82% into verify. The USB disk dropped on sleep; every later read
  failed instantly (verify averaged 86.6 MB/s, above the card's 72 MB/s).
  **The card is fine; the Mac slept.**

## Cause

- **The verdict is recorded too late.** `run_check` records the stress
  result only inside `retag` (`microsd_utils/check.py`), after
  `erase_fat32`. If the format hangs or raises, nothing is recorded.
  `stress_passes` records failures of the passes themselves, not of
  `retag`.

- **No timeout.** The `diskutil` calls that write to the card
  (`erase_fat32`, `unmount_disk`, `mount_disk`, `mount`) run with no
  timeout, so a card that doesn't complete writes hangs the tool silently.

- **No sleep guard.** Nothing keeps the Mac awake during a 35-minute run,
  so idle sleep drops the card mid-pass.

- **A vanished device reads as bad chunks.** `read_pass` records each
  `OSError` and keeps going, so a lost disk becomes thousands of "bad
  chunks" and a false RETIRE.

## Tests done

- Read the code path: `run_check` → `report` → `retag` → `erase_fat32` →
  `store` → `registry.record`.

- `ps` showed `diskutil eraseDisk` as the stuck child of `microsd check`.

## Proposed fix

**Taken up by F05** (`process/03-features/notdone/F05-stress-robustness.md`).
Close this issue when F05 is done.

**Behavior change: needs a feature and task file.**

- Record the stress verdict in the registry right after `report`, before
  formatting. Record a format failure as its own event.

- Give the `diskutil` calls that write to the card a timeout, and raise a
  clear error when it expires.

- Hold a sleep assertion for the whole run (e.g. re-exec under
  `caffeinate -i`, or `caffeinate -w <pid>`).

- Stop a pass when the device is gone (e.g. `ENXIO`, or the disk no longer
  passes `recheck`) and report "card disconnected at X GB", not RETIRE.

- Workaround until fixed: `caffeinate -i make stress`.

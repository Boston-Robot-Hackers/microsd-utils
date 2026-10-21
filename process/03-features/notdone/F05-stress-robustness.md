# F05 — Stress survives a hung format, a sleeping Mac, and a lost card

**Priority**: High

**Date Created:** 2026-10-21

**Done:** no

**Tasks File Created:** yes

**Tests Written:** yes

**Test Passing:** yes

**Description**: Fixes issue I01
(`process/05-issues/open/I01-stress-verdict-lost-on-hung-format.md`). Twice on
2026-10-21 a full stress run finished its passes but the result never reached
the registry: once because `diskutil eraseDisk` hung (R3), once because the
Mac went to idle sleep and the card dropped off USB (R2). The second also
turned a healthy card into a false RETIRE.

### Scope

- **Record the result before formatting.** The `stress` event goes into the
  registry right after the report, before `erase_fat32`. A format that fails
  or times out is recorded as its own event, then raised.

- **Timeouts on `diskutil` calls that write to the card.** `erase_fat32`,
  `unmount_disk`, `mount_disk`, `mount` and `eject` get a timeout; when it
  expires the tool stops with a clear message naming the command, instead of
  hanging silently.

- **Keep the Mac awake.** The Makefile's long-running targets (`validate`,
  `stress`, `backup`, `flash`, `copy`) run under `caffeinate -i`, so idle
  sleep can't drop the card mid-pass.

- **A lost card aborts the pass.** A read or write that fails because the
  device is gone (not a bad block) stops the pass with "card disconnected"
  instead of being counted as a bad chunk. Bad blocks are still counted.

- **Chore folded in**: card sizes under 1 GB print in MB, not "0.0 GB".

### Decisions

- **Keep-awake lives in the Makefile**, not in Python: the Makefile is the
  entry point, and `caffeinate -i <command>` is one word per target.

- **A lost card is told apart by errno.** A bad block gives `EIO`; a device
  that has gone away is expected to give `ENXIO` or `ENODEV`. **Unverified**
  on this Mac and reader until the hardware step pulls a card mid-read.

- **Timeouts**: 300 s for `eraseDisk` (a healthy 64 GB format took a few
  seconds; R3 hung for over 6 minutes), 60 s for the others.

## How to Demo

**Setup**: the test card (R2) in the NORELSYS reader.

**Steps**:
1. `make stress`, and let it finish: the registry (`make cards`) shows a
   `stress` event, then `formatted FAT32`.
2. `make validate`, and pull the card out during the read pass.
3. `make card` with a card under 1 GB, if one is at hand.

**Expected output**: step 1 records the result even though it now comes
before the format; step 2 stops at once with "card disconnected" and no
RETIRE verdict; step 3 shows the size in MB.

## Process Gate

After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

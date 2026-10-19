# Feature description for feature F01

Feature file name must be `FNN-<slug>.md` where `NN` matches the feature number.
# F01 — microSD health check on macOS
**Priority**: High
**Date Created:** 2026-10-18
**Done:** yes
**Tasks File Created:** yes
**Tests Written:** yes
**Test Passing:** yes
**Description**: A `microsd check` command for macOS that checks the microSD
card in the designated card reader for errors, stress-tests it, and gives a verdict: *brand new*,
*still OK*, or *retire*.

### Modes

- **Read-only (default)**: reads every block of the raw device, counts read
  errors, and measures read speed. Card data is untouched.

- **Destructive (`--destructive`)**: writes a position-dependent pattern to
  every block and reads it back. This wipes the card. It finds bad blocks,
  detects fake capacity (writes that wrap around to earlier blocks), and
  measures write speed.

### Verdict

The verdict is an **estimate from measured signals**, not a reading of the
card's wear: the reader reports none (`SMARTStatus: Not Supported`, checked
2026-10-18).

- **Retire**: any read/verify error, real capacity below advertised, or
  speed far below the minimum for a usable card.
- **Brand new**: no errors, good speed, and a factory-fresh layout (one
  FAT32/exFAT partition spanning the card, no user files).
- **Still OK**: everything else that passes.

Each verdict prints the reasons behind it.

### Safety

- **Only the card in the designated reader** is touched; no other disk is
  read or written. The reader is identified by `sd_reader.json` (IORegistry
  name `NORELSYS 1081CS0 Media` and its exact USB port path), see the spec's
  Safety section.
- No disk argument: the command finds the card itself. Zero or several
  matching devices → refuse.
- The fingerprint is re-checked immediately before the raw device is opened.
- Destructive mode shows the card's identifier, size and name, and requires
  typing the identifier (e.g. `disk4`) to confirm.
- `--dry-run` prints what would be done without touching the device.

### Make targets

- `make validate` runs the read-only check.
- `make stress` runs the destructive check; `DRY_RUN=1` adds `--dry-run`.
- Both prompt for `sudo`.

### Out of scope

Raspberry Pi / Linux support (a later feature), repairing or reformatting the card.

## How to Demo
**Setup**: `uv sync` done; the NORELSYS reader in its designated port with a
card in it. A spare card you don't mind wiping for the destructive demo.

**Steps**:
1. `make` — the Tool section lists `validate` and `stress`.
2. `make validate` — finds the card and runs the read-only check.
3. Move the reader to a different USB port, `make validate` — refused, no
   matching reader. Move it back.
4. `make stress DRY_RUN=1` — prints the plan, writes nothing.
5. `make stress` — type the shown identifier (e.g. `disk4`) to confirm.

**Expected output**: a report with device info, bytes checked, error count,
read (and write) speed, real capacity in destructive mode, and a verdict line
such as `Verdict: STILL OK` with its reasons. Step 3 exits non-zero with a
refusal message.

## Process Gate
After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

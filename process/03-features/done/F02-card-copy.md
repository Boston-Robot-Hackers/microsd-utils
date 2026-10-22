# Feature description for feature F02

Feature file name must be `FNN-<slug>.md` where `NN` matches the feature number.
# F02 — Back up, flash and copy microSD cards on macOS
**Priority**: High
**Date Created:** 2026-10-18
**Done:** yes
**Tasks File Created:** yes
**Tests Written:** yes
**Test Passing:** yes
**Description**: Three commands sharing one image store on the Mac:

- **`microsd backup <name>`**: read the card into a compressed image
  file in the store.
- **`microsd flash <image>`**: write an image to the card, verify it by
  reading it back, then eject it.
- **`microsd copy <name>`**: guided copy through the Mac's single card slot.
  The user inserts the master card in the reader, it is backed up to `<name>`,
  the tool asks them to remove it and insert a new card in the same reader,
  then flashes and verifies the new card. One new card per run; the image is kept, so `flash` can make more
  copies later without the master.

### What gets copied

Only the data up to the **end of the last partition**, read from the card's
own partition table (MBR or GPT). A target card smaller than that is refused.
A card with no partition table is copied whole.

### Image store

- Images live in `images/` at the repo root as `<name>.img.gz`, each with a
  `<name>.json` sidecar: source card name and size, bytes copied, SHA-256, date.
- `images/` is in `.gitignore`; the tool creates it if missing.
- The commands run under `sudo`, so new image files are handed back to the
  invoking user (`SUDO_USER`) rather than left owned by root.
- `flash` also accepts plain `.img` and `.img.xz` files (e.g. Raspberry Pi OS
  downloads), from any path.
- `backup` refuses to overwrite an existing image name.

### Safety

- Same reader fingerprint and discovery as F01; no disk argument anywhere.
- `flash` and the flash half of `copy` show the same all-caps erase warning
  as `make stress` and ask both questions: `yes`, then the disk identifier.
- Commands show their plan, then re-run themselves under `sudo`.
- During `copy`, the tool waits for the reader to report no card (master
  removed) before accepting a new card, so the master can't be the target.
- `--dry-run` prints the plan without reading or writing.

### Make targets

- `make backup NAME=<name>`
- `make flash IMAGE=<name or path>`
- `make copy NAME=<name>`

### Depends on

F01's project scaffold (TF01.0), reader fingerprint and discovery (TF01.1) and
the CLI root check (TF01.6). F02 is built after F01.

### Out of scope

Raspberry Pi / Linux support, copying several cards at once, shrinking the
filesystem inside the last partition.

## How to Demo
**Setup**: macOS with `uv sync` done, a master card (e.g. a working Pi
card) and a spare card you don't mind wiping.

**Steps**:
1. `make copy NAME=pi-robot` and follow the prompts: insert master, wait for
   the backup, remove it, insert the spare, type its disk identifier to confirm.
2. `ls images/` shows `pi-robot.img.gz` and `pi-robot.json`.
3. Boot a Pi from the new card.
4. Insert another spare: `make flash IMAGE=pi-robot`.
5. `make backup NAME=pi-robot` is refused because the name exists.

**Expected output**: each step prints progress and finishes with
`Verified: OK` (SHA-256 match). The copied card boots like the master.

## Process Gate
After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

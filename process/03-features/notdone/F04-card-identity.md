# Feature description for feature F04

Feature file name must be `FNN-<slug>.md` where `NN` matches the feature number.
# F04 — Card identity: on-card manifest and repo registry
**Priority**: High
**Date Created:** 2026-10-20
**Done:** no
**Tasks File Created:** yes
**Tests Written:** yes
**Test Passing:** no
**Description**: Cards get mixed up. Each physical card has a label with a
1–4 character ID (letters and digits, e.g. `A1`, `PI7`). The tools record that
ID on the card itself and keep a list of every known card in the repo, so any
card put in the reader can be identified and its history shown.

### On the card

- `.microsd_tools/manifest.json` on the card's FAT partition (the Pi
  `bootfs`, or the whole card after a format) — the only partition macOS can
  write.
- Holds the **ID**, **contents** (what we think is on it, e.g. the image
  name), and a **history** list: one entry per event with an ISO date and
  time, the event (`tagged`, `formatted`, `stress`, `flash`, `copy`), and
  detail (image name, grade, ...).

### In the repo

- `.microsd_tools/cards.json` at the repo root, git-ignored, located from the
  package like `images/`. One entry per ID: the latest copy of that card's
  manifest plus when it was last seen.
- Updated whenever a card's manifest is read or written. Under `sudo`, files
  are handed back to `SUDO_USER`, like the image store.

### IDs

- 1–4 characters, `A–Z` and `0–9`. Typed case-insensitively, stored upper
  case. Anything else is refused.
- A card with no manifest gets its ID from the user. If the ID is already in
  the registry, the tool shows that entry and asks whether this is the same
  card.

### Commands that overwrite a card

**Rule: read the manifest first, write it back afterwards with a new history
entry.**

- **stress**: read manifest → wipe and verify → reformat FAT32 (volume named
  after the ID) → write manifest with a `stress` entry (grade).
- **flash**: read target's manifest → flash and verify → mount the new
  `bootfs` → write the target's own manifest with a `flash` entry; contents
  becomes the image name.
- **copy**: as flash, for the new card. The new card never inherits the
  master's ID; entering the master's ID for it is refused.
- No FAT partition after flash (image without one) → warn, record the event
  in the registry only.

### Read-only commands

- **validate** and **backup** show the card's ID but never write to it.
  Untagged cards are reported, with a pointer to `make card`.
- **backup** records the source card's ID in the image sidecar.

### New commands

- **`make card`**: show the card in the reader — ID, contents, history. If
  untagged, ask for its ID and tag it. Offers to update the contents
  description.
- **`make cards`**: list every card in the registry: ID, contents, last event.

### Safety

- Same reader fingerprint as F01. The FAT volume written to must belong to the
  fingerprinted disk, checked immediately before writing.
- Tagging an untagged card shows what will be written and asks `y/N`.
- `--dry-run` prints the manifest that would be written.

### Depends on

F01 (reader, discovery, stress), F02 (flash, copy, image store).

### Out of scope

Reading manifests from ext4 partitions, a Linux/Pi version, syncing the
registry between machines.

## How to Demo
**Setup**: macOS with `uv sync` done; a card in the reader; a sticker with its
ID (say `A1`).

**Steps**:
1. `make card` → card is untagged; enter `A1`, describe contents; confirm.
2. `make card` again → shows `A1`, contents, one `tagged` entry.
3. `make flash IMAGE=<raspios>.img.xz` → after verify, prints
   `Manifest written: A1`.
4. `make card` → history now has a `flash` entry with the image name.
5. `make cards` → lists `A1`.
6. `make stress` → after the run, card is FAT32 named `A1`, history has a
   `stress` entry with the grade.

**Expected output**: the ID and history survive every overwrite, and the
registry matches the card.

## Process Gate
After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

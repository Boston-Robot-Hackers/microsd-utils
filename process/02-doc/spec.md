# microsd-utils — Spec

## Purpose

A few simple command-line tools for working with microSD cards, focused on
macOS and Raspberry Pi.

## Platforms

- **macOS**: the host where cards are usually flashed, backed up and inspected.
  Disks are managed with `diskutil` and accessed as `/dev/diskN` / `/dev/rdiskN`.

- **Raspberry Pi OS (Linux)**: either a card in a USB reader, or the Pi's own
  boot card. Disks are managed with `lsblk` and accessed as `/dev/sdX` /
  `/dev/mmcblk0`.

## Tools

Each tool, or a group of closely related tools, becomes a feature (`F01`, `F02`, ...).

### Confirmed

- **Health check (macOS)**: check a card for errors, stress-test it, and give
  a verdict: *brand new*, *still OK*, or *retire*. Two modes:
  - *read-only* (default): reads every block, counts errors, measures read speed.
  - *destructive*: writes and verifies every block, which wipes the card.
    It also detects fake capacity and measures write speed.

  The verdict is an **estimate from measured signals** (errors, real vs
  advertised capacity, speed, factory-fresh layout). The card reader reports
  no wear data (`SMARTStatus: Not Supported`, checked 2026-10-18).

  **Graded verdict** (F03, replaces *still OK*): *excellent*, *good*, *fair*
  or *retire*, plus a separate *looks brand new* note for factory-fresh
  cards. The grade is the worst of two measurements:
  - *sequential speed* tiers, anchored on the SD speed classes (U1 = 10 MB/s,
    U3/V30 = 30 MB/s minimum write);
  - a short *random 4 KB* test (30–60 s) rated against the A1/A2 application
    classes (A1: 1500 read / 500 write IOPS; A2: 4000 / 2000). Random writes
    happen in destructive mode only, before the full wipe. A card within 5%
    of a class counts as meeting it, and the first 20% of each pass is an
    uncounted warm-up: a USB reader measures a little low, so borderline
    cards lean toward the better grade.

  Retire stays reserved for errors and speed below the U1 floor; slow random
  I/O alone lowers the grade to *fair*, it doesn't retire a card.

- **Backup, flash and copy (macOS)**: three related commands built on one
  image store, `images/` in the repo (git-ignored; images are kept for reuse):
  - *backup*: read a card into a compressed image file.
  - *flash*: write an image file to a card, then verify it by reading it back.
  - *copy*: back up the master card in the slot, ask the user to swap in a
    new card, then flash it. One new card per run.

  Only the data up to the end of the last partition is copied, so a slightly
  smaller target card still works; a card smaller than that is refused.

- **Card identity (macOS)**: cards get mixed up, so each one carries a
  physical label with a 1–4 character ID (letters/digits), and the tools
  track it:
  - *on the card*: `.microsd_tools/manifest.json` on its FAT partition — the
    ID, what we think is on it, and its history (formats, flashes, stress
    runs, with date and time).
  - *in the repo*: a git-ignored `.microsd_tools/cards.json` registry of every
    card we know about.
  - Commands that overwrite a card (stress, flash, copy) read its manifest
    first and write it back afterwards with a new history entry; stress
    reformats the card FAT32 so it has somewhere to put it. A card with no
    manifest gets its ID from the user. A copied card never inherits the
    master's ID.

### Candidate ideas, not confirmed

- List attached removable cards (device, size, label, partitions).
- Eject / unmount a card safely.
- Pre-configure a freshly flashed Pi card (hostname, Wi-Fi, SSH, user).

## Safety

Most of these tools write raw disks, so **the tools touch only the card in one
designated card reader, and no other disk is ever read or written**:

- **Reader fingerprint**: the reader is identified by a tracked
  `sd_reader.json`: its IORegistry name and its exact USB port path
  (`DeviceTreePath`), plus physical, removable, not internal, whole disk. The
  current reader is a USB NORELSYS 1081CS0 on this Mac's
  `usb-drd2-port-ss@02200000` port; moving it to another port means editing
  the file.
- **No disk argument**: commands never take a disk identifier; they find the
  card by the fingerprint.
- **Discovery reads metadata only**: list external physical disks
  (`diskutil list external physical`), read each one's `diskutil info` until
  exactly one matches. Zero or several matches → refuse. No other device is
  ever opened.
- **Re-check before I/O**: the fingerprint is checked again immediately before
  the raw device is opened.
- Show the card and require confirmation before any write.
- Support a dry-run mode that prints what would happen.

## Implementation language

**Decided: Python** (2026-10-18). It calls the native tools (`diskutil`,
`dd`, `lsblk`) via `subprocess`, and the safety and verdict logic is unit-tested.

Tradeoffs considered:

- **Shell**: no dependencies, natural for thin wrappers around `diskutil`,
  `dd` and `lsblk`. Harder to test, and macOS/Linux differences pile up in
  `if` branches.

- **Python**: a little more setup, but the safety checks and the
  platform-specific parsing can be unit-tested. It would still call the native
  tools via `subprocess`. Fits the existing scaffold (`ruff`, `pytest`).

## Non-goals

- No GUI.
- No Windows support.

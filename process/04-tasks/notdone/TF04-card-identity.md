# TF04 Card identity: on-card manifest and repo registry for Feature F04
**Date Created:** 2026-10-20

Task file name must be `TFNN-<slug>.md` where `NN` matches the feature number.
Each step is numbered `TFNN.N`, matching this file's own `TFNN` identifier
(e.g. a step in `TF03-<slug>.md` is `TF03.0`, `TF03.1`, ...), starting at `.0`.
For each task step, add a test when feasible. If not feasible, note why.

**Builds on F01/F02**: reader fingerprint and discovery, the `diskutil`
adapter, `Env` prompts, the image store's repo-root location and `SUDO_USER`
chown.

**Design rule**: same as F01. Manifest and registry logic are pure and tested
with temp dirs; `diskutil` calls (mount, erase) stay in the adapter and are
faked in tests. Stdlib only (`json`, `datetime`).

## TF04.0 — Manifest model
**Status**: done
**Description**: Pure module: ID validation (1–4 of `A–Z0–9`, upper-cased),
manifest fields (ID, contents, history), history entry (ISO date-time, event,
detail), JSON load and dump. A malformed manifest raises with the file and
reason; it is never silently replaced.

**Test**: valid and invalid IDs, case folding, round trip, malformed JSON,
missing fields, unknown event.

## TF04.1 — Repo registry
**Status**: done
**Description**: `.microsd_tools/cards.json` at the repo root, located from
the package and overridable for tests; created if missing; chowned to
`SUDO_USER` (share the image store's helper rather than copy it). Upsert a
card from its manifest with a last-seen time; look up by ID; list all. Add
`.microsd_tools/` to `.gitignore`.

**Test**: temp-dir create, upsert, lookup, list, chown target faked,
malformed registry raises.

## TF04.2 — Find and mount the card's FAT volume
**Status**: done
**Description**: Adapter additions: from the card's `diskutil` partition list,
pick its FAT partition (`DOS_FAT_32` / `Windows_FAT_32` / `Microsoft Basic
Data`), mount it if needed, return the mount point. Verify the volume's parent
disk is the fingerprinted card before any write. Zero FAT partitions → "none";
several → use the first and say which.

**Test**: plist fixtures for a Pi OS card, a factory exFAT/FAT32 card, a blank
card, two FAT partitions; parent-disk mismatch refused.

## TF04.3 — Read and write the manifest on the card
**Status**: done
**Description**: Read `.microsd_tools/manifest.json` from the mount point
(absent → none). Write it via a temp file and rename, honouring `--dry-run`
(print instead). Every write also upserts the registry.

**Test**: temp dir as mount point: absent, present, write then read back,
dry run writes nothing, registry updated.

## TF04.4 — Identify a card
**Status**: done
**Description**: Shared flow used by all commands: return the card's manifest,
or for an untagged card ask the user for the ID on its label. If the ID is in
the registry, show that entry and ask if it's the same card (yes → start from
its history). Optionally ask what's on the card. Read-only callers can skip
the prompt and get "untagged".

**Test**: scripted prompts for tagged, untagged-new, untagged-known-yes,
untagged-known-no, invalid ID re-asked, read-only skip.

## TF04.5 — `card` and `cards` commands
**Status**: done
**Description**: `microsd card`: show ID, contents, history; tag an untagged
card (shows the manifest, asks `y/N`); offer to update contents. `microsd
cards`: list the registry. Make targets `card` and `cards` with `##`
descriptions; README usage lines.

**Test**: CLI parse; output for tagged/untagged cards and an empty/non-empty
registry; Makefile test covers the new targets.

## TF04.6 — ID in validate and backup
**Status**: done
**Description**: `validate` and `backup` print the card's ID (or "untagged —
run make card") without writing to it. `backup` adds the source card ID to
the image sidecar.

**Test**: report line for tagged/untagged; sidecar field present, and absent
for untagged.

## TF04.7 — Stress keeps the manifest
**Status**: done
**Description**: Before the wipe: identify the card (asking for the ID if
untagged). After verify: `diskutil eraseDisk FAT32 <ID> MBRFormat` on the
fingerprinted disk, mount, write the manifest with a `formatted` and a
`stress` entry (grade); contents becomes "empty". If stress fails partway,
the manifest still goes to the registry with the failure noted.

**Test**: faked adapter records the erase call and its disk; manifest written
with both entries; failure path records to the registry only; dry run shows
the reformat step.

## TF04.8 — Flash and copy keep the target's manifest
**Status**: done
**Description**: Before writing: identify the target. After verify: re-probe
the disk, mount its FAT volume, write the target's manifest with a `flash`
(or `copy`) entry, contents = image name. No FAT volume → warn and record in
the registry only. In `copy`, the new card's ID must differ from the master's.

**Test**: faked adapter: manifest restored with the target's ID, never the
master's; same-ID refusal; no-FAT path; dry run.

## TF04.9 — Test suite
**Status**: done
**Description**: Complete the unit tests above in `tests/test_manifest.py`,
`tests/test_registry.py` and additions to the existing command tests; extend
`tests/fakes.py` with mount/erase fakes. Full `uv run pytest` passes.

**Test**: this task is the tests.

## TF04.10 — Real-card run
**Status**: not done
**Description**: Manual, on the card in the reader: `make card` to tag it,
`make stress`, `make card`, `make flash`, `make card`, `make cards`. Check the
**unverified** assumption that macOS sees the new partitions after a raw flash
without the card being reinserted; if not, the flash step asks the user to
reinsert it. Record results in `notes.md`.

**Test**: manual (`-m manual`) — needs the real reader and card.

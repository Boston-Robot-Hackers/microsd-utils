# Current

## Open

- **F05 — stress robustness, fixes I01**
  (`process/03-features/notdone/F05-stress-robustness.md`): code and tests
  done and committed (TF05.0–TF05.6, 263 tests pass). Stress records its
  result before formatting; card-changing `diskutil` calls time out; a lost
  card (`ENXIO`/`ENODEV`) stops the pass; long Makefile targets run under
  `caffeinate -i`; sizes under 1 GB print in MB. **TF05.7 open**, deferred
  by the user: pull the card mid-`make validate` (expect "card disconnected",
  record the errno; adjust `GONE_ERRNOS` in `passes.py` if it differs), then
  a full `make stress` and check `make history` lists `stress` before
  `formatted`. Then close F05 and move I01 to `closed/`. Note: on
  2026-10-21 a reader reset during flash showed macOS reports a lost reader
  as `[Errno 6]` (ENXIO), as F05 assumes.

- **Cards** (registry): R1 = the user's working Dome2 card (master); R2 and
  R4 = verified clones of it, both boot; R3 = retired (bad).

- **Images**: `images/` holds three ~12 GB images of the same card
  (`dome-2-master`, `dome-2-copy`, `dome-2-copy2`); the user may prune them.

- **Small follow-ups, not started** (need the user's go-ahead):
  `verify` exits 1 even when only the FAT boot partition differs, so `make`
  prints `Error 1` for a good card; Ctrl-C (now the normal way out of a
  `copy` swap wait) prints a Python traceback.

- **Hardware rule**: only the card in the NORELSYS reader on port
  `usb-drd2-port-ss@02200000` may be touched (fingerprint in `sd_reader.json`).
  Ask before running any disk command; never query other disks to build
  fixtures.

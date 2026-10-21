# Current

## Open

- **F04 — card identity** (`process/03-features/notdone/F04-card-identity.md`):
  code and unit tests done (TF04.0–TF04.9). **TF04.10 open**: real-card run.
  Done 2026-10-21: tag (R2) and `make stress` (formatted FAT32, manifest
  written, `stress` event recorded). Still to do: `make card`, `make flash`,
  `make card`, `make cards`. Check the unverified assumptions: macOS sees the
  new partitions after a raw flash (`mountDisk`, no reinsertion); `diskutil
  mount` on a mounted volume succeeds; `make card` can write the FAT volume
  without sudo; which `Content` types the reader reports (factory exFAT may
  show as `Windows_NTFS`).

- **F05 — stress robustness, fixes I01**
  (`process/03-features/notdone/F05-stress-robustness.md`): code and tests
  done and committed (TF05.0–TF05.6, 263 tests pass). Stress records its
  result before formatting; card-changing `diskutil` calls time out; a lost
  card (`ENXIO`/`ENODEV`) stops the pass; long Makefile targets run under
  `caffeinate -i`; sizes under 1 GB print in MB. **TF05.7 open**, deferred
  by the user: pull the card mid-`make validate` (expect "card disconnected",
  record the errno; adjust `GONE_ERRNOS` in `passes.py` if it differs), then
  a full `make stress` and check `make cards` lists `stress` before
  `formatted`. Then close F05 and move I01 to `closed/`.

- **F02 — backup, flash, copy** (`process/03-features/notdone/F02-card-copy.md`):
  code and 181 unit tests done (TF02.0–TF02.8). **TF02.9 open**: real-card run
  needs a Pi card — the test card was wiped by `make stress`. Suggested order:
  `make flash IMAGE=<raspios>.img.xz`, boot a Pi, `make backup NAME=pi-test`,
  `make copy NAME=pi-test2`, boot the copy. Record throughput, gzip cost, and
  whether the reader's disk vanishes from `diskutil` when the card is pulled
  (assumed by `swap.py`).

- **Hardware rule**: only the card in the NORELSYS reader on port
  `usb-drd2-port-ss@02200000` may be touched (fingerprint in `sd_reader.json`).
  Ask before running any disk command; never query other disks to build
  fixtures.

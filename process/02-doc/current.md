# Current

## Open

- **F04 — card identity** (`process/03-features/notdone/F04-card-identity.md`):
  code and unit tests done (TF04.0–TF04.9; 245 tests pass). **TF04.10 open**:
  real-card run — `make card` to tag, `make stress`, `make card`,
  `make flash`, `make card`, `make cards`. Check the unverified assumptions:
  macOS sees the new partitions after a raw flash (`mountDisk`, no
  reinsertion); `diskutil mount` on a mounted volume succeeds; `make card`
  can write the FAT volume without sudo; which `Content` types the reader
  reports (factory exFAT may show as `Windows_NTFS`). The stress in this run
  also gives TF03.6 its numbers.

- **Ruff `ERA001`**: flags every file header's `# Version:`/`# Created:` lines
  as commented-out code (93 hits, pre-existing). Needs a per-pattern ignore in
  the ruff config.

- **F02 — backup, flash, copy** (`process/03-features/notdone/F02-card-copy.md`):
  code and 181 unit tests done (TF02.0–TF02.8). **TF02.9 open**: real-card run
  needs a Pi card — the test card was wiped by `make stress`. Suggested order:
  `make flash IMAGE=<raspios>.img.xz`, boot a Pi, `make backup NAME=pi-test`,
  `make copy NAME=pi-test2`, boot the copy. Record throughput, gzip cost, and
  whether the reader's disk vanishes from `diskutil` when the card is pulled
  (assumed by `swap.py`).

- **F03 — graded verdict** (`process/03-features/notdone/F03-graded-verdict.md`):
  code done (TF03.0–TF03.5). **TF03.6 open**: `make validate` / `make stress`
  on a real card; check Python overhead doesn't cap 4 KB IOPS (compare with
  `iostat`), record IOPS in `notes.md`, recalibrate thresholds if needed.

- **Hardware rule**: only the card in the NORELSYS reader on port
  `usb-drd2-port-ss@02200000` may be touched (fingerprint in `sd_reader.json`).
  Ask before running any disk command; never query other disks to build
  fixtures.

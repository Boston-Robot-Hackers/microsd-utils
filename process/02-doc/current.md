# Current

## Open

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

- **Unanswered**: git remote is `micros-utils`, folder is `microsd-utils`; the
  README's `cd microsd-utils` breaks for a fresh clone. `run.bash` is now
  unused.

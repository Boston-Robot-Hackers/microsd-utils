# microsd-utils

Command-line tools for checking, backing up and copying microSD cards on macOS.

## Installation

```bash
git clone git@github.com:Boston-Robot-Hackers/micros-utils.git
cd microsd-utils
uv sync
```

## Usage

The tools only touch the card in the designated card reader (see
`sd_reader.json`); they take no disk argument and refuse to run if that reader
isn't found.

```bash
make                  # list targets
make validate         # read-only health check: errors, speed, verdict
make stress DRY_RUN=1 # show what the destructive check would do
make stress           # write + verify every block — WIPES the card

make backup NAME=pi-robot      # save the card as images/pi-robot.img.gz
make flash IMAGE=pi-robot      # write a saved image to the card — ERASES it
make flash IMAGE=~/Downloads/raspios.img.xz   # or any .img / .img.gz / .img.xz
make copy NAME=pi-robot        # back up a master card, swap, flash a new card
```

Add `DRY_RUN=1` to any of them to see the plan without touching the card.
Each command shows its plan, then re-runs itself under `sudo` (macOS asks for
your password). Anything that erases a card shows a warning and asks you to
type `yes` and then the card's identifier.

Backups copy only up to the end of the card's last partition, so an image of
a Pi card holds just its partitions and fits a slightly smaller card. Images
live in `images/` (git-ignored), each with a `.json` record of its size and
SHA-256; every flash is verified by reading it back.

The verdict is `EXCELLENT`, `GOOD`, `FAIR` or `RETIRE`, with its reasons:
the worse of a sequential-speed grade (SD speed classes) and a random 4 KB
grade (A1/A2 classes). Any error retires the card. A factory-fresh card also
gets a `Looks brand new` note. Exit code 0 for excellent / good / fair, 2 for
retire, 1 for errors or refusal.

## Development

```bash
uv run pytest          # unit tests
uv run pytest -m manual  # real-card tests (reader + card needed)
```

## License

MIT — see [LICENSE](LICENSE)

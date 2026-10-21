# History

## 2026-10-18 – 2026-10-19

- **Scaffold**: folder renamed to `microsd-utils`; spec written (macOS + Pi
  microSD tools, Python, safety section). Makefile reduced to user-facing
  targets (`help` default); dev commands run via `uv`. j3 kit got the
  `make help` and tool-first Makefile rules.

- **Safety design**: tools touch only the card in one USB reader, pinned by
  IORegistry name + exact USB port (`sd_reader.json`); no disk arguments;
  metadata-only discovery; fingerprint re-checked immediately before every
  raw open. Commands print their plan, then re-run under `sudo` with an
  explanation. Erasing needs an all-caps warning, `yes`, and the disk
  identifier.

- **F01 — health check, closed 2026-10-19**: `make validate` / `make stress`.
  Measured on the 64 GB test card: read 70.1 MB/s (893 s), stress write
  54.0 MB/s / verify 72.0 MB/s, 0 bad chunks, genuine capacity. Reader reports
  no SMART/wear data; raw reads work while mounted. Wrong-port refusal marked
  done at the user's direction (output not captured).

- **F03 code**: graded verdict (EXCELLENT / GOOD / FAIR / RETIRE) from
  sequential speed classes and A1/A2 random 4 KB IOPS; *looks brand new* as a
  note.

- **F02 code**: partition-table parser (MBR/GPT), image store in `images/`
  (atomic publish, sidecar with size + SHA-256, chown to the sudo user,
  `.img`/`.gz`/`.xz` input), backup, flash with double hash verification,
  card-swap waits, guided `copy`; shared `session.py` extracted from
  `check.py`. Review fix: copy's "looks like the master" check compared
  identifiers and mount points, so it could never fire; now compares layout.

- **Literate docs**: `process/01-literate/01`–`15` plus `X01`.

## 2026-10-20

- **Repo rename**: GitHub repo is now `Boston-Robot-Hackers/microsd-utils`;
  remote and README clone URL updated.

- **Makefile rule**: `run.bash` removed. The kit (style guide, Makefile/CLAUDE/
  README templates, bootstrap) now requires a Makefile with `make help` holding
  only user commands; dev commands run via `uv`. Same change in j3.

- **F04 code**: card identity. `manifest.py` (ID, manifest, registry),
  `identity.py` (peek / identify / store on the card's FAT volume),
  `cards.py` (`make card`, `make cards`). Stress reformats FAT32 named after
  the ID and writes the manifest back; flash and copy restore the target's own
  manifest; backup records the source card ID in the sidecar. Literate docs
  16–18 added, 02/09/12–15 updated.

## 2026-10-21

- **Ruff**: `Version`/`Created`/`Updated` added to `lint.task-tags`, so
  ERA001 no longer flags the stamped file headers (also in the kit template).

- **I01 opened**: a stress verdict is lost when the format step hangs (R3) or
  the Mac sleeps mid-pass (R2). Workaround: `caffeinate -i make stress`.

- **F03 — graded verdict, closed 2026-10-21** (TF03.6): R2 stress write
  59.9 MB/s, verify 71.2 MB/s, 0 bad chunks; random 1,499 read / 980 write
  IOPS. Python loop overhead is ~0.1% of a 4 KB read, and `iostat` matched
  the tool's rate. R2 sits on the A1 line (±2%, cold start ~7% slower), so
  grading now leans toward the better grade: `READER_MARGIN = 0.95` on the
  A1/A2 thresholds and a 20% uncounted warm-up per random pass. Literate
  docs 05 and 07 updated.

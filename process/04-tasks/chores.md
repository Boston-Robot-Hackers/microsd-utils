# Chores

- [x] README: `cd microsd` → `cd microsd-utils` after folder rename (2026-10-18)
- [x] Makefile: add `help` target (default goal) per style guide; also in `.claude/templates/Makefile.template` and j3 kit (2026-10-18)
- [x] Makefile: split `make help` into Tool / Development sections, rename dev `check` → `ci`; style guide rule that the Makefile serves the tool user first. Same in j3 kit (2026-10-18)
- [x] Makefile: tool targets only (help, validate, stress); dev commands moved to `uv` in CLAUDE.md/README, per user. Project-local deviation from the kit style guide's Development section (2026-10-18)
- [x] GitHub repo renamed `micros-utils` → `microsd-utils`; remote and README clone URL updated (2026-10-20)
- [x] Removed `run.bash`; kit now requires a tool-only Makefile with `make help` and no dev targets (style guide, Makefile/CLAUDE/README templates, bootstrap). Same in j3 kit (2026-10-20)
- [x] ruff: add `Version`/`Created`/`Updated` to `lint.task-tags` so ERA001 stops flagging the stamped file-header lines (111 hits); also in `.claude/templates/ruff.toml.template` (2026-10-21)
- [x] Card size shows "0.0 GB" for cards under 1 GB (R3, 32 MB); show MB below 1 GB — done in F05 (TF05.5), `human_size` (2026-10-21)
- [x] Renamed `make cards` / `microsd cards` to `make history` / `microsd history` (`run_cards` → `run_history`), per user; README, process docs and literate docs 15/18 updated (2026-10-21)
- [x] verify report: `regions` counted a chunk's regions through a set, so the order of the report lines changed between runs (flaky test); now first-byte region first, via `dict.fromkeys` (2026-10-22)

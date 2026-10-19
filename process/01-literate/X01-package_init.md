---
version: "1.0"
generated: "2026-10-18"
---

# Appendix X01 — `microsd_utils/__init__.py`

## What it is

The package marker for `microsd_utils`. It holds only the project's standard file header — no imports, no re-exports, no code.

## Why it is empty

- **No side effects at import time.** The style guide forbids them, and an `__init__` that imports submodules would run `diskutil`-adjacent code just by importing the package.
- **Explicit imports.** Callers write `from microsd_utils.reader import discover`, so every dependency is visible at the import site. There is no package-level API to keep in sync.

`tests/__init__.py` is the same, and exists so tests can share fakes via `from tests.fakes import …` (with `pythonpath = ["."]` in `pyproject.toml`).

## Observations

1. A `__version__` here, read from package metadata, would be the natural home for a future `microsd --version`.

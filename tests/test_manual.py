#!/usr/bin/env python3
# test_manual — end-to-end checks against the real card in the designated reader
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Manual tests: need the NORELSYS reader in its designated port with a card.

Run with `uv run pytest -m manual`. They read diskutil metadata only and never
open the device. The real reads and writes need root and are run by hand:
`make validate` / `make stress` (TF01.9) and `make backup` / `flash` / `copy`
(TF02.9).
"""

import pytest

from microsd_utils.cli import main
from microsd_utils.diskutil import Diskutil
from microsd_utils.reader import discover, load_fingerprint

pytestmark = pytest.mark.manual


def test_real_card_is_discovered():
    card = discover(Diskutil(), load_fingerprint())
    assert card.raw_device.startswith("/dev/rdisk")
    assert card.size_bytes > 0


@pytest.mark.parametrize(
    "argv", [["check", "--dry-run"], ["check", "--destructive", "--dry-run"]]
)
def test_dry_run_on_real_card(argv, capsys):
    assert main(argv) == 0
    assert "Dry run: nothing touched." in capsys.readouterr().out


@pytest.mark.parametrize("command", ["backup", "copy"])
def test_backup_and_copy_dry_run_on_real_card(command, capsys):
    assert main([command, "manual-test-never-saved", "--dry-run"]) == 0
    assert "Dry run: nothing touched." in capsys.readouterr().out


def test_flash_dry_run_on_real_card(tmp_path, capsys):
    image = tmp_path / "blank.img"
    image.write_bytes(bytes(1024 * 1024))
    assert main(["flash", str(image), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "WARNING: EVERYTHING ON THIS CARD WILL BE ERASED." in out
    assert "Dry run: nothing touched." in out

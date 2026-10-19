#!/usr/bin/env python3
# test_cli — tests for the microsd command-line interface
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import pytest

from microsd_utils.cli import main
from microsd_utils.images import ImageError
from microsd_utils.reader import ReaderError


@pytest.mark.parametrize("argv", [["--help"], ["check", "--help"]])
def test_help_exits_zero(argv):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 0


def test_reader_error_exits_one_with_message(monkeypatch, capsys):
    def no_card(*args):
        raise ReaderError("No card found")

    monkeypatch.setattr("microsd_utils.cli.run_check", no_card)
    assert main(["check"]) == 1
    assert "microsd: No card found" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv, target, expected",
    [
        (["check", "--destructive"], "run_check", (True, False)),
        (["backup", "pi", "--dry-run"], "run_backup", ("pi", True)),
        (["flash", "pi.img.xz"], "run_flash", ("pi.img.xz", False)),
        (["copy", "pi"], "run_copy", ("pi", False)),
    ],
)
def test_subcommands_dispatch(monkeypatch, argv, target, expected):
    calls = []
    monkeypatch.setattr(
        f"microsd_utils.cli.{target}", lambda env, *args: calls.append(args) or 0
    )
    assert main(argv) == 0
    assert calls == [expected]


@pytest.mark.parametrize("argv", [["backup"], ["flash"], ["copy"], ["erase"]])
def test_missing_or_unknown_arguments_exit_two(argv):
    with pytest.raises(SystemExit) as exit_info:
        main(argv)
    assert exit_info.value.code == 2


def test_image_error_exits_one_with_message(monkeypatch, capsys):
    def exists(*args):
        raise ImageError("image 'pi' already exists")

    monkeypatch.setattr("microsd_utils.cli.run_backup", exists)
    assert main(["backup", "pi"]) == 1
    assert "microsd: image 'pi' already exists" in capsys.readouterr().err

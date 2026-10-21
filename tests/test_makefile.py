#!/usr/bin/env python3
# test_makefile — the Makefile's tool targets run the expected commands
# Author: Pito Salas and Claude Code
# Version: 3
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def make(*args: str) -> str:
    result = subprocess.run(
        ["make", "--no-print-directory", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.mark.parametrize(
    "args, command",
    [
        (["validate"], "caffeinate -i .venv/bin/microsd check"),
        (["stress"], "caffeinate -i .venv/bin/microsd check --destructive"),
        (
            ["stress", "DRY_RUN=1"],
            "caffeinate -i .venv/bin/microsd check --destructive --dry-run",
        ),
        (["backup", "NAME=pi"], 'caffeinate -i .venv/bin/microsd backup "pi"'),
        (
            ["flash", "IMAGE=pi", "DRY_RUN=1"],
            'caffeinate -i .venv/bin/microsd flash "pi" --dry-run',
        ),
        (["copy", "NAME=pi"], 'caffeinate -i .venv/bin/microsd copy "pi"'),
        (["card"], ".venv/bin/microsd card"),
        (["card", "DRY_RUN=1"], ".venv/bin/microsd card --dry-run"),
        (["cards"], ".venv/bin/microsd cards"),
    ],
)
def test_tool_target_commands(args, command):
    assert make("-n", *args).strip().splitlines()[-1].strip() == command


def test_help_lists_only_tool_targets():
    targets = [line.split()[0] for line in make("help").splitlines()]
    assert targets == [
        "help",
        "validate",
        "stress",
        "backup",
        "flash",
        "copy",
        "card",
        "cards",
    ]


@pytest.mark.parametrize("target", ["backup", "flash", "copy"])
def test_missing_variable_prints_usage(target):
    result = subprocess.run(
        ["make", "--no-print-directory", target],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert f"usage: make {target}" in result.stdout

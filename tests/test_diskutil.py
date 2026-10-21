#!/usr/bin/env python3
# test_diskutil — tests for the diskutil adapter's timeouts, with subprocess faked
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-21
# Updated: 2026-10-21
# Open Source Under MIT license

import subprocess

import pytest

from microsd_utils.diskutil import (
    CHANGE_TIMEOUT_S,
    ERASE_TIMEOUT_S,
    Diskutil,
    DiskutilTimeout,
)


@pytest.fixture
def calls(monkeypatch):
    """Records each subprocess.run call as (args, timeout); runs nothing."""
    recorded = []

    def fake_run(args, **kwargs):
        recorded.append((args, kwargs.get("timeout")))
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr("microsd_utils.diskutil.subprocess.run", fake_run)
    return recorded


@pytest.mark.parametrize(
    "call, timeout_s",
    [
        (lambda d: d.unmount_disk("disk4"), CHANGE_TIMEOUT_S),
        (lambda d: d.mount_disk("disk4"), CHANGE_TIMEOUT_S),
        (lambda d: d.eject("disk4"), CHANGE_TIMEOUT_S),
        (lambda d: d.erase_fat32("disk4", "R2"), ERASE_TIMEOUT_S),
    ],
)
def test_card_changing_calls_have_a_timeout(calls, call, timeout_s):
    call(Diskutil())
    assert calls[0][1] == timeout_s


def test_mount_has_a_timeout(calls, monkeypatch):
    monkeypatch.setattr(
        "microsd_utils.diskutil.run_plist", lambda args: {"MountPoint": "/Volumes/R2"}
    )
    assert Diskutil().mount("disk4s1") == "/Volumes/R2"
    assert calls == [(["diskutil", "mount", "disk4s1"], CHANGE_TIMEOUT_S)]


def test_timeout_names_the_command(monkeypatch):
    def hang(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr("microsd_utils.diskutil.subprocess.run", hang)
    with pytest.raises(DiskutilTimeout) as caught:
        Diskutil().erase_fat32("disk4", "R3")
    assert str(caught.value) == (
        f"diskutil eraseDisk FAT32 R3 MBRFormat disk4 did not finish in "
        f"{ERASE_TIMEOUT_S} s"
    )

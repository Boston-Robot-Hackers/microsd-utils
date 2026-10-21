#!/usr/bin/env python3
# diskutil — thin adapter over the macOS `diskutil` command
# Author: Pito Salas and Claude Code
# Version: 3
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license
"""Run `diskutil` and return its plist output as dicts.

Only disk identifiers (`diskN`, or `diskNsM` where a partition is meant) are
accepted, so a typo or a parsed value can never turn into an arbitrary path.

Commands that change the card (unmount, mount, eject, erase) run with a
timeout: a card that stops completing writes would otherwise hang `diskutil`,
and the tool with it, with no output.
"""

import plistlib
import re
import subprocess

WHOLE_DISK_RE = re.compile(r"disk\d+")
PARTITION_RE = re.compile(r"disk\d+s\d+")
# A failing card hung eraseDisk for over 6 minutes.
ERASE_TIMEOUT_S = 300
CHANGE_TIMEOUT_S = 60


class DiskutilTimeout(TimeoutError):
    """A diskutil command that changes the card didn't finish in time."""


def require_whole_disk(identifier: str) -> None:
    if not WHOLE_DISK_RE.fullmatch(identifier):
        raise ValueError(f"not a whole-disk identifier: {identifier!r}")


def require_partition(identifier: str) -> None:
    if not PARTITION_RE.fullmatch(identifier):
        raise ValueError(f"not a partition identifier: {identifier!r}")


def run_change(args: list[str], timeout_s: int) -> None:
    try:
        subprocess.run(
            ["diskutil", *args], capture_output=True, check=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired as error:
        command = " ".join(["diskutil", *args])
        raise DiskutilTimeout(f"{command} did not finish in {timeout_s} s") from error


def run_plist(args: list[str]) -> dict:
    result = subprocess.run(["diskutil", *args], capture_output=True, check=True)
    return plistlib.loads(result.stdout)


class Diskutil:
    def list_external_physical(self) -> dict:
        return run_plist(["list", "-plist", "external", "physical"])

    def info(self, identifier: str) -> dict:
        require_whole_disk(identifier)
        return run_plist(["info", "-plist", identifier])

    def unmount_disk(self, identifier: str) -> None:
        run_command("unmountDisk", identifier)

    def eject(self, identifier: str) -> None:
        run_command("eject", identifier)

    def mount_disk(self, identifier: str) -> None:
        run_command("mountDisk", identifier)

    def mount(self, partition: str) -> str:
        """Mount a partition (no-op if mounted) and return its mount point."""
        require_partition(partition)
        run_change(["mount", partition], CHANGE_TIMEOUT_S)
        return run_plist(["info", "-plist", partition])["MountPoint"]

    def erase_fat32(self, identifier: str, volume_name: str) -> None:
        require_whole_disk(identifier)
        run_change(
            ["eraseDisk", "FAT32", volume_name, "MBRFormat", identifier],
            ERASE_TIMEOUT_S,
        )


def run_command(verb: str, identifier: str) -> None:
    require_whole_disk(identifier)
    run_change([verb, identifier], CHANGE_TIMEOUT_S)

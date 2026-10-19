#!/usr/bin/env python3
# diskutil — thin adapter over the macOS `diskutil` command
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Run `diskutil` and return its plist output as dicts.

Only whole-disk identifiers (`diskN`) are accepted, so a typo or a parsed
value can never turn into an arbitrary path or partition argument.
"""

import plistlib
import re
import subprocess

WHOLE_DISK_RE = re.compile(r"disk\d+")


def require_whole_disk(identifier: str) -> None:
    if not WHOLE_DISK_RE.fullmatch(identifier):
        raise ValueError(f"not a whole-disk identifier: {identifier!r}")


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


def run_command(verb: str, identifier: str) -> None:
    require_whole_disk(identifier)
    subprocess.run(["diskutil", verb, identifier], capture_output=True, check=True)

#!/usr/bin/env python3
# session — what every microsd command shares: environment, elevation, prompts
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-20
# Open Source Under MIT license
"""The pieces every command uses.

- `Env` carries every side effect (diskutil, device access, prompts, output,
  clock), so each command's whole flow is tested with fakes.
- `preflight` prints the plan, stops for a dry run, and otherwise re-runs
  the command under sudo after saying why a password is coming. Commands
  call it before touching any device.
- `confirmed_erase` is the two-step confirmation in front of anything that
  overwrites a card: an explicit "yes", then the card's identifier.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from microsd_utils.images import ImageStore
from microsd_utils.manifest import Registry
from microsd_utils.reader import CardInfo, DiskutilQueries, Fingerprint
from microsd_utils.swap import Poll

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_RETIRE = 2

SUDO_NOTE = (
    "Reading or writing the card's raw device needs administrator rights, so\n"
    "microsd now re-runs itself with sudo. macOS may ask for your login password."
)


class DiskutilCommands(DiskutilQueries, Protocol):
    def unmount_disk(self, identifier: str) -> None: ...

    def eject(self, identifier: str) -> None: ...

    def mount_disk(self, identifier: str) -> None: ...

    def mount(self, partition: str) -> str: ...

    def erase_fat32(self, identifier: str, volume_name: str) -> None: ...


@dataclass
class Env:
    diskutil: DiskutilCommands
    fingerprint: Fingerprint
    open_device: Callable[[CardInfo, bool], object]
    list_volume: Callable[[str], list[str]]
    ask: Callable[[str], str]
    out: Callable[..., None]
    is_root: bool
    elevate: Callable[[], int]
    random_seconds: float
    images: ImageStore
    registry: Registry
    poll: Poll
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    now: Callable[[], datetime]

    @property
    def wait_timing(self) -> dict:
        return {"clock": self.clock, "sleep": self.sleep}


def gigabytes(size_bytes: int) -> str:
    return f"{size_bytes / 1e9:.1f} GB"


def card_line(label: str, card: CardInfo) -> str:
    return (
        f"{label}: {card.identifier}  {card.media_name}  {gigabytes(card.size_bytes)}"
    )


def progress_printer(
    label: str, out: Callable[..., None]
) -> Callable[[int, int], None]:
    last_percent = -1

    def show(done_bytes: int, total_bytes: int) -> None:
        nonlocal last_percent
        percent = done_bytes * 100 // total_bytes
        if percent != last_percent:
            last_percent = percent
            out(f"\r{label} {percent:3d}%", end="\n" if percent == 100 else "")

    return show


def erase_warning(card: CardInfo) -> str:
    rule = "!" * 72
    return (
        f"{rule}\n"
        f"  WARNING: EVERYTHING ON THIS CARD WILL BE ERASED.\n"
        f"  ALL FILES AND PARTITIONS ON {card.identifier} ({card.media_name}, "
        f"{gigabytes(card.size_bytes)}) WILL BE DESTROYED.\n"
        f"  THIS CANNOT BE UNDONE.\n"
        f"{rule}"
    )


def preflight(env: Env, plan: str, is_dry_run: bool) -> int | None:
    """Print the plan; return an exit code if the command should stop here
    (dry run, or handed over to sudo), None to carry on as root."""
    env.out(plan)
    if is_dry_run:
        env.out("Dry run: nothing touched.")
        return EXIT_OK
    if not env.is_root:
        env.out(SUDO_NOTE)
        return env.elevate()
    return None


def is_yes(answer: str) -> bool:
    return answer.strip().lower() in ("y", "yes")


def confirmed_erase(env: Env, card: CardInfo) -> bool:
    """Two separate answers: an explicit "yes", then the card's identifier,
    so a reflexive Enter or "y" can never start an erase."""
    if env.ask("ARE YOU SURE you want to ERASE this card? Type yes: ").strip() != "yes":
        return False
    answer = env.ask(f"Type {card.identifier} to confirm which card to erase: ")
    return answer.strip() == card.identifier

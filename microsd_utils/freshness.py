#!/usr/bin/env python3
# freshness — does the card still look the way it left the factory?
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Signal for the *brand new* verdict.

A factory card has one FAT32 or exFAT partition spanning (almost) the whole
card, and no files on it beyond what macOS itself creates on mount. Cards
don't report wear, so this layout is the only hint that a card is unused.
"""

from dataclasses import dataclass

from microsd_utils.reader import CardInfo

# diskutil's partition content names for FAT32 and exFAT. On MBR, exFAT uses
# the same type byte as NTFS, so diskutil reports it as Windows_NTFS.
FACTORY_CONTENTS = {"DOS_FAT_32", "Windows_FAT_32", "Windows_NTFS"}
# Factory cards leave a few MB before the partition for erase-block alignment.
MIN_PARTITION_SHARE = 0.95
MACOS_MOUNT_FILES = {
    ".Spotlight-V100",
    ".fseventsd",
    ".Trashes",
    ".TemporaryItems",
    "System Volume Information",
}


@dataclass(frozen=True)
class Freshness:
    is_fresh: bool
    reason: str


def assess(card: CardInfo, top_level_names: list[str] | None) -> Freshness:
    """`top_level_names` lists the mounted volume's root, or None if the
    card's partition is not mounted."""
    if len(card.partitions) != 1:
        return Freshness(False, f"{len(card.partitions)} partitions, factory has 1")
    partition = card.partitions[0]
    if partition.content not in FACTORY_CONTENTS:
        return Freshness(False, f"partition type {partition.content} is not FAT/exFAT")
    if partition.size_bytes < MIN_PARTITION_SHARE * card.size_bytes:
        return Freshness(False, "partition does not span the card")
    if top_level_names is None:
        return Freshness(False, "volume not mounted, can't check for files")
    user_files = [
        name
        for name in top_level_names
        if name not in MACOS_MOUNT_FILES and not name.startswith("._")
    ]
    if user_files:
        return Freshness(False, f"{len(user_files)} files or folders on the card")
    return Freshness(True, "factory layout, no files")

#!/usr/bin/env python3
# reader — find the card in the designated reader, and refuse anything else
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Locate the microSD card in the one card reader these tools may touch.

The reader is pinned by a fingerprint in `sd_reader.json` at the repo root:
its IORegistry name, its exact USB port path (`DeviceTreePath`) and its bus
protocol. A disk is the card only if it matches all three *and* is a whole,
physical, non-internal, removable disk.

Discovery works on `diskutil` metadata only. It never opens a device node:
callers open the raw device only after `recheck` confirms the identifier still
belongs to the fingerprinted reader.

The `diskutil` calls go through an injected adapter (see `diskutil.py`) so
everything here is tested against captured plists.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

FINGERPRINT_PATH = Path(__file__).resolve().parent.parent / "sd_reader.json"


class ReaderError(Exception):
    """The card can't be located safely; nothing has been touched."""


class NoCardError(ReaderError):
    """The designated reader has no card, or isn't in its port."""


@dataclass(frozen=True)
class Fingerprint:
    registry_name: str
    device_tree_path: str
    bus_protocol: str


@dataclass(frozen=True)
class Partition:
    identifier: str
    content: str
    size_bytes: int
    mount_point: str | None


@dataclass(frozen=True)
class CardInfo:
    identifier: str
    size_bytes: int
    block_size_bytes: int
    media_name: str
    partitions: tuple[Partition, ...]

    @property
    def raw_device(self) -> str:
        return f"/dev/r{self.identifier}"


class DiskutilQueries(Protocol):
    def list_external_physical(self) -> dict: ...

    def info(self, identifier: str) -> dict: ...


def load_fingerprint(path: Path = FINGERPRINT_PATH) -> Fingerprint:
    fields = json.loads(path.read_text())
    return Fingerprint(**fields)


def mismatches(info: dict, fingerprint: Fingerprint) -> list[str]:
    """Return why a `diskutil info` plist is not the card; empty if it is."""
    expected = {
        "IORegistryEntryName": fingerprint.registry_name,
        "DeviceTreePath": fingerprint.device_tree_path,
        "BusProtocol": fingerprint.bus_protocol,
        "WholeDisk": True,
        "VirtualOrPhysical": "Physical",
        "Internal": False,
        "RemovableMedia": True,
    }
    return [
        f"{key} is {info.get(key)!r}, expected {value!r}"
        for key, value in expected.items()
        if info.get(key) != value
    ]


def parse_card(info: dict, disk_list: dict) -> CardInfo:
    """Build a CardInfo from the card's `diskutil info` plist and the
    `diskutil list -plist` output that contains it."""
    identifier = info["DeviceIdentifier"]
    entries = [
        entry
        for entry in disk_list["AllDisksAndPartitions"]
        if entry["DeviceIdentifier"] == identifier
    ]
    if len(entries) != 1:
        raise ReaderError(f"{identifier} appears {len(entries)} times in diskutil list")
    partitions = tuple(
        Partition(
            identifier=part["DeviceIdentifier"],
            content=part["Content"],
            size_bytes=part["Size"],
            mount_point=part.get("MountPoint"),
        )
        # A blank card with no partition table has no Partitions key.
        for part in entries[0].get("Partitions", [])
    )
    return CardInfo(
        identifier=identifier,
        size_bytes=info["Size"],
        block_size_bytes=info["DeviceBlockSize"],
        media_name=info["MediaName"],
        partitions=partitions,
    )


def discover(diskutil: DiskutilQueries, fingerprint: Fingerprint) -> CardInfo:
    """Find exactly one card in the fingerprinted reader, or raise."""
    disk_list = diskutil.list_external_physical()
    matches = []
    for identifier in disk_list["WholeDisks"]:
        info = diskutil.info(identifier)
        if not mismatches(info, fingerprint):
            matches.append(info)
    if not matches:
        raise NoCardError(
            "No card found in the designated reader "
            f"({fingerprint.registry_name}). Is the reader in its usual port "
            "with a card in it?"
        )
    if len(matches) > 1:
        names = ", ".join(info["DeviceIdentifier"] for info in matches)
        raise ReaderError(f"Several disks match the reader fingerprint: {names}")
    return parse_card(matches[0], disk_list)


def recheck(
    diskutil: DiskutilQueries, fingerprint: Fingerprint, card: CardInfo
) -> None:
    """Confirm `card.identifier` is still the same card in the reader.

    Call immediately before opening the raw device: disk identifiers are
    reassigned when devices come and go.
    """
    info = diskutil.info(card.identifier)
    reasons = mismatches(info, fingerprint)
    if info.get("Size") != card.size_bytes:
        reasons.append(f"size is {info.get('Size')}, expected {card.size_bytes}")
    if reasons:
        raise ReaderError(
            f"{card.identifier} is no longer the card in the reader: "
            + "; ".join(reasons)
        )

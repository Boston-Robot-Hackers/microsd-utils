#!/usr/bin/env python3
# fakes — in-memory stand-ins for diskutil and the card, shared by tests
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-20
# Open Source Under MIT license

import plistlib
import struct
from datetime import datetime
from pathlib import Path

from microsd_utils.images import ImageStore
from microsd_utils.manifest import Event, Manifest, Registry, write_manifest
from microsd_utils.reader import load_fingerprint
from microsd_utils.session import Env
from microsd_utils.swap import card_poll

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 20, 14, 5, 0)
NOW_TEXT = "2026-10-20T14:05:00"


def load_plist(name: str) -> dict:
    return plistlib.loads((FIXTURES / name).read_bytes())


class FakeDiskutil:
    """`volume_dir` stands in for wherever macOS mounts the card's FAT
    partition; `erased` records (disk, volume name) per erase."""

    def __init__(
        self,
        disk_list: dict,
        infos: dict[str, dict],
        volume_dir: Path = Path("/nonexistent/volume"),
    ):
        self.disk_list = disk_list
        self.infos = infos
        self.volume_dir = volume_dir
        self.unmounted = []
        self.ejected = []
        self.mounted = []
        self.erased = []

    def list_external_physical(self) -> dict:
        return self.disk_list

    def info(self, identifier: str) -> dict:
        return self.infos[identifier]

    def unmount_disk(self, identifier: str) -> None:
        self.unmounted.append(identifier)

    def eject(self, identifier: str) -> None:
        self.ejected.append(identifier)

    def mount_disk(self, identifier: str) -> None:
        self.mounted.append(identifier)

    def mount(self, partition: str) -> str:
        self.mounted.append(partition)
        return str(self.volume_dir)

    def erase_fat32(self, identifier: str, volume_name: str) -> None:
        self.erased.append((identifier, volume_name))


class FakeCard:
    """In-memory card. `real_bytes` below the advertised size makes it wrap
    writes around like a fake-capacity card; `corrupt_offset` flips a byte
    on every read of that chunk; `failing_offset` raises on read there."""

    def __init__(self, size, real_bytes=None, corrupt_offset=None, failing_offset=None):
        self.real_bytes = real_bytes or size
        self.store = bytearray(self.real_bytes)
        self.corrupt_offset = corrupt_offset
        self.failing_offset = failing_offset
        self.write_log = []

    @property
    def writes(self):
        return len(self.write_log)

    def write_at(self, offset, data):
        self.write_log.append((offset, len(data)))
        start = offset % self.real_bytes
        self.store[start : start + len(data)] = data

    def read_at(self, offset, length):
        if offset == self.failing_offset:
            raise OSError("I/O error")
        start = offset % self.real_bytes
        data = bytearray(self.store[start : start + length])
        if offset == self.corrupt_offset:
            data[0] ^= 0xFF
        return bytes(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass


class Recorder:
    """Collects output and prompts, answers prompts from a script, and
    records which devices were opened and whether for writing."""

    def __init__(self, answers=()):
        self.lines = []
        self.answers = list(answers)
        self.prompts = []
        self.opened = []

    def out(self, text="", end="\n"):
        self.lines.append(text)

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""

    def elevate(self):
        self.lines.append("<sudo>")
        return 0

    @property
    def text(self):
        return "\n".join(self.lines)


def tag(volume_dir: Path, card_id: str = "A1") -> Manifest:
    """Put a manifest for `card_id` on a fake card volume."""
    manifest = Manifest(card_id, "raspios", (Event(NOW_TEXT, "tagged", ""),))
    write_manifest(volume_dir, manifest)
    return manifest


def make_test_env(
    recorder, devices, card_bytes, extra_disks=0, work_dir=None, **env_fields
):
    """An Env whose reader holds disk4 (the captured card, resized to
    `card_bytes`); `devices` maps identifiers to FakeCards. The card's FAT
    volume is `work_dir/volume` and the registry `work_dir/cards.json`; with
    no `work_dir` they point nowhere, so the card reads as untagged.
    `env_fields` override any Env field (is_root, images, poll, ...)."""
    work_dir = work_dir or Path("/nonexistent/work")
    info = load_plist("norelsys-card-info.plist")
    info["Size"] = card_bytes
    disk_list = load_plist("norelsys-card-list.plist")
    infos = {"disk4": info}
    for i in range(extra_disks):
        twin = f"disk{5 + i}"
        infos[twin] = dict(info, DeviceIdentifier=twin)
        disk_list["WholeDisks"].append(twin)

    def open_device(card_info, is_writable):
        recorder.opened.append((card_info.identifier, is_writable))
        return devices[card_info.identifier]

    clock = [0.0]

    def sleep(seconds):
        clock[0] += seconds

    diskutil = FakeDiskutil(disk_list, infos, work_dir / "volume")
    fingerprint = load_fingerprint()
    fields = {
        "diskutil": diskutil,
        "fingerprint": fingerprint,
        "open_device": open_device,
        "list_volume": lambda path: [],
        "ask": recorder.ask,
        "out": recorder.out,
        "is_root": True,
        "elevate": recorder.elevate,
        "random_seconds": 0.01,
        "images": ImageStore(Path("/nonexistent/images")),
        "poll": card_poll(diskutil, fingerprint),
        "clock": lambda: clock[0],
        "sleep": sleep,
        "registry": Registry(work_dir / "cards.json"),
        "now": lambda: NOW,
    }
    return Env(**(fields | env_fields))


def partitioned_card(card_bytes: int, data_bytes: int) -> FakeCard:
    """A card with distinct content and one MBR partition ending at
    `data_bytes`, like a Pi card on a bigger card."""
    card = FakeCard(card_bytes)
    card.store[:] = (bytes(range(251)) * (card_bytes // 251 + 1))[:card_bytes]
    sector0 = bytearray(512)
    sector0[446 + 4] = 0x83
    struct.pack_into("<II", sector0, 446 + 8, 0, data_bytes // 512)
    sector0[510:512] = b"\x55\xaa"
    card.store[:512] = sector0
    return card

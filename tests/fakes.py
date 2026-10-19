#!/usr/bin/env python3
# fakes — in-memory stand-ins for diskutil and the card, shared by tests
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import plistlib
import struct
from pathlib import Path

from microsd_utils.images import ImageStore
from microsd_utils.reader import load_fingerprint
from microsd_utils.session import Env

FIXTURES = Path(__file__).parent / "fixtures"


def load_plist(name: str) -> dict:
    return plistlib.loads((FIXTURES / name).read_bytes())


class FakeDiskutil:
    def __init__(self, disk_list: dict, infos: dict[str, dict]):
        self.disk_list = disk_list
        self.infos = infos
        self.unmounted = []
        self.ejected = []

    def list_external_physical(self) -> dict:
        return self.disk_list

    def info(self, identifier: str) -> dict:
        return self.infos[identifier]

    def unmount_disk(self, identifier: str) -> None:
        self.unmounted.append(identifier)

    def eject(self, identifier: str) -> None:
        self.ejected.append(identifier)


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


def make_test_env(recorder, devices, card_bytes, extra_disks=0, **env_fields):
    """An Env whose reader holds disk4 (the captured card, resized to
    `card_bytes`); `devices` maps identifiers to FakeCards. `env_fields`
    override any Env field (is_root, images, poll, ...)."""
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

    fields = {
        "diskutil": FakeDiskutil(disk_list, infos),
        "fingerprint": load_fingerprint(),
        "open_device": open_device,
        "list_volume": lambda path: [],
        "ask": recorder.ask,
        "out": recorder.out,
        "is_root": True,
        "elevate": recorder.elevate,
        "random_seconds": 0.01,
        "images": ImageStore(Path("/nonexistent/images")),
        "poll": lambda: None,
        "clock": lambda: clock[0],
        "sleep": sleep,
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

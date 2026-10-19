#!/usr/bin/env python3
# test_reader — tests for locating the card in the designated reader
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import pytest

from microsd_utils.device import open_card
from microsd_utils.diskutil import require_whole_disk
from microsd_utils.reader import (
    FINGERPRINT_PATH,
    ReaderError,
    discover,
    load_fingerprint,
    mismatches,
    parse_card,
    recheck,
)
from tests.fakes import FakeDiskutil, load_plist


@pytest.fixture
def card_info():
    return load_plist("norelsys-card-info.plist")


@pytest.fixture
def card_list():
    return load_plist("norelsys-card-list.plist")


@pytest.fixture
def fingerprint():
    return load_fingerprint()


def test_fingerprint_file_matches_real_capture(card_info, fingerprint):
    assert FINGERPRINT_PATH.name == "sd_reader.json"
    assert mismatches(card_info, fingerprint) == []


@pytest.mark.parametrize(
    "key, value",
    [
        ("DeviceTreePath", "IODeviceTree:/arm-io@10F00000/usb-drd/other-port"),
        ("IORegistryEntryName", "Generic STORAGE DEVICE Media"),
        ("BusProtocol", "Secure Digital"),
        ("Internal", True),
        ("VirtualOrPhysical", "Virtual"),
        ("WholeDisk", False),
        ("RemovableMedia", False),
    ],
)
def test_any_difference_is_refused(card_info, fingerprint, key, value):
    card_info[key] = value
    assert len(mismatches(card_info, fingerprint)) == 1


def test_missing_key_is_refused(card_info, fingerprint):
    del card_info["DeviceTreePath"]
    assert mismatches(card_info, fingerprint)


def test_parse_card(card_info, card_list):
    card = parse_card(card_info, card_list)
    assert card.identifier == "disk4"
    assert card.raw_device == "/dev/rdisk4"
    assert card.size_bytes == 62599987200
    assert card.block_size_bytes == 512
    assert [p.content for p in card.partitions] == ["Windows_FAT_32", "Linux"]
    assert card.partitions[0].mount_point == "/Volumes/system-boot"
    assert card.partitions[1].mount_point is None


def test_discover_one_match(card_info, card_list, fingerprint):
    diskutil = FakeDiskutil(card_list, {"disk4": card_info})
    assert discover(diskutil, fingerprint).identifier == "disk4"


def test_discover_skips_other_disks(card_info, card_list, fingerprint):
    other = dict(card_info, DeviceIdentifier="disk5", DeviceTreePath="elsewhere")
    card_list["WholeDisks"] = ["disk5", "disk4"]
    diskutil = FakeDiskutil(card_list, {"disk4": card_info, "disk5": other})
    assert discover(diskutil, fingerprint).identifier == "disk4"


def test_discover_no_card(card_list, fingerprint):
    card_list["WholeDisks"] = []
    with pytest.raises(ReaderError, match="No card found"):
        discover(FakeDiskutil(card_list, {}), fingerprint)


def test_discover_two_matches(card_info, card_list, fingerprint):
    twin = dict(card_info, DeviceIdentifier="disk5")
    card_list["WholeDisks"] = ["disk4", "disk5"]
    diskutil = FakeDiskutil(card_list, {"disk4": card_info, "disk5": twin})
    with pytest.raises(ReaderError, match="disk4, disk5"):
        discover(diskutil, fingerprint)


def test_recheck_passes_for_same_card(card_info, card_list, fingerprint):
    card = parse_card(card_info, card_list)
    recheck(FakeDiskutil(card_list, {"disk4": card_info}), fingerprint, card)


def test_recheck_fails_when_identifier_moved(card_info, card_list, fingerprint):
    card = parse_card(card_info, card_list)
    moved = dict(card_info, DeviceTreePath="elsewhere")
    with pytest.raises(ReaderError, match="no longer the card"):
        recheck(FakeDiskutil(card_list, {"disk4": moved}), fingerprint, card)


def test_recheck_fails_when_size_changed(card_info, card_list, fingerprint):
    card = parse_card(card_info, card_list)
    swapped = dict(card_info, Size=31914983424)
    with pytest.raises(ReaderError, match="size is"):
        recheck(FakeDiskutil(card_list, {"disk4": swapped}), fingerprint, card)


@pytest.mark.parametrize(
    "identifier", ["disk4s1", "/dev/disk4", "disk", "disk4 ; x", "disk4\n"]
)
def test_require_whole_disk_rejects(identifier):
    with pytest.raises(ValueError):
        require_whole_disk(identifier)


def test_open_card_refuses_before_opening(
    card_info, card_list, fingerprint, monkeypatch
):
    card = parse_card(card_info, card_list)
    moved = dict(card_info, DeviceTreePath="elsewhere")

    def fail_open(*args):
        raise AssertionError("device must not be opened")

    monkeypatch.setattr("os.open", fail_open)
    with pytest.raises(ReaderError):
        open_card(FakeDiskutil(card_list, {"disk4": moved}), fingerprint, card, False)

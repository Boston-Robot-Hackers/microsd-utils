#!/usr/bin/env python3
# test_partitions — tests for finding where a card's partitions end
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import struct

import pytest

from microsd_utils.partitions import HEADER_BYTES, PartitionError, data_end

BLOCK = 512
CARD_BYTES = 62_599_987_200


def mbr(*entries: tuple[int, int, int]) -> bytearray:
    """Header with an MBR holding (type, start LBA, sectors) entries."""
    header = bytearray(HEADER_BYTES)
    for index, (part_type, start, sectors) in enumerate(entries):
        offset = 446 + 16 * index
        header[offset + 4] = part_type
        struct.pack_into("<II", header, offset + 8, start, sectors)
    header[510:512] = b"\x55\xaa"
    return header


def gpt(*last_lbas: int, entry_count: int = 128) -> bytearray:
    header = mbr((0xEE, 1, 0xFFFFFFFF))
    gpt_header = bytearray(BLOCK)
    gpt_header[:8] = b"EFI PART"
    struct.pack_into("<QII", gpt_header, 72, 2, entry_count, 128)
    header[BLOCK : 2 * BLOCK] = gpt_header
    for index, last_lba in enumerate(last_lbas):
        entry = 2 * BLOCK + index * 128
        header[entry : entry + 16] = b"\x01" * 16
        struct.pack_into("<Q", header, entry + 40, last_lba)
    return header


def test_pi_os_mbr():
    # FAT32 boot partition then a Linux root partition, as Pi OS lays out.
    header = mbr((0x0C, 8192, 1_048_576), (0x83, 1_056_768, 10_000_000))
    assert data_end(header, BLOCK, CARD_BYTES) == (1_056_768 + 10_000_000) * BLOCK


def test_mbr_entry_order_does_not_matter():
    header = mbr((0x83, 1_056_768, 10_000_000), (0x0C, 8192, 1_048_576))
    assert data_end(header, BLOCK, CARD_BYTES) == (1_056_768 + 10_000_000) * BLOCK


def test_factory_exfat_spans_card():
    sectors = CARD_BYTES // BLOCK - 32_768
    header = mbr((0x07, 32_768, sectors))
    assert data_end(header, BLOCK, CARD_BYTES) == CARD_BYTES


def test_gpt():
    assert data_end(gpt(500_000, 2_000_000), BLOCK, CARD_BYTES) == 2_000_001 * BLOCK


def test_blank_card_has_no_table():
    assert data_end(bytes(HEADER_BYTES), BLOCK, CARD_BYTES) is None


def test_partition_past_card_end_is_corrupt():
    header = mbr((0x83, 2048, CARD_BYTES // BLOCK))
    with pytest.raises(PartitionError, match="past the card"):
        data_end(header, BLOCK, CARD_BYTES)


def test_signature_without_partitions_is_corrupt():
    with pytest.raises(PartitionError, match="no partitions"):
        data_end(mbr(), BLOCK, CARD_BYTES)


def test_protective_mbr_without_gpt_header_is_corrupt():
    header = mbr((0xEE, 1, 0xFFFFFFFF))
    with pytest.raises(PartitionError, match="no GPT header"):
        data_end(header, BLOCK, CARD_BYTES)


def test_gpt_without_used_entries_is_corrupt():
    with pytest.raises(PartitionError, match="GPT has no partitions"):
        data_end(gpt(), BLOCK, CARD_BYTES)


def test_gpt_entries_outside_header_is_corrupt():
    with pytest.raises(PartitionError, match="outside the header"):
        data_end(gpt(100, entry_count=1_000_000), BLOCK, CARD_BYTES)

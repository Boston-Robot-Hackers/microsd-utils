#!/usr/bin/env python3
# partitions — where does the data on a card end?
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license
"""Find the byte offset where a card's last partition ends.

Backup copies only up to that point, so an image of a Pi card on a 64 GB
card holds just its few GB of partitions, and fits a slightly smaller card.

- **MBR** (Raspberry Pi OS, factory cards): four 16-byte entries at byte 446
  of sector 0, each with a start LBA and a sector count. An extended
  partition's entry covers its logical partitions, so the four primaries
  are enough.
- **GPT**: a protective MBR entry of type 0xEE, then the GPT header in
  block 1 pointing at the partition entries, each holding its last LBA.
- **No table** (no 0x55AA boot signature): returns None and the caller
  copies the whole card.

A table that points past the end of the card raises: it's corrupt, and
guessing a length would produce a broken copy.

`regions` names where on the card given byte offsets fall (an MBR partition
and its type, the partition table area, or outside any partition), so a
verify can tell differences in the FAT boot partition, which macOS changes
whenever it mounts a card, from differences anywhere else.
"""

import struct
from collections import Counter
from dataclasses import dataclass

MBR_SIGNATURE = b"\x55\xaa"
MBR_ENTRIES_OFFSET = 446
MBR_ENTRY_BYTES = 16
GPT_PROTECTIVE_TYPE = 0xEE
GPT_SIGNATURE = b"EFI PART"
# Enough for the MBR, GPT header and the standard 128 x 128-byte entry array.
HEADER_BYTES = 1024 * 1024


FAT_TYPES = {0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E}
TYPE_NAMES = {
    0x01: "FAT12",
    0x04: "FAT16",
    0x06: "FAT16",
    0x0B: "FAT32",
    0x0C: "FAT32",
    0x0E: "FAT16",
    0x07: "exFAT/NTFS",
    0x83: "Linux",
    GPT_PROTECTIVE_TYPE: "GPT",
}


class PartitionError(Exception):
    """The partition table is present but can't be trusted."""


@dataclass(frozen=True)
class Region:
    label: str
    is_fat: bool


def mbr_entries(sector0: bytes) -> list[tuple[int, int, int]]:
    """(type, start LBA, sector count) for each used MBR entry."""
    entries = []
    for index in range(4):
        offset = MBR_ENTRIES_OFFSET + index * MBR_ENTRY_BYTES
        entry = sector0[offset : offset + MBR_ENTRY_BYTES]
        part_type = entry[4]
        start_lba, sectors = struct.unpack_from("<II", entry, 8)
        if part_type and sectors:
            entries.append((part_type, start_lba, sectors))
    return entries


def gpt_end_block(header: bytes, block_bytes: int) -> int:
    """One past the highest last-LBA of any used GPT entry."""
    gpt = header[block_bytes : 2 * block_bytes]
    if gpt[:8] != GPT_SIGNATURE:
        raise PartitionError("protective MBR but no GPT header in block 1")
    entries_lba, entry_count, entry_bytes = struct.unpack_from("<QII", gpt, 72)
    start = entries_lba * block_bytes
    if start + entry_count * entry_bytes > len(header):
        raise PartitionError("GPT entry array lies outside the header read")
    last_lbas = [
        struct.unpack_from("<Q", header, start + i * entry_bytes + 40)[0]
        for i in range(entry_count)
        if any(header[start + i * entry_bytes : start + i * entry_bytes + 16])
    ]
    if not last_lbas:
        raise PartitionError("GPT has no partitions")
    return max(last_lbas) + 1


def data_end(header: bytes, block_bytes: int, card_bytes: int) -> int | None:
    """Byte offset where the last partition ends, or None if the card has no
    partition table. `header` is the first HEADER_BYTES of the card."""
    if header[510:512] != MBR_SIGNATURE:
        return None
    entries = mbr_entries(header[:512])
    if not entries:
        raise PartitionError("MBR signature but no partitions")
    if any(part_type == GPT_PROTECTIVE_TYPE for part_type, _, _ in entries):
        end_bytes = gpt_end_block(header, block_bytes) * block_bytes
    else:
        end_bytes = max(start + sectors for _, start, sectors in entries)
        end_bytes *= block_bytes
    if end_bytes > card_bytes:
        raise PartitionError(
            f"partitions end at {end_bytes} bytes, past the card's {card_bytes}"
        )
    return end_bytes


def region_of(
    entries: list[tuple[int, int, int]], offset: int, block_bytes: int
) -> Region:
    for number, (part_type, start_lba, sectors) in enumerate(entries, 1):
        if start_lba * block_bytes <= offset < (start_lba + sectors) * block_bytes:
            name = TYPE_NAMES.get(part_type, f"type 0x{part_type:02x}")
            return Region(f"partition {number} ({name})", part_type in FAT_TYPES)
    first_bytes = min((start for _, start, _ in entries), default=0) * block_bytes
    if offset < first_bytes:
        return Region("partition table", False)
    return Region("outside any partition", False)


def regions(sector0: bytes, block_bytes: int, spans: list[tuple[int, int]]) -> Counter:
    """How many differing chunks touch each region of the MBR in `sector0`.
    Each span is a chunk's first and last differing byte; the chunk counts in
    the regions of both, so a chunk straddling the table and a partition is
    named by where its bytes actually differ, not where it starts."""
    has_table = sector0[510:512] == MBR_SIGNATURE
    entries = mbr_entries(sector0) if has_table else []
    counts = Counter()
    for first, last in spans:
        # dict.fromkeys, not a set: drops a repeat but keeps first-byte order.
        touched = dict.fromkeys(
            [
                region_of(entries, first, block_bytes),
                region_of(entries, last, block_bytes),
            ]
        )
        counts.update(list(touched))
    return counts

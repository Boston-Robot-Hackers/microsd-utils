#!/usr/bin/env python3
# partitions — where does the data on a card end?
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
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
"""

import struct

MBR_SIGNATURE = b"\x55\xaa"
MBR_ENTRIES_OFFSET = 446
MBR_ENTRY_BYTES = 16
GPT_PROTECTIVE_TYPE = 0xEE
GPT_SIGNATURE = b"EFI PART"
# Enough for the MBR, GPT header and the standard 128 x 128-byte entry array.
HEADER_BYTES = 1024 * 1024


class PartitionError(Exception):
    """The partition table is present but can't be trusted."""


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

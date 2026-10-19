#!/usr/bin/env python3
# device — open the card's raw device, only after re-checking it is the card
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Raw access to the card: the only place a device node is opened.

`open_card` re-runs the reader fingerprint check on the card's identifier
immediately before `os.open`, so a reassigned identifier can never lead to
another disk being read or written.
"""

import os

from microsd_utils.reader import CardInfo, DiskutilQueries, Fingerprint, recheck


class RawDevice:
    """Positioned reads and writes on an open raw device."""

    def __init__(self, path: str, is_writable: bool):
        self.fd = os.open(path, os.O_RDWR if is_writable else os.O_RDONLY)

    def read_at(self, offset: int, length: int) -> bytes:
        return os.pread(self.fd, length, offset)

    def write_at(self, offset: int, data: bytes) -> None:
        written = os.pwrite(self.fd, data, offset)
        if written != len(data):
            raise OSError(f"short write at {offset}: {written} of {len(data)} bytes")

    def close(self) -> None:
        os.close(self.fd)

    def __enter__(self) -> "RawDevice":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def open_card(
    diskutil: DiskutilQueries,
    fingerprint: Fingerprint,
    card: CardInfo,
    is_writable: bool,
) -> RawDevice:
    recheck(diskutil, fingerprint, card)
    return RawDevice(card.raw_device, is_writable)

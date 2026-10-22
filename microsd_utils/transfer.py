#!/usr/bin/env python3
# transfer — stream a card into an image, and an image onto a card
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license
"""Backup and flash, streaming in 4 MiB chunks with SHA-256 on the fly.

Backup reads the card's partition table first and copies only up to the end
of its last partition (the whole card if there is no table). The hash of
those bytes goes in the image's sidecar.

Flash writes the image and checks the bytes written against the image's
recorded size and hash (catches a corrupt image file). `compare_card` then
reads the same range back and compares it with the image chunk by chunk,
returning, for each chunk that differs, its first and last differing byte,
so a mismatch says *where*.
`verify` uses `compare_card` on its own, read-only.

A reader that drops mid-transfer raises `CardDisconnected`, not a bare
`OSError`.

Like `passes.py`, both take plain `read_at` / `write_at` callables so they
run on temp files in tests.
"""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import BinaryIO, TypeVar

from microsd_utils.images import ImageSource, open_image
from microsd_utils.partitions import HEADER_BYTES, data_end, regions
from microsd_utils.passes import (
    CHUNK_BYTES,
    PassResult,
    Progress,
    ReadAt,
    WriteAt,
    chunks,
    raise_if_gone,
)

T = TypeVar("T")


class TransferError(Exception):
    """A backup or flash can't proceed or didn't verify."""


@dataclass
class Comparison:
    timing: PassResult
    # Per differing chunk: absolute offsets of its first and last differing byte.
    differing_spans: list[tuple[int, int]] = field(default_factory=list)


def unless_gone(action: Callable[[], T]) -> T:
    """Run a card read or write; a lost reader raises CardDisconnected."""
    try:
        return action()
    except OSError as error:
        raise_if_gone(error)
        raise


def read_exactly(read_at: ReadAt, offset: int, length: int) -> bytes:
    data = unless_gone(lambda: read_at(offset, length))
    if len(data) != length:
        raise OSError(f"short read at {offset}: {len(data)} of {length} bytes")
    return data


def copy_length(read_at: ReadAt, card_bytes: int, block_bytes: int) -> int:
    """Bytes to back up: up to the end of the last partition."""
    header = read_exactly(read_at, 0, min(HEADER_BYTES, card_bytes))
    end_bytes = data_end(header, block_bytes, card_bytes)
    return card_bytes if end_bytes is None else end_bytes


def backup_card(
    read_at: ReadAt, length_bytes: int, stream: BinaryIO, on_progress: Progress
) -> tuple[PassResult, str]:
    """Copy the first `length_bytes` of the card into `stream`. Returns the
    timing and the SHA-256 of the bytes copied. A read error raises."""
    digest = hashlib.sha256()
    start = time.monotonic()
    for offset, length in chunks(length_bytes, CHUNK_BYTES):
        data = read_exactly(read_at, offset, length)
        digest.update(data)
        stream.write(data)
        on_progress(offset + length, length_bytes)
    timing = PassResult(total_bytes=length_bytes, seconds=time.monotonic() - start)
    return timing, digest.hexdigest()


def check_fits(source: ImageSource, card_bytes: int, block_bytes: int) -> None:
    if source.data_bytes > card_bytes:
        raise TransferError(
            f"image holds {source.data_bytes:,} bytes but the card has only "
            f"{card_bytes:,}"
        )
    if source.data_bytes % block_bytes:
        raise TransferError(
            f"image size {source.data_bytes:,} is not a multiple of the card's "
            f"{block_bytes}-byte blocks"
        )


def stream_image(
    source: ImageSource,
    on_progress: Progress,
    step: Callable[[int, bytes], None],
) -> PassResult:
    """Call `step(offset, data)` for each chunk of the image, then check the
    image held its recorded size and hash."""
    digest = hashlib.sha256()
    offset = 0
    start = time.monotonic()
    with open_image(source.path) as stream:
        while data := stream.read(CHUNK_BYTES):
            step(offset, data)
            digest.update(data)
            offset += len(data)
            on_progress(offset, source.data_bytes)
    if offset != source.data_bytes or digest.hexdigest() != source.sha256:
        raise TransferError(
            f"{source.path} doesn't match its recorded size and hash; "
            "the image file may be corrupt"
        )
    return PassResult(total_bytes=offset, seconds=time.monotonic() - start)


def write_image(
    write_at: WriteAt, source: ImageSource, on_progress: Progress
) -> PassResult:
    def write_chunk(offset: int, data: bytes) -> None:
        unless_gone(lambda: write_at(offset, data))

    return stream_image(source, on_progress, write_chunk)


def difference_span(card: bytes, image: bytes) -> tuple[int, int]:
    """Indexes of the first and last differing byte of two unequal,
    equal-length chunks. Binary search on memoryview slices, so each step is
    one C-level comparison and no copy."""
    card_view, image_view = memoryview(card), memoryview(image)
    low, high = 0, len(card)
    while high - low > 1:
        mid = (low + high) // 2
        if card_view[low:mid] == image_view[low:mid]:
            low = mid
        else:
            high = mid
    first = low
    low, high = 0, len(card)
    while high - low > 1:
        mid = (low + high) // 2
        if card_view[mid:high] == image_view[mid:high]:
            high = mid
        else:
            low = mid
    return first, low


def compare_card(
    read_at: ReadAt, source: ImageSource, on_progress: Progress
) -> Comparison:
    """Read the card up to the image's length and compare it with the image,
    chunk by chunk. A read error raises; a differing chunk is recorded as the
    span of bytes that differ in it."""
    spans = []

    def compare_chunk(offset: int, data: bytes) -> None:
        card = read_exactly(read_at, offset, len(data))
        if card != data:
            first, last = difference_span(card, data)
            spans.append((offset + first, offset + last))

    timing = stream_image(source, on_progress, compare_chunk)
    return Comparison(timing, spans)


def difference_lines(
    source: ImageSource, block_bytes: int, comparison: Comparison
) -> list[str]:
    """How many chunks differ, where (by the image's own partition table),
    and a note when every difference is in a FAT partition."""
    with open_image(source.path) as stream:
        sector0 = stream.read(512)
    counts = regions(sector0, block_bytes, comparison.differing_spans)
    total_chunks = -(-source.data_bytes // CHUNK_BYTES)
    lines = [
        f"Differs: {len(comparison.differing_spans):,} of {total_chunks:,} "
        f"chunks ({CHUNK_BYTES // 1024**2} MiB each)"
    ]
    lines += [f"  {region.label}: {count:,}" for region, count in counts.items()]
    if all(region.is_fat for region in counts):
        lines.append(
            "All differences are in the FAT boot partition: macOS changes it "
            "whenever it mounts the card. The rest of the card matches."
        )
    return lines

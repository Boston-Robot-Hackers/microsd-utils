#!/usr/bin/env python3
# passes — chunked read, write and verify passes over a card
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license
"""Whole-card passes in fixed-size chunks.

`read_pass` reads every chunk, recording chunks that fail to read and,
when given an `expected` generator, chunks whose content differs. A failed
chunk is recorded and skipped, so the pass runs to the end, unless the error
says the card itself is gone: then it stops with `CardDisconnected` rather
than recording every remaining chunk as bad.

`write_pass` fills every chunk with `pattern(offset, length)`: pseudo-random
bytes seeded by the chunk's offset. Because each chunk's content depends on
where it was written, a fake-capacity card that wraps writes around to
earlier blocks fails verification on the overwritten chunks.

Both take plain `read_at` / `write_at` callables so they run unchanged on a
temp file in tests.
"""

import errno
import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

CHUNK_BYTES = 4 * 1024 * 1024
BYTES_PER_MB = 1_000_000
# Errors meaning the device went away, not that a block is bad (EIO).
GONE_ERRNOS = {errno.ENXIO, errno.ENODEV}

ReadAt = Callable[[int, int], bytes]
WriteAt = Callable[[int, bytes], None]
Progress = Callable[[int, int], None]


class CardDisconnected(Exception):
    """The card left the reader mid-pass (pulled out, or the Mac slept)."""


def raise_if_gone(error: OSError) -> None:
    if error.errno in GONE_ERRNOS:
        raise CardDisconnected(f"card disconnected: {error}") from error


@dataclass
class PassResult:
    total_bytes: int
    seconds: float
    error_offsets: list[int] = field(default_factory=list)
    mismatch_offsets: list[int] = field(default_factory=list)

    @property
    def mb_per_s(self) -> float:
        return self.total_bytes / BYTES_PER_MB / self.seconds


def chunks(size_bytes: int, chunk_bytes: int) -> Iterator[tuple[int, int]]:
    for offset in range(0, size_bytes, chunk_bytes):
        yield offset, min(chunk_bytes, size_bytes - offset)


def pattern(offset: int, length: int) -> bytes:
    return random.Random(offset).randbytes(length)


def timed_pass(
    size_bytes: int,
    chunk_bytes: int,
    on_progress: Progress,
    step: Callable[[PassResult, int, int], None],
) -> PassResult:
    """Run `step(result, offset, length)` on every chunk, timing the pass."""
    result = PassResult(total_bytes=size_bytes, seconds=0.0)
    start = time.monotonic()
    for offset, length in chunks(size_bytes, chunk_bytes):
        step(result, offset, length)
        on_progress(offset + length, size_bytes)
    result.seconds = time.monotonic() - start
    return result


def read_pass(
    read_at: ReadAt,
    size_bytes: int,
    on_progress: Progress,
    expected: Callable[[int, int], bytes] | None = None,
    chunk_bytes: int = CHUNK_BYTES,
) -> PassResult:
    def read_chunk(result: PassResult, offset: int, length: int) -> None:
        try:
            data = read_at(offset, length)
        except OSError as error:
            raise_if_gone(error)
            result.error_offsets.append(offset)
            return
        if len(data) != length:
            result.error_offsets.append(offset)
        elif expected is not None and data != expected(offset, length):
            result.mismatch_offsets.append(offset)

    return timed_pass(size_bytes, chunk_bytes, on_progress, read_chunk)


def write_pass(
    write_at: WriteAt,
    size_bytes: int,
    on_progress: Progress,
    chunk_bytes: int = CHUNK_BYTES,
) -> PassResult:
    def write_chunk(result: PassResult, offset: int, length: int) -> None:
        try:
            write_at(offset, pattern(offset, length))
        except OSError as error:
            raise_if_gone(error)
            result.error_offsets.append(offset)

    return timed_pass(size_bytes, chunk_bytes, on_progress, write_chunk)

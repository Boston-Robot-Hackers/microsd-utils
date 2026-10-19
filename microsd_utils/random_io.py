#!/usr/bin/env python3
# random_io — timed 4 KB random read and write passes
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Random 4 KB I/O, the workload a Raspberry Pi puts on its system card.

Sequential speed can look healthy on a worn card while small scattered
writes have slowed badly, so this is the most wear-sensitive signal we can
measure without SMART data. Results are compared against the SD
Association's A1/A2 application classes in `verdict.py`.

Each pass issues one 4 KB request at a time at seeded random, 4 KB-aligned
offsets until its time is up, and reports operations per second (IOPS).
The clock is injected so tests run without sleeping.
"""

import random
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from microsd_utils.passes import ReadAt, WriteAt, pattern

BLOCK_BYTES = 4096
SCRATCH_BYTES = 1024**3
RANDOM_SECONDS = 30.0
SEED = 20261018

Clock = Callable[[], float]


@dataclass
class RandomResult:
    operations: int = 0
    seconds: float = 0.0
    error_offsets: list[int] = field(default_factory=list)

    @property
    def iops(self) -> float:
        return self.operations / self.seconds


def random_offsets(region_bytes: int, seed: int = SEED) -> Iterator[int]:
    """Endless 4 KB-aligned offsets in [0, region_bytes), same for a seed."""
    rng = random.Random(seed)
    blocks = region_bytes // BLOCK_BYTES
    while True:
        yield rng.randrange(blocks) * BLOCK_BYTES


def timed_random_pass(
    region_bytes: int,
    duration_s: float,
    clock: Clock,
    operation: Callable[[int], None],
) -> RandomResult:
    """Run `operation(offset)` at random offsets until `duration_s` has passed.
    An OSError from the operation is recorded as an error at that offset."""
    result = RandomResult()
    start = clock()
    for offset in random_offsets(region_bytes):
        if clock() - start >= duration_s:
            break
        try:
            operation(offset)
        except OSError:
            result.error_offsets.append(offset)
        else:
            result.operations += 1
    result.seconds = clock() - start
    return result


def random_read_pass(
    read_at: ReadAt,
    region_bytes: int,
    duration_s: float = RANDOM_SECONDS,
    clock: Clock = time.monotonic,
) -> RandomResult:
    def read_block(offset: int) -> None:
        if len(read_at(offset, BLOCK_BYTES)) != BLOCK_BYTES:
            raise OSError(f"short read at {offset}")

    return timed_random_pass(region_bytes, duration_s, clock, read_block)


def random_write_pass(
    write_at: WriteAt,
    region_bytes: int,
    duration_s: float = RANDOM_SECONDS,
    clock: Clock = time.monotonic,
) -> RandomResult:
    # One block of pattern data reused, so generating data doesn't cost IOPS.
    block = pattern(0, BLOCK_BYTES)
    return timed_random_pass(
        region_bytes, duration_s, clock, lambda offset: write_at(offset, block)
    )

#!/usr/bin/env python3
# test_random_io — tests for the timed 4 KB random read and write passes
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

from itertools import islice

import pytest

from microsd_utils.random_io import (
    BLOCK_BYTES,
    random_offsets,
    random_read_pass,
    random_write_pass,
)

REGION = 64 * BLOCK_BYTES


class TickingClock:
    """Advances `step_s` every time it is read."""

    def __init__(self, step_s=0.001):
        self.now = 0.0
        self.step_s = step_s

    def __call__(self):
        self.now += self.step_s
        return self.now


def test_offsets_are_aligned_inside_region_and_repeatable():
    offsets = list(islice(random_offsets(REGION), 500))
    assert all(offset % BLOCK_BYTES == 0 for offset in offsets)
    assert all(0 <= offset < REGION for offset in offsets)
    assert offsets == list(islice(random_offsets(REGION), 500))
    assert len(set(offsets)) > 1


def test_read_pass_stops_on_time_and_counts_iops():
    reads = []

    def read_at(offset, length):
        reads.append(offset)
        return bytes(length)

    # Each loop reads the clock once; 1 s at 1 ms per tick is ~1000 operations.
    result = random_read_pass(read_at, REGION, duration_s=1.0, clock=TickingClock())
    assert result.operations == len(reads)
    assert 990 <= result.operations <= 1000
    assert result.iops == pytest.approx(result.operations / result.seconds)


def test_read_errors_are_counted_and_pass_continues():
    failing = next(random_offsets(REGION))

    def read_at(offset, length):
        if offset == failing:
            raise OSError("I/O error")
        return bytes(length)

    result = random_read_pass(read_at, REGION, duration_s=0.1, clock=TickingClock())
    assert failing in result.error_offsets
    assert result.operations > 0


def test_short_read_is_an_error():
    result = random_read_pass(
        lambda offset, length: b"x", REGION, duration_s=0.01, clock=TickingClock()
    )
    assert result.operations == 0
    assert result.error_offsets


def test_writes_stay_aligned_inside_region():
    writes = []
    result = random_write_pass(
        lambda offset, data: writes.append((offset, len(data))),
        REGION,
        duration_s=0.5,
        clock=TickingClock(),
    )
    assert result.operations == len(writes) > 0
    assert all(length == BLOCK_BYTES for _, length in writes)
    assert all(offset % BLOCK_BYTES == 0 and offset < REGION for offset, _ in writes)


def test_write_errors_are_counted():
    def write_at(offset, data):
        raise OSError("I/O error")

    result = random_write_pass(write_at, REGION, duration_s=0.01, clock=TickingClock())
    assert result.operations == 0
    assert len(result.error_offsets) > 0

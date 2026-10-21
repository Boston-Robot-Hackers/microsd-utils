#!/usr/bin/env python3
# test_passes — tests for whole-card read, write and verify passes
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license

import errno

import pytest

from microsd_utils.device import RawDevice
from microsd_utils.passes import (
    CardDisconnected,
    chunks,
    pattern,
    read_pass,
    write_pass,
)
from tests.fakes import FakeCard

CHUNK = 1024
SIZE = 16 * CHUNK


def no_progress(done_bytes, total_bytes):
    pass


def stress(card):
    written = write_pass(card.write_at, SIZE, no_progress, chunk_bytes=CHUNK)
    verified = read_pass(card.read_at, SIZE, no_progress, pattern, chunk_bytes=CHUNK)
    return written, verified


def test_chunks_cover_size_exactly():
    assert list(chunks(2500, 1000)) == [(0, 1000), (1000, 1000), (2000, 500)]


def test_pattern_is_deterministic_and_differs_per_offset():
    assert pattern(CHUNK, CHUNK) == pattern(CHUNK, CHUNK)
    assert pattern(0, CHUNK) != pattern(CHUNK, CHUNK)


def test_good_card_verifies_clean():
    written, verified = stress(FakeCard(SIZE))
    assert written.error_offsets == []
    assert verified.error_offsets == []
    assert verified.mismatch_offsets == []


def test_fake_capacity_card_fails_overwritten_chunks():
    written, verified = stress(FakeCard(SIZE, real_bytes=SIZE // 2))
    assert verified.mismatch_offsets == list(range(0, SIZE // 2, CHUNK))


def test_corrupt_chunk_is_reported():
    _, verified = stress(FakeCard(SIZE, corrupt_offset=3 * CHUNK))
    assert verified.mismatch_offsets == [3 * CHUNK]


def test_read_error_is_counted_and_scan_continues():
    card = FakeCard(SIZE, failing_offset=5 * CHUNK)
    calls = []
    result = read_pass(
        card.read_at, SIZE, lambda done, total: calls.append(done), chunk_bytes=CHUNK
    )
    assert result.error_offsets == [5 * CHUNK]
    assert calls[-1] == SIZE
    assert len(calls) == SIZE // CHUNK


def test_short_read_is_an_error():
    result = read_pass(
        lambda offset, length: b"x", CHUNK, no_progress, chunk_bytes=CHUNK
    )
    assert result.error_offsets == [0]


def test_write_error_is_counted_and_pass_continues():
    def write_at(offset, data):
        if offset == CHUNK:
            raise OSError("I/O error")

    result = write_pass(write_at, SIZE, no_progress, chunk_bytes=CHUNK)
    assert result.error_offsets == [CHUNK]


def test_mb_per_s():
    result = read_pass(FakeCard(SIZE).read_at, SIZE, no_progress, chunk_bytes=CHUNK)
    assert result.seconds > 0
    assert result.mb_per_s == pytest.approx(SIZE / 1e6 / result.seconds)


def test_raw_device_round_trip_on_temp_file(tmp_path):
    path = tmp_path / "card.img"
    path.write_bytes(bytes(SIZE))
    with RawDevice(str(path), is_writable=True) as device:
        written = write_pass(device.write_at, SIZE, no_progress, chunk_bytes=CHUNK)
        verified = read_pass(
            device.read_at, SIZE, no_progress, pattern, chunk_bytes=CHUNK
        )
    assert written.error_offsets == []
    assert verified.mismatch_offsets == []


def failing_after(first_bad_offset, errno_code):
    """read_at / write_at that fail with `errno_code` from an offset on."""

    def access(offset, payload):
        if offset >= first_bad_offset:
            raise OSError(errno_code, "simulated")
        return bytes(payload) if isinstance(payload, int) else None

    return access


@pytest.mark.parametrize("errno_code", [errno.ENXIO, errno.ENODEV])
def test_lost_card_stops_read_and_write_passes(errno_code):
    access = failing_after(4 * CHUNK, errno_code)
    with pytest.raises(CardDisconnected, match="card disconnected"):
        read_pass(access, SIZE, no_progress, chunk_bytes=CHUNK)
    with pytest.raises(CardDisconnected):
        write_pass(access, SIZE, no_progress, chunk_bytes=CHUNK)


def test_bad_block_errno_is_still_counted():
    access = failing_after(14 * CHUNK, errno.EIO)
    result = read_pass(access, SIZE, no_progress, chunk_bytes=CHUNK)
    assert result.error_offsets == [14 * CHUNK, 15 * CHUNK]

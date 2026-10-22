#!/usr/bin/env python3
# test_transfer — tests for backing up a card and flashing an image
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license

import errno
import gzip
import hashlib
import struct

import pytest

from microsd_utils.images import ImageSource, ImageStore
from microsd_utils.passes import CHUNK_BYTES, CardDisconnected
from microsd_utils.transfer import (
    TransferError,
    backup_card,
    check_fits,
    compare_card,
    copy_length,
    difference_lines,
    difference_span,
    read_exactly,
    write_image,
)
from tests.fakes import FakeCard, partitioned_card

BLOCK = 512
CARD_BYTES = 4 * CHUNK_BYTES


def no_progress(done_bytes, total_bytes):
    pass


def pi_card() -> FakeCard:
    return partitioned_card(CARD_BYTES, 3 * CHUNK_BYTES)


def image_of(tmp_path, data: bytes) -> ImageSource:
    path = tmp_path / "pi.img.gz"
    path.write_bytes(gzip.compress(data))
    return ImageSource(path, len(data), hashlib.sha256(data).hexdigest())


def test_copy_length_stops_at_last_partition():
    assert copy_length(pi_card().read_at, CARD_BYTES, BLOCK) == 3 * CHUNK_BYTES


def test_copy_length_whole_card_without_table():
    assert copy_length(FakeCard(CARD_BYTES).read_at, CARD_BYTES, BLOCK) == CARD_BYTES


def test_backup_copies_exactly_the_partitions(tmp_path):
    card = pi_card()
    store = ImageStore(tmp_path / "images")
    length = copy_length(card.read_at, CARD_BYTES, BLOCK)
    with store.create("pi") as stream:
        timing, sha256 = backup_card(card.read_at, length, stream, no_progress)
    expected = bytes(card.store[:length])
    assert gzip.decompress(store.image_path("pi").read_bytes()) == expected
    assert sha256 == hashlib.sha256(expected).hexdigest()
    assert timing.total_bytes == length


def test_backup_read_error_leaves_no_image(tmp_path):
    card = FakeCard(CARD_BYTES, failing_offset=CHUNK_BYTES)
    store = ImageStore(tmp_path / "images")
    with pytest.raises(OSError), store.create("pi") as stream:
        backup_card(card.read_at, CARD_BYTES, stream, no_progress)
    assert list(store.directory.iterdir()) == []


MIB = 1024**2


def pi_layout_image(fat_start_bytes: int = CHUNK_BYTES) -> bytes:
    """Three chunks like a Pi image: partition table, FAT32 boot from
    `fat_start_bytes` to chunk 2, Linux root in chunk 2."""
    data = bytearray(bytes(range(251)) * (3 * CHUNK_BYTES // 251 + 1))[
        : 3 * CHUNK_BYTES
    ]
    sector0 = bytearray(512)
    layout = [
        (0x0C, fat_start_bytes, 2 * CHUNK_BYTES - fat_start_bytes),
        (0x83, 2 * CHUNK_BYTES, CHUNK_BYTES),
    ]
    for index, (part_type, start_bytes, size_bytes) in enumerate(layout):
        entry = 446 + index * 16
        sector0[entry + 4] = part_type
        struct.pack_into(
            "<II", sector0, entry + 8, start_bytes // BLOCK, size_bytes // BLOCK
        )
    sector0[510:512] = b"\x55\xaa"
    data[:512] = sector0
    return bytes(data)


@pytest.mark.parametrize(
    "changed, span",
    [([5], (5, 5)), ([0, MIB - 1], (0, MIB - 1)), ([3, 9, 70_000], (3, 70_000))],
)
def test_difference_span_finds_first_and_last_byte(changed, span):
    image = bytes(range(256)) * (MIB // 256)
    card = bytearray(image)
    for index in changed:
        card[index] ^= 0xFF
    assert difference_span(bytes(card), image) == span


def test_flash_and_compare_round_trip(tmp_path):
    data = bytes(pi_card().store[: 3 * CHUNK_BYTES])
    source = image_of(tmp_path, data)
    target = FakeCard(CARD_BYTES)
    check_fits(source, CARD_BYTES, BLOCK)
    written = write_image(target.write_at, source, no_progress)
    comparison = compare_card(target.read_at, source, no_progress)
    assert bytes(target.store[: len(data)]) == data
    assert comparison.differing_spans == []
    assert written.total_bytes == comparison.timing.total_bytes == len(data)


@pytest.mark.parametrize("suffix", [".img", ".img.gz"])
def test_compare_finds_exactly_the_changed_chunks(tmp_path, suffix):
    data = pi_layout_image()
    path = tmp_path / f"pi{suffix}"
    path.write_bytes(gzip.compress(data) if suffix == ".img.gz" else data)
    source = ImageSource(path, len(data), hashlib.sha256(data).hexdigest())
    card = FakeCard(CARD_BYTES)
    card.store[: len(data)] = data
    card.store[CHUNK_BYTES + 7] ^= 0xFF
    card.store[2 * CHUNK_BYTES] ^= 0xFF
    comparison = compare_card(card.read_at, source, no_progress)
    assert comparison.differing_spans == [
        (CHUNK_BYTES + 7, CHUNK_BYTES + 7),
        (2 * CHUNK_BYTES, 2 * CHUNK_BYTES),
    ]


@pytest.mark.parametrize(
    "changed_chunks, lines",
    [
        (
            [1],
            [
                "Differs: 1 of 3 chunks (4 MiB each)",
                "  partition 1 (FAT32): 1",
                "All differences are in the FAT boot partition: macOS changes it "
                "whenever it mounts the card. The rest of the card matches.",
            ],
        ),
        (
            [0, 2],
            [
                "Differs: 2 of 3 chunks (4 MiB each)",
                "  partition table: 1",
                "  partition 2 (Linux): 1",
            ],
        ),
    ],
)
def test_difference_lines_name_partitions(tmp_path, changed_chunks, lines):
    data = pi_layout_image()
    source = image_of(tmp_path, data)
    card = FakeCard(CARD_BYTES)
    card.store[: len(data)] = data
    for chunk in changed_chunks:
        card.store[chunk * CHUNK_BYTES + 600] ^= 0xFF
    comparison = compare_card(card.read_at, source, no_progress)
    assert difference_lines(source, BLOCK, comparison) == lines


@pytest.mark.parametrize(
    "changed_bytes, lines",
    [
        # Regression: dome-2-master's FAT starts at 1 MiB, inside chunk 0, so a
        # mount's FAT changes there were reported as "partition table".
        (
            [2 * MIB, CHUNK_BYTES + 9],
            [
                "Differs: 2 of 3 chunks (4 MiB each)",
                "  partition 1 (FAT32): 2",
                "All differences are in the FAT boot partition: macOS changes it "
                "whenever it mounts the card. The rest of the card matches.",
            ],
        ),
        (
            [600, 2 * MIB],
            [
                "Differs: 1 of 3 chunks (4 MiB each)",
                "  partition table: 1",
                "  partition 1 (FAT32): 1",
            ],
        ),
    ],
)
def test_chunk_straddling_table_and_fat_is_named_by_its_bytes(
    tmp_path, changed_bytes, lines
):
    data = pi_layout_image(fat_start_bytes=MIB)
    source = image_of(tmp_path, data)
    card = FakeCard(CARD_BYTES)
    card.store[: len(data)] = data
    for index in changed_bytes:
        card.store[index] ^= 0xFF
    comparison = compare_card(card.read_at, source, no_progress)
    assert difference_lines(source, BLOCK, comparison) == lines


@pytest.mark.parametrize("errno_code", [errno.ENXIO, errno.ENODEV])
def test_lost_reader_mid_transfer_is_card_disconnected(tmp_path, errno_code):
    def gone(*args):
        raise OSError(errno_code, "Device not configured")

    with pytest.raises(CardDisconnected):
        read_exactly(gone, 0, BLOCK)
    source = image_of(tmp_path, bytes(CHUNK_BYTES))
    with pytest.raises(CardDisconnected):
        write_image(gone, source, no_progress)


def test_bad_block_mid_transfer_stays_a_plain_error():
    def bad_block(offset, length):
        raise OSError(errno.EIO, "Input/output error")

    with pytest.raises(OSError) as caught:
        read_exactly(bad_block, 0, BLOCK)
    assert not isinstance(caught.value, CardDisconnected)


def test_too_small_card_refused(tmp_path):
    source = image_of(tmp_path, bytes(CARD_BYTES))
    with pytest.raises(TransferError, match="has only"):
        check_fits(source, CARD_BYTES - BLOCK, BLOCK)


def test_unaligned_image_refused(tmp_path):
    source = image_of(tmp_path, bytes(BLOCK + 1))
    with pytest.raises(TransferError, match="multiple"):
        check_fits(source, CARD_BYTES, BLOCK)


def test_corrupting_card_shows_in_comparison(tmp_path):
    source = image_of(tmp_path, bytes(range(256)) * (2 * CHUNK_BYTES // 256))
    target = FakeCard(CARD_BYTES, corrupt_offset=CHUNK_BYTES)
    write_image(target.write_at, source, no_progress)
    comparison = compare_card(target.read_at, source, no_progress)
    assert comparison.differing_spans == [(CHUNK_BYTES, CHUNK_BYTES)]


def test_image_not_matching_its_record_is_reported(tmp_path):
    good = image_of(tmp_path, bytes(CHUNK_BYTES))
    wrong_hash = ImageSource(good.path, good.data_bytes, "0" * 64)
    with pytest.raises(TransferError, match="may be corrupt"):
        write_image(FakeCard(CARD_BYTES).write_at, wrong_hash, no_progress)

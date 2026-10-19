#!/usr/bin/env python3
# test_transfer — tests for backing up a card and flashing an image
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import gzip
import hashlib

import pytest

from microsd_utils.images import ImageSource, ImageStore
from microsd_utils.passes import CHUNK_BYTES
from microsd_utils.transfer import (
    TransferError,
    backup_card,
    check_fits,
    copy_length,
    verify_card,
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


def test_flash_and_verify_round_trip(tmp_path):
    data = bytes(pi_card().store[: 3 * CHUNK_BYTES])
    source = image_of(tmp_path, data)
    target = FakeCard(CARD_BYTES)
    check_fits(source, CARD_BYTES, BLOCK)
    written = write_image(target.write_at, source, no_progress)
    verified = verify_card(target.read_at, source, no_progress)
    assert bytes(target.store[: len(data)]) == data
    assert written.total_bytes == verified.total_bytes == len(data)


def test_too_small_card_refused(tmp_path):
    source = image_of(tmp_path, bytes(CARD_BYTES))
    with pytest.raises(TransferError, match="has only"):
        check_fits(source, CARD_BYTES - BLOCK, BLOCK)


def test_unaligned_image_refused(tmp_path):
    source = image_of(tmp_path, bytes(BLOCK + 1))
    with pytest.raises(TransferError, match="multiple"):
        check_fits(source, CARD_BYTES, BLOCK)


def test_corrupting_card_fails_verification(tmp_path):
    source = image_of(tmp_path, bytes(range(256)) * (2 * CHUNK_BYTES // 256))
    target = FakeCard(CARD_BYTES, corrupt_offset=CHUNK_BYTES)
    write_image(target.write_at, source, no_progress)
    with pytest.raises(TransferError, match="verification failed"):
        verify_card(target.read_at, source, no_progress)


def test_image_not_matching_its_record_is_reported(tmp_path):
    good = image_of(tmp_path, bytes(CHUNK_BYTES))
    wrong_hash = ImageSource(good.path, good.data_bytes, "0" * 64)
    with pytest.raises(TransferError, match="may be corrupt"):
        write_image(FakeCard(CARD_BYTES).write_at, wrong_hash, no_progress)

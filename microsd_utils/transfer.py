#!/usr/bin/env python3
# transfer — stream a card into an image, and an image onto a card
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Backup and flash, streaming in 4 MiB chunks with SHA-256 on the fly.

Backup reads the card's partition table first and copies only up to the end
of its last partition (the whole card if there is no table). The hash of
those bytes goes in the image's sidecar.

Flash writes the image, then reads the same range back from the card and
compares hashes. Two hashes are checked: the bytes written must match the
image's recorded hash (catches a corrupt image file), and the bytes read
back must match too (catches a card that didn't store what it was given).

Like `passes.py`, both take plain `read_at` / `write_at` callables so they
run on temp files in tests.
"""

import hashlib
import time
from typing import BinaryIO

from microsd_utils.images import ImageSource, open_image
from microsd_utils.partitions import HEADER_BYTES, data_end
from microsd_utils.passes import (
    CHUNK_BYTES,
    PassResult,
    Progress,
    ReadAt,
    WriteAt,
    chunks,
)


class TransferError(Exception):
    """A backup or flash can't proceed or didn't verify."""


def read_exactly(read_at: ReadAt, offset: int, length: int) -> bytes:
    data = read_at(offset, length)
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


def write_image(
    write_at: WriteAt, source: ImageSource, on_progress: Progress
) -> PassResult:
    digest = hashlib.sha256()
    offset = 0
    start = time.monotonic()
    with open_image(source.path) as stream:
        while data := stream.read(CHUNK_BYTES):
            write_at(offset, data)
            digest.update(data)
            offset += len(data)
            on_progress(offset, source.data_bytes)
    if offset != source.data_bytes or digest.hexdigest() != source.sha256:
        raise TransferError(
            f"{source.path} doesn't match its recorded size and hash; "
            "the image file may be corrupt"
        )
    return PassResult(total_bytes=offset, seconds=time.monotonic() - start)


def verify_card(
    read_at: ReadAt, source: ImageSource, on_progress: Progress
) -> PassResult:
    digest = hashlib.sha256()
    start = time.monotonic()
    for offset, length in chunks(source.data_bytes, CHUNK_BYTES):
        digest.update(read_exactly(read_at, offset, length))
        on_progress(offset + length, source.data_bytes)
    if digest.hexdigest() != source.sha256:
        raise TransferError("verification failed: the card doesn't hold the image")
    return PassResult(total_bytes=source.data_bytes, seconds=time.monotonic() - start)

#!/usr/bin/env python3
# swap — wait for the card in the reader to be removed or inserted
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""Waiting for the user to swap cards in the one designated reader.

`copy` needs the master card out before it will accept a new card, so the
master can never be picked as the flash target. Each poll runs the normal
reader discovery: a card (with its identifier), or no card. Anything else
discovery refuses, such as two matching readers, propagates.

Clock and sleep are injected so tests replay scripted poll sequences.
"""

import time
from collections.abc import Callable

from microsd_utils.reader import (
    CardInfo,
    DiskutilQueries,
    Fingerprint,
    NoCardError,
    discover,
)

POLL_SECONDS = 1.0
SWAP_TIMEOUT_SECONDS = 300.0

Poll = Callable[[], CardInfo | None]


class SwapError(Exception):
    """The user didn't swap cards in time."""


def card_poll(diskutil: DiskutilQueries, fingerprint: Fingerprint) -> Poll:
    def poll() -> CardInfo | None:
        try:
            return discover(diskutil, fingerprint)
        except NoCardError:
            return None

    return poll


def wait_until(
    poll: Poll,
    is_done: Callable[[CardInfo | None], bool],
    waiting_for: str,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> CardInfo | None:
    deadline = clock() + SWAP_TIMEOUT_SECONDS
    while True:
        card = poll()
        if is_done(card):
            return card
        if clock() >= deadline:
            raise SwapError(
                f"gave up after {SWAP_TIMEOUT_SECONDS:.0f} s waiting for {waiting_for}"
            )
        sleep(POLL_SECONDS)


def wait_for_removal(poll: Poll, **timing) -> None:
    wait_until(poll, lambda card: card is None, "the card to be removed", **timing)


def wait_for_insert(poll: Poll, **timing) -> CardInfo:
    return wait_until(
        poll, lambda card: card is not None, "a card to be inserted", **timing
    )

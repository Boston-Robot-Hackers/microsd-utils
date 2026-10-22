#!/usr/bin/env python3
# swap — wait for the card in the reader to be removed or inserted
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license
"""Waiting for the user to swap cards in the one designated reader.

`copy` needs the master card out before it will accept a new card, so the
master can never be picked as the flash target. Each poll runs the normal
reader discovery: a card (with its identifier), or no card. Anything else
discovery refuses, such as two matching readers, propagates.

There is no timeout: the backup before the swap takes a quarter of an hour,
so the user may well not be there when it ends. The wait lasts until the
card is swapped or the user presses Ctrl-C.

Sleep is injected so tests replay scripted poll sequences.
"""

from collections.abc import Callable

from microsd_utils.reader import (
    CardInfo,
    DiskutilQueries,
    Fingerprint,
    NoCardError,
    discover,
)

POLL_SECONDS = 1.0

Poll = Callable[[], CardInfo | None]
Sleep = Callable[[float], None]


def card_poll(diskutil: DiskutilQueries, fingerprint: Fingerprint) -> Poll:
    def poll() -> CardInfo | None:
        try:
            return discover(diskutil, fingerprint)
        except NoCardError:
            return None

    return poll


def wait_until(
    poll: Poll, is_done: Callable[[CardInfo | None], bool], sleep: Sleep
) -> CardInfo | None:
    while not is_done(card := poll()):
        sleep(POLL_SECONDS)
    return card


def wait_for_removal(poll: Poll, sleep: Sleep) -> None:
    wait_until(poll, lambda card: card is None, sleep)


def wait_for_insert(poll: Poll, sleep: Sleep) -> CardInfo:
    return wait_until(poll, lambda card: card is not None, sleep)

#!/usr/bin/env python3
# test_swap — tests for waiting on card removal and insertion
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import pytest

from microsd_utils.reader import (
    CardInfo,
    NoCardError,
    ReaderError,
    load_fingerprint,
    parse_card,
)
from microsd_utils.swap import (
    POLL_SECONDS,
    SWAP_TIMEOUT_SECONDS,
    SwapError,
    card_poll,
    wait_for_insert,
    wait_for_removal,
)
from tests.fakes import FakeDiskutil, load_plist

MASTER = CardInfo("disk4", 62_599_987_200, 512, "1081CS0", ())
NEW = CardInfo("disk5", 31_914_983_424, 512, "1081CS0", ())


class Script:
    """Replays poll results; time advances one poll interval per sleep."""

    def __init__(self, *results):
        self.results = list(results)
        self.now = 0.0
        self.polls = 0

    def poll(self):
        self.polls += 1
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return result

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    @property
    def timing(self):
        return {"clock": self.clock, "sleep": self.sleep}


def test_normal_swap():
    script = Script(MASTER, MASTER, None, None, NEW)
    wait_for_removal(script.poll, **script.timing)
    assert wait_for_insert(script.poll, **script.timing) is NEW


def test_card_never_removed_times_out():
    script = Script(MASTER)
    with pytest.raises(SwapError, match="removed"):
        wait_for_removal(script.poll, **script.timing)
    assert script.now >= SWAP_TIMEOUT_SECONDS
    assert script.polls == SWAP_TIMEOUT_SECONDS / POLL_SECONDS + 1


def test_no_new_card_times_out():
    script = Script(None)
    with pytest.raises(SwapError, match="inserted"):
        wait_for_insert(script.poll, **script.timing)


def test_two_readers_propagate():
    script = Script(ReaderError("Several disks match the reader fingerprint"))
    with pytest.raises(ReaderError, match="Several"):
        wait_for_insert(script.poll, **script.timing)


def test_card_poll_maps_no_card_to_none():
    card_list = load_plist("norelsys-card-list.plist")
    info = load_plist("norelsys-card-info.plist")
    poll = card_poll(FakeDiskutil(card_list, {"disk4": info}), load_fingerprint())
    assert poll() == parse_card(info, card_list)
    card_list["WholeDisks"] = []
    assert poll() is None


def test_no_card_error_is_a_reader_error():
    assert issubclass(NoCardError, ReaderError)

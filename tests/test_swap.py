#!/usr/bin/env python3
# test_swap — tests for waiting on card removal and insertion
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-22
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

    def sleep(self, seconds):
        self.now += seconds


# Two hours of polls: far past the old 300 s timeout.
LONG_WAIT_POLLS = int(2 * 3600 / POLL_SECONDS)


def test_normal_swap():
    script = Script(MASTER, MASTER, None, None, NEW)
    wait_for_removal(script.poll, script.sleep)
    assert wait_for_insert(script.poll, script.sleep) is NEW


def test_waits_for_removal_with_no_timeout():
    script = Script(*[MASTER] * LONG_WAIT_POLLS, None)
    wait_for_removal(script.poll, script.sleep)
    assert script.polls == LONG_WAIT_POLLS + 1
    assert script.now == LONG_WAIT_POLLS * POLL_SECONDS


def test_waits_for_insert_with_no_timeout():
    script = Script(*[None] * LONG_WAIT_POLLS, NEW)
    assert wait_for_insert(script.poll, script.sleep) is NEW
    assert script.polls == LONG_WAIT_POLLS + 1


def test_two_readers_propagate():
    script = Script(ReaderError("Several disks match the reader fingerprint"))
    with pytest.raises(ReaderError, match="Several"):
        wait_for_insert(script.poll, script.sleep)


def test_card_poll_maps_no_card_to_none():
    card_list = load_plist("norelsys-card-list.plist")
    info = load_plist("norelsys-card-info.plist")
    poll = card_poll(FakeDiskutil(card_list, {"disk4": info}), load_fingerprint())
    assert poll() == parse_card(info, card_list)
    card_list["WholeDisks"] = []
    assert poll() is None


def test_no_card_error_is_a_reader_error():
    assert issubclass(NoCardError, ReaderError)

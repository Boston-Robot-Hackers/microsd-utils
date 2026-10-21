#!/usr/bin/env python3
# test_session — tests for the shared session helpers
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-21
# Updated: 2026-10-21
# Open Source Under MIT license

import pytest

from microsd_utils.session import human_size


@pytest.mark.parametrize(
    "size_bytes, text",
    [
        (32_000_000, "32 MB"),
        (999_999_999, "1000 MB"),
        (1_000_000_000, "1.0 GB"),
        (62_599_987_200, "62.6 GB"),
    ],
)
def test_human_size_uses_mb_below_one_gb(size_bytes, text):
    assert human_size(size_bytes) == text

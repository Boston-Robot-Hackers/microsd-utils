#!/usr/bin/env python3
# test_verdict — tests for factory-fresh signals and the verdict
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import pytest

from microsd_utils.freshness import Freshness, assess
from microsd_utils.passes import PassResult
from microsd_utils.random_io import RandomResult
from microsd_utils.reader import CardInfo, Partition
from microsd_utils.verdict import (
    Grade,
    Measurements,
    decide,
    random_tier,
    sequential_grade,
)

CARD_BYTES = 64_000_000_000
FRESH = Freshness(True, "factory layout, no files")
USED = Freshness(False, "2 partitions, factory has 1")


def card_with(*partitions: tuple[str, int]) -> CardInfo:
    return CardInfo(
        identifier="disk4",
        size_bytes=CARD_BYTES,
        block_size_bytes=512,
        media_name="1081CS0",
        partitions=tuple(
            Partition(f"disk4s{i + 1}", content, size, "/Volumes/X")
            for i, (content, size) in enumerate(partitions)
        ),
    )


def at_speed(mb_per_s: float, **offsets) -> PassResult:
    return PassResult(total_bytes=int(mb_per_s * 1e6), seconds=1.0, **offsets)


FACTORY_EXFAT = card_with(("Windows_NTFS", CARD_BYTES - 4_194_304))


def test_factory_card_is_fresh():
    assert assess(FACTORY_EXFAT, [".fseventsd", ".Spotlight-V100", "._x"]).is_fresh


def test_pi_card_is_not_fresh():
    pi_card = card_with(("Windows_FAT_32", 536_870_912), ("Linux", 62_062_050_816))
    assert assess(pi_card, []).reason == "2 partitions, factory has 1"


def test_card_with_user_files_is_not_fresh():
    fresh = assess(FACTORY_EXFAT, ["DCIM", ".fseventsd"])
    assert not fresh.is_fresh
    assert fresh.reason == "1 files or folders on the card"


def test_unmounted_card_is_not_fresh():
    assert not assess(FACTORY_EXFAT, None).is_fresh


def test_small_partition_is_not_fresh():
    assert not assess(card_with(("Windows_NTFS", CARD_BYTES // 2)), []).is_fresh


def test_non_fat_partition_is_not_fresh():
    assert not assess(card_with(("Apple_HFS", CARD_BYTES)), []).is_fresh


def measured(read_mb_s=72, write_mb_s=54, read_iops=5000, write_iops=2500, **errs):
    return Measurements(
        read=at_speed(read_mb_s, **errs.get("read", {})),
        write=None
        if write_mb_s is None
        else at_speed(write_mb_s, **errs.get("write", {})),
        random_read=RandomResult(round(read_iops), 1.0, errs.get("random_read", [])),
        random_write=None
        if write_iops is None
        else RandomResult(round(write_iops), 1.0, errs.get("random_write", [])),
    )


def test_excellent_card():
    verdict = decide(measured(), USED)
    assert verdict.grade is Grade.EXCELLENT
    assert verdict.reasons == [
        "sequential: EXCELLENT (write 54.0 MB/s, read 72.0 MB/s)",
        "random: EXCELLENT (A2 level)",
        f"not brand new: {USED.reason}",
    ]
    assert not verdict.is_read_only
    assert not verdict.is_brand_new


def test_brand_new_is_a_note_not_a_grade():
    verdict = decide(measured(), FRESH)
    assert verdict.grade is Grade.EXCELLENT
    assert verdict.is_brand_new
    assert FRESH.reason in verdict.reasons


@pytest.mark.parametrize(
    "write_mb_s, read_mb_s, grade",
    [
        (30, 60, Grade.EXCELLENT),
        (29.9, 60, Grade.GOOD),
        (30, 59.9, Grade.GOOD),
        (20, 40, Grade.GOOD),
        (19.9, 40, Grade.FAIR),
        (20, 39.9, Grade.FAIR),
        (10, 20, Grade.FAIR),
        (9.9, 20, Grade.RETIRE),
        (10, 19.9, Grade.RETIRE),
    ],
)
def test_sequential_tiers(write_mb_s, read_mb_s, grade):
    assert sequential_grade(at_speed(read_mb_s), at_speed(write_mb_s)) is grade


@pytest.mark.parametrize(
    "read_iops, write_iops, grade, a_class",
    [
        (4000, 2000, Grade.EXCELLENT, "A2"),
        (3999, 2000, Grade.GOOD, "A1"),
        (4000, 1999, Grade.GOOD, "A1"),
        (1500, 500, Grade.GOOD, "A1"),
        (1499, 500, Grade.FAIR, "below A1"),
        (1500, 499, Grade.FAIR, "below A1"),
        (0, 0, Grade.FAIR, "below A1"),
    ],
)
def test_random_tiers(read_iops, write_iops, grade, a_class):
    tier = random_tier(RandomResult(read_iops, 1.0), RandomResult(write_iops, 1.0))
    assert (tier.grade, tier.a_class) == (grade, a_class)


def test_verdict_is_worst_of_sequential_and_random():
    assert decide(measured(write_mb_s=25), USED).grade is Grade.GOOD
    assert decide(measured(write_iops=600), USED).grade is Grade.GOOD
    assert decide(measured(write_mb_s=25, write_iops=100), USED).grade is Grade.FAIR


def test_slow_random_io_caps_at_fair_and_never_retires():
    verdict = decide(measured(read_iops=10, write_iops=1), USED)
    assert verdict.grade is Grade.FAIR
    assert "random: FAIR (below A1 level)" in verdict.reasons


def test_read_only_grades_on_reads_alone():
    verdict = decide(measured(write_mb_s=None, write_iops=None), USED)
    assert verdict.grade is Grade.EXCELLENT
    assert verdict.is_read_only
    assert verdict.reasons[0] == "sequential: EXCELLENT (read 72.0 MB/s)"


def test_too_slow_retires():
    verdict = decide(measured(write_mb_s=5), FRESH)
    assert verdict.grade is Grade.RETIRE
    assert verdict.reasons == ["too slow: write 5.0 MB/s, read 72.0 MB/s"]
    assert not verdict.is_brand_new


@pytest.mark.parametrize(
    "errs, reason",
    [
        ({"read": {"error_offsets": [0]}}, "1 chunks failed to read"),
        ({"read": {"mismatch_offsets": [0, 4]}}, "2 chunks read back wrong"),
        ({"write": {"error_offsets": [8]}}, "1 chunks failed to write"),
        ({"random_read": [4096]}, "1 random 4 KB reads failed"),
        ({"random_write": [4096, 8192]}, "2 random 4 KB writes failed"),
    ],
)
def test_each_error_retires(errs, reason):
    verdict = decide(measured(**errs), FRESH)
    assert verdict.grade is Grade.RETIRE
    assert len(verdict.reasons) == 1
    assert verdict.reasons[0].startswith(reason)

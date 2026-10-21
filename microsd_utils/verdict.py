#!/usr/bin/env python3
# verdict — grade a card from its measurements: excellent / good / fair / retire
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license
"""The verdict is an estimate: cards report no wear data, so it rests on
errors, speed and the factory-fresh signal.

Any read, write or verify error retires the card. Otherwise the card gets
two grades, and the verdict is the worse of them:

- *sequential*: tiers anchored on the SD speed classes (U1 = 10 MB/s and
  U3/V30 = 30 MB/s minimum write). Below the FAIR tier means RETIRE.
- *random 4 KB*: tiers anchored on the A1/A2 application classes. Slow
  random I/O caps the grade at FAIR but never retires a card on its own,
  since many older cards predate A1. A card within `READER_MARGIN` of a
  class's IOPS counts as meeting it, since a USB reader measures a little
  low.

In read-only mode only the read figures exist, and the verdict says so.
Freshness doesn't change the grade; it adds a *looks brand new* note.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple

from microsd_utils.freshness import Freshness
from microsd_utils.passes import PassResult
from microsd_utils.random_io import RandomResult


class Grade(IntEnum):
    RETIRE = 0
    FAIR = 1
    GOOD = 2
    EXCELLENT = 3


class SequentialTier(NamedTuple):
    grade: Grade
    min_write_mb_s: float
    min_read_mb_s: float


class RandomTier(NamedTuple):
    grade: Grade
    a_class: str
    min_read_iops: float
    min_write_iops: float


# Best first. Below the last sequential tier is RETIRE. The last random tier
# matches everything: slow random I/O caps the grade at FAIR, never retires.
SEQUENTIAL_TIERS = [
    SequentialTier(Grade.EXCELLENT, 30.0, 60.0),
    SequentialTier(Grade.GOOD, 20.0, 40.0),
    SequentialTier(Grade.FAIR, 10.0, 20.0),
]
RANDOM_TIERS = [
    RandomTier(Grade.EXCELLENT, "A2", 4000, 2000),
    RandomTier(Grade.GOOD, "A1", 1500, 500),
    RandomTier(Grade.FAIR, "below A1", 0, 0),
]
# A1/A2 ratings come from an SD host; through a USB reader, one request at
# a time, an A1 card measured ~1,500 ±2%. Lean toward the better grade.
READER_MARGIN = 0.95


@dataclass(frozen=True)
class Measurements:
    read: PassResult
    write: PassResult | None
    random_read: RandomResult
    random_write: RandomResult | None

    @property
    def is_read_only(self) -> bool:
        return self.write is None


@dataclass(frozen=True)
class Verdict:
    grade: Grade
    reasons: list[str]
    is_read_only: bool
    is_brand_new: bool


def errors(measured: Measurements) -> list[str]:
    write = measured.write
    random_write = measured.random_write
    counts = {
        "chunks failed to read": len(measured.read.error_offsets),
        "chunks read back wrong (bad blocks or fake capacity)": len(
            measured.read.mismatch_offsets
        ),
        "chunks failed to write": len(write.error_offsets) if write else 0,
        "random 4 KB reads failed": len(measured.random_read.error_offsets),
        "random 4 KB writes failed": (
            len(random_write.error_offsets) if random_write else 0
        ),
    }
    return [f"{count} {what}" for what, count in counts.items() if count]


def sequential_grade(read: PassResult, write: PassResult | None) -> Grade:
    for tier in SEQUENTIAL_TIERS:
        is_write_ok = write is None or write.mb_per_s >= tier.min_write_mb_s
        if read.mb_per_s >= tier.min_read_mb_s and is_write_ok:
            return tier.grade
    return Grade.RETIRE


def meets(iops: float, min_iops: float) -> bool:
    return iops >= READER_MARGIN * min_iops


def random_tier(read: RandomResult, write: RandomResult | None) -> RandomTier:
    return next(
        tier
        for tier in RANDOM_TIERS
        if meets(read.iops, tier.min_read_iops)
        and (write is None or meets(write.iops, tier.min_write_iops))
    )


def read_a_class(iops: float) -> str:
    return next(t.a_class for t in RANDOM_TIERS if meets(iops, t.min_read_iops))


def write_a_class(iops: float) -> str:
    return next(t.a_class for t in RANDOM_TIERS if meets(iops, t.min_write_iops))


def sequential_reason(measured: Measurements, grade: Grade) -> str:
    speeds = f"read {measured.read.mb_per_s:.1f} MB/s"
    if measured.write is not None:
        speeds = f"write {measured.write.mb_per_s:.1f} MB/s, {speeds}"
    if grade is Grade.RETIRE:
        return f"too slow: {speeds}"
    return f"sequential: {grade.name} ({speeds})"


def decide(measured: Measurements, fresh: Freshness) -> Verdict:
    found = errors(measured)
    sequential = sequential_grade(measured.read, measured.write)
    if found or sequential is Grade.RETIRE:
        if sequential is Grade.RETIRE:
            found.append(sequential_reason(measured, sequential))
        return Verdict(Grade.RETIRE, found, measured.is_read_only, False)
    random = random_tier(measured.random_read, measured.random_write)
    reasons = [
        sequential_reason(measured, sequential),
        f"random: {random.grade.name} ({random.a_class} level)",
        fresh.reason if fresh.is_fresh else f"not brand new: {fresh.reason}",
    ]
    return Verdict(
        min(sequential, random.grade), reasons, measured.is_read_only, fresh.is_fresh
    )

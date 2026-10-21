#!/usr/bin/env python3
# check — the `microsd check` command: find the card, test it, give a verdict
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-20
# Open Source Under MIT license
"""Orchestrates a health check of the card in the designated reader.

Read-only mode runs timed random 4 KB reads, then reads every block.
Destructive mode asks twice for confirmation, unmounts the card, runs random
4 KB writes (in a scratch region) and reads, then writes a position-dependent
pattern to every block and reads it all back. The factory-fresh signal is
taken before any write, from the card as it was inserted.

Both modes show the card's ID. Destructive mode identifies the card before
the wipe (asking for its label ID if untagged), and afterwards formats it
FAT32 named after the ID and writes the manifest back with the grade. If the
passes fail, the failure still goes into the registry.

Run without root, it finds the card and prints the plan (metadata needs no
root), explains why a password is coming, then re-runs itself under sudo.

All side effects come in through `session.Env`, so the whole flow is tested
with fakes.
"""

from collections.abc import Callable

from microsd_utils.freshness import assess
from microsd_utils.identity import (
    ASK_HINT,
    UNTAGGED_HINT,
    event,
    id_line,
    identify,
    peek,
    stamp,
    store,
)
from microsd_utils.manifest import Manifest
from microsd_utils.passes import (
    BYTES_PER_MB,
    PassResult,
    pattern,
    read_pass,
    write_pass,
)
from microsd_utils.random_io import (
    SCRATCH_BYTES,
    RandomResult,
    random_read_pass,
    random_write_pass,
)
from microsd_utils.reader import CardInfo, discover, recheck
from microsd_utils.session import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_RETIRE,
    Env,
    card_line,
    confirmed_erase,
    erase_warning,
    gigabytes,
    preflight,
    progress_printer,
)
from microsd_utils.verdict import (
    Grade,
    Measurements,
    Verdict,
    decide,
    read_a_class,
    write_a_class,
)


def volume_names(
    card: CardInfo, list_volume: Callable[[str], list[str]]
) -> list[str] | None:
    if len(card.partitions) != 1 or card.partitions[0].mount_point is None:
        return None
    return list_volume(card.partitions[0].mount_point)


def describe_plan(card: CardInfo, is_destructive: bool) -> str:
    if is_destructive:
        return (
            f"Plan: unmount {card.identifier}, random 4 KB writes and reads, then "
            f"write and verify every block of {card.raw_device} "
            f"({gigabytes(card.size_bytes)}), then format it FAT32 and write "
            f"its manifest back.\n{erase_warning(card)}"
        )
    size = gigabytes(card.size_bytes)
    return (
        f"Plan: random 4 KB reads, then read every block of {card.raw_device} ({size})."
    )


def pass_line(label: str, result: PassResult) -> str:
    errors = len(result.error_offsets) + len(result.mismatch_offsets)
    return (
        f"{label}: {result.total_bytes / BYTES_PER_MB:,.0f} MB in "
        f"{result.seconds:.0f} s, {result.mb_per_s:.1f} MB/s, {errors} bad chunks"
    )


def random_line(read: RandomResult, write: RandomResult | None) -> str:
    line = f"Random  : read {read.iops:,.0f} IOPS ({read_a_class(read.iops)})"
    if write is not None:
        line += f", write {write.iops:,.0f} IOPS ({write_a_class(write.iops)})"
    return line


def report(env: Env, measured: Measurements, verdict: Verdict) -> None:
    if measured.write is not None:
        env.out(pass_line("Write   ", measured.write))
        env.out(pass_line("Verify  ", measured.read))
    else:
        env.out(pass_line("Read    ", measured.read))
    env.out(random_line(measured.random_read, measured.random_write))
    scope = " (read-only: write not measured)" if verdict.is_read_only else ""
    env.out(f"Verdict: {verdict.grade.name}{scope}")
    if verdict.is_brand_new:
        env.out("Looks brand new")
    for reason in verdict.reasons:
        env.out(f"  - {reason}")


def run_random_read(env: Env, device, card: CardInfo) -> RandomResult:
    env.out(f"Random reads ({env.random_seconds:.0f} s)...")
    return random_read_pass(device.read_at, card.size_bytes, env.random_seconds)


def run_passes(env: Env, card: CardInfo, is_destructive: bool) -> Measurements:
    size_bytes = card.size_bytes
    if not is_destructive:
        with env.open_device(card, False) as device:
            random_read = run_random_read(env, device, card)
            on_read = progress_printer("Read", env.out)
            read = read_pass(device.read_at, size_bytes, on_read)
        return Measurements(read, None, random_read, None)
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, True) as device:
        # Random writes go in a scratch region the full write pass overwrites.
        env.out(f"Random writes ({env.random_seconds:.0f} s)...")
        scratch_bytes = min(SCRATCH_BYTES, size_bytes)
        random_write = random_write_pass(
            device.write_at, scratch_bytes, env.random_seconds
        )
        random_read = run_random_read(env, device, card)
        on_write = progress_printer("Write", env.out)
        on_verify = progress_printer("Verify", env.out)
        write = write_pass(device.write_at, size_bytes, on_write)
        read = read_pass(device.read_at, size_bytes, on_verify, pattern)
    return Measurements(read, write, random_read, random_write)


def stress_passes(env: Env, card: CardInfo, manifest: Manifest) -> Measurements:
    """Destructive passes; a failure is recorded against the card, then raised."""
    try:
        return run_passes(env, card, True)
    except Exception as error:
        failed = manifest.with_event(event(env, "stress", f"failed: {error}"))
        env.registry.record(failed, stamp(env))
        raise


def retag(env: Env, card: CardInfo, manifest: Manifest, grade: Grade) -> None:
    """Format the wiped card FAT32, named after its ID, and put the manifest
    back with the result."""
    recheck(env.diskutil, env.fingerprint, card)
    env.out(f"Formatting {card.identifier} FAT32 as {manifest.card_id}...")
    env.diskutil.erase_fat32(card.identifier, manifest.card_id)
    formatted = discover(env.diskutil, env.fingerprint)
    result = manifest.with_event(event(env, "formatted", "FAT32"), contents="empty")
    store(env, formatted, result.with_event(event(env, "stress", grade.name)))


def run_check(env: Env, is_destructive: bool, is_dry_run: bool) -> int:
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    env.out(id_line(peek(env, card), ASK_HINT if is_destructive else UNTAGGED_HINT))
    code = preflight(env, describe_plan(card, is_destructive), is_dry_run)
    if code is not None:
        return code
    # Before the passes: destructive mode unmounts and wipes the volume.
    fresh = assess(card, volume_names(card, env.list_volume))
    if is_destructive:
        manifest = identify(env, card)
        if not confirmed_erase(env, card):
            env.out("Not confirmed. Nothing written.")
            return EXIT_ERROR
        measured = stress_passes(env, card, manifest)
    else:
        measured = run_passes(env, card, False)
    verdict = decide(measured, fresh)
    report(env, measured, verdict)
    if is_destructive:
        retag(env, card, manifest, verdict.grade)
    return EXIT_RETIRE if verdict.grade is Grade.RETIRE else EXIT_OK

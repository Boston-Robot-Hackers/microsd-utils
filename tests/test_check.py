#!/usr/bin/env python3
# test_check — tests for the `microsd check` flow, with every side effect faked
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import pytest

from microsd_utils.check import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_RETIRE,
    progress_printer,
    run_check,
    volume_names,
)
from microsd_utils.passes import CHUNK_BYTES
from microsd_utils.reader import ReaderError, parse_card
from microsd_utils.verdict import Grade, Verdict
from tests.fakes import FakeCard, Recorder, load_plist, make_test_env

CARD_BYTES = 3 * CHUNK_BYTES


def make_env(recorder, card, is_root=True, extra_disks=0):
    return make_test_env(
        recorder, {"disk4": card}, CARD_BYTES, is_root=is_root, extra_disks=extra_disks
    )


def test_read_only_check_reads_and_never_writes():
    recorder, card = Recorder(), FakeCard(CARD_BYTES)
    env = make_env(recorder, card)
    assert run_check(env, is_destructive=False, is_dry_run=False) == EXIT_OK
    assert recorder.opened == [("disk4", False)]
    assert card.writes == 0
    assert env.diskutil.unmounted == []
    assert "Verdict: EXCELLENT (read-only: write not measured)" in recorder.text
    assert "Random  : read" in recorder.text
    assert ", write" not in recorder.text


def test_destructive_check_with_confirmation():
    recorder, card = Recorder(answers=["yes\n", "disk4\n"]), FakeCard(CARD_BYTES)
    env = make_env(recorder, card)
    assert run_check(env, is_destructive=True, is_dry_run=False) == EXIT_OK
    assert recorder.opened == [("disk4", True)]
    assert env.diskutil.unmounted == ["disk4"]
    assert "Write " in recorder.text
    assert "Verify" in recorder.text


@pytest.mark.parametrize(
    "answers",
    [
        ["", ""],
        ["y", "disk4"],
        ["no", "disk4"],
        ["disk4", "disk4"],
        ["yes", ""],
        ["yes", "yes"],
        ["yes", "disk5"],
        ["yes", "/dev/disk4"],
    ],
)
def test_wrong_confirmation_writes_nothing(answers):
    recorder, card = Recorder(answers=answers), FakeCard(CARD_BYTES)
    env = make_env(recorder, card)
    assert run_check(env, is_destructive=True, is_dry_run=False) == EXIT_ERROR
    assert recorder.opened == []
    assert env.diskutil.unmounted == []
    assert "Nothing written" in recorder.text


@pytest.mark.parametrize("is_destructive", [False, True])
def test_dry_run_touches_nothing(is_destructive):
    recorder = Recorder()
    env = make_env(recorder, FakeCard(CARD_BYTES), is_root=False)
    assert run_check(env, is_destructive, is_dry_run=True) == EXIT_OK
    assert recorder.opened == []
    assert env.diskutil.unmounted == []
    assert "/dev/rdisk4" in recorder.text


@pytest.mark.parametrize("is_destructive", [False, True])
def test_not_root_explains_then_elevates_before_io(is_destructive):
    recorder = Recorder()
    env = make_env(recorder, FakeCard(CARD_BYTES), is_root=False)
    run_check(env, is_destructive, is_dry_run=False)
    assert recorder.opened == []
    assert env.diskutil.unmounted == []
    assert recorder.lines[-1] == "<sudo>"
    explained = recorder.text.index("password")
    assert recorder.text.index("Plan:") < explained < recorder.text.index("<sudo>")


def test_two_readers_are_refused():
    recorder = Recorder()
    env = make_env(recorder, FakeCard(CARD_BYTES), extra_disks=1)
    with pytest.raises(ReaderError, match="Several disks"):
        run_check(env, is_destructive=False, is_dry_run=False)
    assert recorder.opened == []


def test_bad_card_is_retired():
    recorder = Recorder(answers=["yes", "disk4"])
    card = FakeCard(CARD_BYTES, corrupt_offset=CHUNK_BYTES)
    env = make_env(recorder, card)
    assert run_check(env, is_destructive=True, is_dry_run=False) == EXIT_RETIRE
    assert "Verdict: RETIRE" in recorder.text
    assert "1 chunks read back wrong" in recorder.text


def test_volume_names_lists_single_mounted_partition():
    info = load_plist("norelsys-card-info.plist")
    disk_list = load_plist("norelsys-card-list.plist")
    partitions = disk_list["AllDisksAndPartitions"][0]["Partitions"]
    del partitions[1]
    card = parse_card(info, disk_list)
    assert volume_names(card, lambda path: [path]) == ["/Volumes/system-boot"]


def test_volume_names_none_for_two_partitions():
    card = parse_card(
        load_plist("norelsys-card-info.plist"), load_plist("norelsys-card-list.plist")
    )
    assert volume_names(card, lambda path: [path]) is None


def test_progress_prints_each_percent_once():
    recorder = Recorder()
    show = progress_printer("Read", recorder.out)
    for done in (0, 1, 2, 50, 100):
        show(done, 100)
    assert recorder.lines == [
        "\rRead   0%",
        "\rRead   1%",
        "\rRead   2%",
        "\rRead  50%",
        "\rRead 100%",
    ]


def test_erase_warning_comes_before_both_questions():
    recorder = Recorder(answers=["yes", "disk4"])
    env = make_env(recorder, FakeCard(CARD_BYTES))
    run_check(env, is_destructive=True, is_dry_run=False)
    assert "WARNING: EVERYTHING ON THIS CARD WILL BE ERASED." in recorder.lines[1]
    assert "ARE YOU SURE" in recorder.prompts[0]
    assert "disk4" in recorder.prompts[1]


@pytest.mark.parametrize("is_dry_run", [False, True])
def test_erase_warning_shown_before_sudo_and_in_dry_run(is_dry_run):
    recorder = Recorder()
    env = make_env(recorder, FakeCard(CARD_BYTES), is_root=False)
    run_check(env, is_destructive=True, is_dry_run=is_dry_run)
    assert "THIS CANNOT BE UNDONE" in recorder.text
    assert recorder.prompts == []


def test_no_erase_warning_for_read_only():
    recorder = Recorder()
    run_check(make_env(recorder, FakeCard(CARD_BYTES)), False, False)
    assert "ERASED" not in recorder.text


def test_destructive_pass_order_and_random_writes_in_scratch(monkeypatch):
    monkeypatch.setattr("microsd_utils.check.SCRATCH_BYTES", CHUNK_BYTES)
    recorder, card = Recorder(answers=["yes", "disk4"]), FakeCard(CARD_BYTES)
    run_check(make_env(recorder, card), is_destructive=True, is_dry_run=False)
    random_writes = [offset for offset, length in card.write_log if length == 4096]
    assert random_writes
    assert all(offset < CHUNK_BYTES for offset in random_writes)
    first_full_write = next(
        i for i, (_, length) in enumerate(card.write_log) if length != 4096
    )
    assert all(length != 4096 for _, length in card.write_log[first_full_write:])
    text = recorder.text
    assert (
        text.index("Random writes") < text.index("Random reads") < text.index("Write")
    )


def test_destructive_report_has_both_random_directions():
    recorder, card = Recorder(answers=["yes", "disk4"]), FakeCard(CARD_BYTES)
    run_check(make_env(recorder, card), is_destructive=True, is_dry_run=False)
    assert "IOPS (A2), write" in recorder.text
    assert "read-only" not in recorder.text
    assert "  - random: EXCELLENT (A2 level)" in recorder.lines


@pytest.mark.parametrize(
    "grade, exit_code",
    [
        (Grade.EXCELLENT, EXIT_OK),
        (Grade.GOOD, EXIT_OK),
        (Grade.FAIR, EXIT_OK),
        (Grade.RETIRE, EXIT_RETIRE),
    ],
)
def test_exit_code_and_verdict_line_per_grade(monkeypatch, grade, exit_code):
    monkeypatch.setattr(
        "microsd_utils.check.decide",
        lambda measured, fresh: Verdict(grade, ["why"], False, True),
    )
    recorder = Recorder(answers=["yes", "disk4"])
    env = make_env(recorder, FakeCard(CARD_BYTES))
    assert run_check(env, is_destructive=True, is_dry_run=False) == exit_code
    assert f"Verdict: {grade.name}" in recorder.lines
    assert "Looks brand new" in recorder.lines

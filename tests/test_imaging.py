#!/usr/bin/env python3
# test_imaging — tests for the backup, flash and copy commands, all faked
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license

import gzip
import json

import pytest

from microsd_utils.images import ImageError, ImageStore
from microsd_utils.imaging import run_backup, run_copy, run_flash
from microsd_utils.passes import CHUNK_BYTES
from microsd_utils.reader import CardInfo, Partition
from microsd_utils.session import EXIT_ERROR, EXIT_OK
from microsd_utils.transfer import TransferError
from tests.fakes import FakeCard, Recorder, make_test_env, partitioned_card

CARD_BYTES = 4 * CHUNK_BYTES
DATA_BYTES = 3 * CHUNK_BYTES
YES = ["yes", "disk4"]


@pytest.fixture
def store(tmp_path):
    return ImageStore(tmp_path / "images")


def backed_up(store, recorder=None):
    """Store an image named `pi` from a partitioned card; return the card."""
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    env = make_test_env(
        recorder or Recorder(), {"disk4": master}, CARD_BYTES, images=store
    )
    assert run_backup(env, "pi", is_dry_run=False) == EXIT_OK
    return master


def test_backup_saves_partitions_and_sidecar(store):
    recorder = Recorder()
    master = backed_up(store, recorder)
    data = gzip.decompress(store.image_path("pi").read_bytes())
    assert data == bytes(master.store[:DATA_BYTES])
    info = json.loads(store.info_path("pi").read_text())
    assert info["data_bytes"] == DATA_BYTES
    assert info["source_size_bytes"] == CARD_BYTES
    assert recorder.opened == [("disk4", False)]
    assert master.writes == 0
    assert "The card is only read." in recorder.text


def test_backup_existing_name_refused_before_anything(store):
    backed_up(store)
    recorder = Recorder()
    env = make_test_env(recorder, {}, CARD_BYTES, images=store)
    with pytest.raises(ImageError, match="already exists"):
        run_backup(env, "pi", is_dry_run=False)
    assert recorder.lines == []


@pytest.mark.parametrize("is_root, is_dry_run", [(True, True), (False, False)])
def test_backup_dry_run_and_unprivileged_touch_nothing(store, is_root, is_dry_run):
    recorder = Recorder()
    card = partitioned_card(CARD_BYTES, DATA_BYTES)
    env = make_test_env(
        recorder, {"disk4": card}, CARD_BYTES, images=store, is_root=is_root
    )
    assert run_backup(env, "pi", is_dry_run) == EXIT_OK
    assert recorder.opened == []
    assert env.diskutil.unmounted == []
    assert not store.directory.exists()


def test_flash_writes_verifies_and_ejects(store):
    master = backed_up(store)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=YES)
    env = make_test_env(recorder, {"disk4": target}, CARD_BYTES, images=store)
    assert run_flash(env, "pi", is_dry_run=False) == EXIT_OK
    assert bytes(target.store[:DATA_BYTES]) == bytes(master.store[:DATA_BYTES])
    assert env.diskutil.ejected == ["disk4"]
    assert "Verified: OK. The card has been ejected." in recorder.lines
    assert "WARNING: EVERYTHING ON THIS CARD WILL BE ERASED." in recorder.text


@pytest.mark.parametrize("answers", [["", ""], ["y", "disk4"], ["yes", "disk5"]])
def test_flash_wrong_confirmation_writes_nothing(store, answers):
    backed_up(store)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=answers)
    env = make_test_env(recorder, {"disk4": target}, CARD_BYTES, images=store)
    assert run_flash(env, "pi", is_dry_run=False) == EXIT_ERROR
    assert target.writes == 0
    assert env.diskutil.unmounted == []


def test_flash_too_small_card_refused_before_asking(store):
    backed_up(store)
    recorder = Recorder(answers=YES)
    small = DATA_BYTES - CHUNK_BYTES
    env = make_test_env(recorder, {"disk4": FakeCard(small)}, small, images=store)
    with pytest.raises(TransferError, match="has only"):
        run_flash(env, "pi", is_dry_run=False)
    assert recorder.prompts == []
    assert recorder.opened == []


def test_flash_dry_run_shows_warning_and_touches_nothing(store):
    backed_up(store)
    recorder = Recorder()
    target = FakeCard(CARD_BYTES)
    env = make_test_env(recorder, {"disk4": target}, CARD_BYTES, images=store)
    assert run_flash(env, "pi", is_dry_run=True) == EXIT_OK
    assert "THIS CANNOT BE UNDONE" in recorder.text
    assert recorder.opened == []
    assert recorder.prompts == []


def test_flash_unknown_image_refused(store):
    env = make_test_env(Recorder(), {}, CARD_BYTES, images=store)
    with pytest.raises(ImageError, match="no image named"):
        run_flash(env, "missing", is_dry_run=False)


MASTER = CardInfo("disk4", CARD_BYTES, 512, "1081CS0", ())
NEW = CardInfo("disk5", CARD_BYTES, 512, "1081CS0", ())


def scripted_poll(*cards):
    script = list(cards)
    return lambda: script.pop(0) if len(script) > 1 else script[0]


def copy_env(store, recorder, master, target, *polls):
    return make_test_env(
        recorder,
        {"disk4": master, "disk5": target},
        CARD_BYTES,
        images=store,
        poll=scripted_poll(*polls),
    )


def test_copy_backs_up_waits_for_swap_then_flashes(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=["yes", "disk5"])
    env = copy_env(store, recorder, master, target, MASTER, MASTER, None, None, NEW)
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_OK
    assert bytes(target.store[:DATA_BYTES]) == bytes(master.store[:DATA_BYTES])
    assert master.writes == 0
    assert recorder.opened == [("disk4", False), ("disk5", True)]
    assert env.diskutil.ejected == ["disk5"]
    text = recorder.text
    assert text.index("Remove the MASTER") < text.index("Insert the NEW")
    assert text.index("Insert the NEW") < text.index("WARNING")
    assert "Copy complete." in recorder.lines


def test_copy_asks_for_master_when_reader_empty(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    recorder = Recorder(answers=["yes", "disk5"])
    env = copy_env(
        store, recorder, master, FakeCard(CARD_BYTES), None, None, MASTER, None, NEW
    )
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_OK
    assert "Insert the MASTER card into the reader." in recorder.lines


def test_copy_not_confirmed_keeps_image_and_writes_nothing(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=["no"])
    env = copy_env(store, recorder, master, target, MASTER, None, NEW)
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_ERROR
    assert target.writes == 0
    assert store.image_path("pi").exists()


def test_copy_warns_when_new_card_looks_like_master(store):
    # Regression: re-inserted, the master gets new identifiers and is mounted
    # again, so only the layout can match.
    boot, root = ("Windows_FAT_32", 536_870_912), ("Linux", 2_000_000_000)
    master_info = CardInfo(
        "disk4",
        CARD_BYTES,
        512,
        "1081CS0",
        (Partition("disk4s1", *boot, None), Partition("disk4s2", *root, None)),
    )
    again = CardInfo(
        "disk5",
        CARD_BYTES,
        512,
        "1081CS0",
        (
            Partition("disk5s1", *boot, "/Volumes/bootfs"),
            Partition("disk5s2", *root, None),
        ),
    )
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    recorder = Recorder(answers=["no"])
    env = copy_env(
        store, recorder, master, FakeCard(CARD_BYTES), master_info, None, again
    )
    run_copy(env, "pi", is_dry_run=False)
    assert any("CAUTION" in line for line in recorder.lines)


def test_copy_no_caution_for_a_different_card(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    other = CardInfo("disk5", 2 * CARD_BYTES, 512, "1081CS0", ())
    recorder = Recorder(answers=["no"])
    env = copy_env(store, recorder, master, FakeCard(CARD_BYTES), MASTER, None, other)
    run_copy(env, "pi", is_dry_run=False)
    assert not any("CAUTION" in line for line in recorder.lines)


def test_copy_dry_run_touches_nothing(store):
    recorder = Recorder()
    env = copy_env(store, recorder, FakeCard(CARD_BYTES), FakeCard(CARD_BYTES), MASTER)
    assert run_copy(env, "pi", is_dry_run=True) == EXIT_OK
    assert recorder.opened == []
    assert not store.directory.exists()

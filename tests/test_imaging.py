#!/usr/bin/env python3
# test_imaging — tests for the backup, flash and copy commands, all faked
# Author: Pito Salas and Claude Code
# Version: 3
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license

import gzip
import json

import pytest

from microsd_utils import imaging
from microsd_utils.images import ImageError, ImageStore
from microsd_utils.imaging import run_backup, run_copy, run_flash, run_verify
from microsd_utils.manifest import manifest_path, read_manifest
from microsd_utils.passes import CHUNK_BYTES
from microsd_utils.reader import CardInfo, NoCardError, Partition
from microsd_utils.session import EXIT_ERROR, EXIT_OK
from microsd_utils.transfer import TransferError
from tests.fakes import FakeCard, Recorder, make_test_env, partitioned_card, tag

CARD_BYTES = 4 * CHUNK_BYTES
DATA_BYTES = 3 * CHUNK_BYTES
YES = ["yes", "disk4"]


@pytest.fixture
def store(tmp_path):
    return ImageStore(tmp_path / "images")


@pytest.fixture
def work(tmp_path):
    """Work dir whose card volume is tagged A1."""
    (tmp_path / "volume").mkdir()
    tag(tmp_path / "volume")
    return tmp_path


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


def test_flash_writes_verifies_and_ejects(store, work):
    master = backed_up(store)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=YES)
    env = make_test_env(
        recorder, {"disk4": target}, CARD_BYTES, images=store, work_dir=work
    )
    assert run_flash(env, "pi", is_dry_run=False) == EXIT_OK
    assert bytes(target.store[:DATA_BYTES]) == bytes(master.store[:DATA_BYTES])
    assert env.diskutil.ejected == ["disk4"]
    assert "Verified: OK." in recorder.lines
    assert "The card has been ejected." in recorder.lines
    assert "WARNING: EVERYTHING ON THIS CARD WILL BE ERASED." in recorder.text


@pytest.mark.parametrize("answers", [["", ""], ["y", "disk4"], ["yes", "disk5"]])
def test_flash_wrong_confirmation_writes_nothing(store, answers, work):
    backed_up(store)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=answers)
    env = make_test_env(
        recorder, {"disk4": target}, CARD_BYTES, images=store, work_dir=work
    )
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
NEW_ID = ["B2", ""]  # the new card's label ID, then no contents description


def scripted_poll(*cards):
    script = list(cards)
    return lambda: script.pop(0) if len(script) > 1 else script[0]


def copy_env(store, recorder, master, target, *polls, work_dir=None):
    env = make_test_env(
        recorder,
        {"disk4": master, "disk5": target},
        CARD_BYTES,
        images=store,
        poll=scripted_poll(*polls),
        work_dir=work_dir,
    )
    infos = env.diskutil.infos
    infos["disk5"] = dict(infos["disk4"], DeviceIdentifier="disk5")
    return env


def test_copy_backs_up_waits_for_swap_then_flashes(store, tmp_path):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=NEW_ID + ["yes", "disk5"])
    env = copy_env(
        store,
        recorder,
        master,
        target,
        MASTER,
        MASTER,
        None,
        None,
        NEW,
        work_dir=tmp_path,
    )
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_OK
    assert bytes(target.store[:DATA_BYTES]) == bytes(master.store[:DATA_BYTES])
    assert master.writes == 0
    assert recorder.opened == [("disk4", False), ("disk5", True)]
    assert env.diskutil.ejected == ["disk5"]
    text = recorder.text
    assert text.index("Remove the MASTER") < text.index("Insert the NEW")
    assert text.index("Insert the NEW") < text.index("WARNING")
    assert "Copy complete." in recorder.lines


def test_copy_asks_for_master_when_reader_empty(store, tmp_path):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    recorder = Recorder(answers=NEW_ID + ["yes", "disk5"])
    env = copy_env(
        store,
        recorder,
        master,
        FakeCard(CARD_BYTES),
        None,
        None,
        MASTER,
        None,
        NEW,
        work_dir=tmp_path,
    )
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_OK
    assert "Insert the MASTER card into the reader." in recorder.text


def test_copy_not_confirmed_keeps_image_and_writes_nothing(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    target = FakeCard(CARD_BYTES)
    recorder = Recorder(answers=NEW_ID + ["no"])
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
    recorder = Recorder(answers=NEW_ID + ["no"])
    env = copy_env(
        store, recorder, master, FakeCard(CARD_BYTES), master_info, None, again
    )
    run_copy(env, "pi", is_dry_run=False)
    assert any("CAUTION" in line for line in recorder.lines)


def test_copy_no_caution_for_a_different_card(store):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    other = CardInfo("disk5", 2 * CARD_BYTES, 512, "1081CS0", ())
    recorder = Recorder(answers=NEW_ID + ["no"])
    env = copy_env(store, recorder, master, FakeCard(CARD_BYTES), MASTER, None, other)
    run_copy(env, "pi", is_dry_run=False)
    assert not any("CAUTION" in line for line in recorder.lines)


def test_copy_dry_run_touches_nothing(store):
    recorder = Recorder()
    env = copy_env(store, recorder, FakeCard(CARD_BYTES), FakeCard(CARD_BYTES), MASTER)
    assert run_copy(env, "pi", is_dry_run=True) == EXIT_OK
    assert recorder.opened == []
    assert not store.directory.exists()


def test_backup_records_master_id_in_sidecar(store, work):
    recorder = Recorder()
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    env = make_test_env(
        recorder, {"disk4": master}, CARD_BYTES, images=store, work_dir=work
    )
    run_backup(env, "pi", is_dry_run=False)
    assert json.loads(store.info_path("pi").read_text())["source_card_id"] == "A1"
    assert "Card ID: A1  raspios" in recorder.lines
    assert len(read_manifest(work / "volume").history) == 1


def test_backup_untagged_card_has_no_id_in_sidecar(store):
    recorder = Recorder()
    backed_up(store, recorder)
    assert json.loads(store.info_path("pi").read_text())["source_card_id"] is None
    assert "Card ID: untagged; run `make card` to tag it" in recorder.lines


def test_flash_writes_target_manifest_back_after_verify(store, work):
    backed_up(store)
    recorder = Recorder(answers=YES)
    env = make_test_env(
        recorder,
        {"disk4": FakeCard(CARD_BYTES)},
        CARD_BYTES,
        images=store,
        work_dir=work,
    )
    run_flash(env, "pi", is_dry_run=False)
    manifest = read_manifest(work / "volume")
    assert manifest.card_id == "A1"
    assert manifest.contents == "pi"
    last = manifest.history[-1]
    assert (last.event, last.detail) == ("flash", "pi")
    assert env.diskutil.mounted[-2:] == ["disk4", "disk4s1"]
    text = recorder.text
    assert text.index("Verified: OK.") < text.index("Manifest written: A1")
    assert text.index("Manifest written: A1") < text.index("ejected")


def test_flash_untagged_target_asks_id_before_erase(store, tmp_path):
    backed_up(store)
    (tmp_path / "volume").mkdir()
    recorder = Recorder(answers=["d4", "", *YES])
    env = make_test_env(
        recorder,
        {"disk4": FakeCard(CARD_BYTES)},
        CARD_BYTES,
        images=store,
        work_dir=tmp_path,
    )
    assert run_flash(env, "pi", is_dry_run=False) == EXIT_OK
    assert "label" in recorder.prompts[0]
    assert read_manifest(tmp_path / "volume").card_id == "D4"


def test_flash_card_pulled_before_manifest_is_reported(store, work):
    backed_up(store)
    env = make_test_env(
        Recorder(answers=YES),
        {"disk4": FakeCard(CARD_BYTES)},
        CARD_BYTES,
        images=store,
        work_dir=work,
        poll=lambda: None,
    )
    with pytest.raises(NoCardError, match="A1's manifest"):
        run_flash(env, "pi", is_dry_run=False)


BOOT = Partition("disk5s1", "Windows_FAT_32", 536_870_912, None)
NEW_WITH_BOOT = CardInfo("disk5", CARD_BYTES, 512, "1081CS0", (BOOT,))


def test_copy_gives_new_card_its_own_id_not_the_masters(store, work, monkeypatch):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    master_boot = Partition("disk4s1", BOOT.content, BOOT.size_bytes, None)
    tagged_master = CardInfo("disk4", CARD_BYTES, 512, "1081CS0", (master_boot,))
    recorder = Recorder(answers=["A1", "B2", "", "yes", "disk5"])
    env = copy_env(
        store,
        recorder,
        master,
        FakeCard(CARD_BYTES),
        tagged_master,
        None,
        NEW_WITH_BOOT,
        NEW_WITH_BOOT,
        work_dir=work,
    )
    # The fake mounts every card's FAT in one place, so the master's manifest
    # is removed when the swap happens: the new card arrives untagged.
    real_identify = imaging.identify

    def identify_blank_new_card(env, card, forbidden_id=None):
        manifest_path(work / "volume").unlink()
        return real_identify(env, card, forbidden_id)

    monkeypatch.setattr(imaging, "identify", identify_blank_new_card)
    assert run_copy(env, "pi", is_dry_run=False) == EXIT_OK
    assert "A1 is the master card's ID" in recorder.text
    manifest = read_manifest(work / "volume")
    assert manifest.card_id == "B2"
    last = manifest.history[-1]
    assert (last.event, last.detail) == ("copy", "from A1 via image pi")
    info = json.loads(store.info_path("pi").read_text())
    assert info["source_card_id"] == "A1"


def test_copy_without_fat_on_new_card_records_registry_only(store, tmp_path):
    master = partitioned_card(CARD_BYTES, DATA_BYTES)
    recorder = Recorder(answers=NEW_ID + ["yes", "disk5"])
    env = copy_env(
        store,
        recorder,
        master,
        FakeCard(CARD_BYTES),
        MASTER,
        None,
        NEW,
        work_dir=tmp_path,
    )
    run_copy(env, "pi", is_dry_run=False)
    assert "registry only" in recorder.text
    last = env.registry.lookup("B2").history[-1]
    assert (last.event, last.detail) == ("copy", "from an untagged master via image pi")


def verify_env(store, card, recorder, is_root=True):
    return make_test_env(
        recorder, {"disk4": card}, CARD_BYTES, images=store, is_root=is_root
    )


def test_verify_matching_card_reads_only(store):
    master = backed_up(store)
    recorder = Recorder()
    env = verify_env(store, master, recorder)
    assert run_verify(env, "pi", is_dry_run=False) == EXIT_OK
    assert "Verified: OK." in recorder.lines
    assert "The card is only read." in recorder.text
    assert recorder.opened == [("disk4", False)]
    assert env.diskutil.unmounted == ["disk4"]
    assert master.writes == 0
    assert recorder.prompts == []


def test_verify_differing_card_reports_where_and_fails(store):
    master = backed_up(store)
    card = FakeCard(CARD_BYTES, corrupt_offset=CHUNK_BYTES)
    card.store[:] = master.store
    recorder = Recorder()
    env = verify_env(store, card, recorder)
    assert run_verify(env, "pi", is_dry_run=False) == EXIT_ERROR
    assert "Differs: 1 of 3 chunks (4 MiB each)" in recorder.lines
    assert "  partition 1 (Linux): 1" in recorder.lines
    assert "Verified: OK." not in recorder.lines
    assert card.writes == 0


@pytest.mark.parametrize("is_root, is_dry_run", [(True, True), (False, False)])
def test_verify_dry_run_and_unprivileged_touch_nothing(store, is_root, is_dry_run):
    master = backed_up(store)
    recorder = Recorder()
    env = verify_env(store, master, recorder, is_root=is_root)
    assert run_verify(env, "pi", is_dry_run) == EXIT_OK
    assert recorder.opened == []
    assert env.diskutil.unmounted == []


def test_flash_verify_failure_says_where_and_is_recorded(store, work):
    backed_up(store)
    target = FakeCard(CARD_BYTES, corrupt_offset=2 * CHUNK_BYTES)
    recorder = Recorder(answers=YES)
    env = make_test_env(
        recorder, {"disk4": target}, CARD_BYTES, images=store, work_dir=work
    )
    with pytest.raises(TransferError, match="verification failed"):
        run_flash(env, "pi", is_dry_run=False)
    assert "  partition 1 (Linux): 1" in recorder.lines
    last = env.registry.lookup("A1").history[-1]
    assert last.event == "flash"
    assert last.detail.startswith("failed: verification failed")
    assert env.diskutil.ejected == []


def test_flash_write_error_is_recorded(store, work):
    class BrokenCard(FakeCard):
        def write_at(self, offset, data):
            raise OSError("I/O error")

    backed_up(store)
    recorder = Recorder(answers=YES)
    env = make_test_env(
        recorder,
        {"disk4": BrokenCard(CARD_BYTES)},
        CARD_BYTES,
        images=store,
        work_dir=work,
    )
    with pytest.raises(OSError, match="I/O error"):
        run_flash(env, "pi", is_dry_run=False)
    last = env.registry.lookup("A1").history[-1]
    assert (last.event, last.detail) == ("flash", "failed: I/O error")

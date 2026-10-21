#!/usr/bin/env python3
# test_identity — tests for finding, asking for and storing a card's identity
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-20
# Updated: 2026-10-20
# Open Source Under MIT license

import pytest

from microsd_utils.identity import card_volume, identify, peek, store
from microsd_utils.manifest import IdentityError, Manifest, read_manifest
from microsd_utils.reader import CardInfo, Partition, ReaderError, discover
from tests.fakes import NOW_TEXT, FakeCard, Recorder, make_test_env, tag

CARD_BYTES = 62599987200


def setup(tmp_path, answers=(), is_tagged=False):
    volume = tmp_path / "volume"
    volume.mkdir()
    if is_tagged:
        tag(volume)
    recorder = Recorder(answers=answers)
    env = make_test_env(recorder, {"disk4": FakeCard(1)}, CARD_BYTES, work_dir=tmp_path)
    return env, recorder, discover(env.diskutil, env.fingerprint)


def with_partitions(*partitions):
    return CardInfo("disk4", CARD_BYTES, 512, "1081CS0", partitions)


BOOT = Partition("disk4s1", "Windows_FAT_32", 536870912, None)
ROOT = Partition("disk4s2", "Linux", 2000000000, None)


def test_card_volume_mounts_the_fat_partition(tmp_path):
    env, _, _ = setup(tmp_path)
    assert card_volume(env, with_partitions(BOOT, ROOT)) == tmp_path / "volume"
    assert env.diskutil.mounted == ["disk4s1"]


@pytest.mark.parametrize("partitions", [(), (ROOT,)])
def test_card_volume_none_without_fat(tmp_path, partitions):
    env, _, _ = setup(tmp_path)
    assert card_volume(env, with_partitions(*partitions)) is None
    assert env.diskutil.mounted == []


def test_card_volume_uses_first_of_two_fat_partitions_and_says_so(tmp_path):
    env, recorder, _ = setup(tmp_path)
    second = Partition("disk4s3", "DOS_FAT_32", 1000, None)
    card_volume(env, with_partitions(BOOT, second))
    assert env.diskutil.mounted == ["disk4s1"]
    assert "2 FAT partitions; using disk4s1" in recorder.text


def test_peek_records_a_tagged_card_in_the_registry(tmp_path):
    env, recorder, card = setup(tmp_path, is_tagged=True)
    assert peek(env, card).card_id == "A1"
    assert env.registry.lookup("A1").contents == "raspios"
    assert recorder.prompts == []


def test_peek_untagged_asks_nothing(tmp_path):
    env, recorder, card = setup(tmp_path)
    assert peek(env, card) is None
    assert recorder.prompts == []


def test_identify_tagged_card_asks_nothing(tmp_path):
    env, recorder, card = setup(tmp_path, is_tagged=True)
    assert identify(env, card).card_id == "A1"
    assert recorder.prompts == []


def test_identify_new_card_asks_id_and_contents(tmp_path):
    env, _, card = setup(tmp_path, answers=["b2", "robot image"])
    manifest = identify(env, card)
    assert manifest.card_id == "B2"
    assert manifest.contents == "robot image"
    assert [(e.at, e.event) for e in manifest.history] == [(NOW_TEXT, "tagged")]


def test_identify_known_id_confirmed_brings_back_history(tmp_path):
    env, recorder, card = setup(tmp_path, answers=["A1", "y"])
    known = Manifest("A1", "old pi", ())
    env.registry.record(known, NOW_TEXT)
    assert identify(env, card) == known
    assert "Known card:\nA1: old pi" in recorder.text


def test_identify_known_id_denied_asks_again(tmp_path):
    env, recorder, card = setup(tmp_path, answers=["A1", "n", "C3", ""])
    env.registry.record(Manifest("A1", "old pi", ()), NOW_TEXT)
    assert identify(env, card).card_id == "C3"
    assert "A1 belongs to another card" in recorder.text


def test_identify_bad_id_asked_again_then_gives_up(tmp_path):
    env, recorder, card = setup(tmp_path, answers=["toolong", "", "!"])
    with pytest.raises(IdentityError, match="no usable card ID after 3 tries"):
        identify(env, card)
    assert recorder.text.count("bad card ID") == 3


def test_identify_refuses_the_forbidden_id_typed(tmp_path):
    env, recorder, card = setup(tmp_path, answers=["A1", "B2", ""])
    assert identify(env, card, forbidden_id="A1").card_id == "B2"
    assert "A1 is the master card's ID" in recorder.text


def test_identify_refuses_a_card_already_tagged_with_forbidden_id(tmp_path):
    env, _, card = setup(tmp_path, is_tagged=True)
    with pytest.raises(IdentityError, match="the master's ID"):
        identify(env, card, forbidden_id="A1")


def test_store_writes_card_and_registry(tmp_path):
    env, recorder, card = setup(tmp_path)
    manifest = Manifest("B2", "pi", ())
    store(env, card, manifest)
    assert read_manifest(tmp_path / "volume") == manifest
    assert env.registry.lookup("B2") == manifest
    assert "Manifest written: B2" in recorder.lines


def test_store_without_fat_goes_to_registry_only(tmp_path):
    env, recorder, card = setup(tmp_path)
    store(env, with_partitions(ROOT), Manifest("B2", "pi", ()))
    assert read_manifest(tmp_path / "volume") is None
    assert env.registry.lookup("B2") is not None
    assert "registry only" in recorder.text


def test_store_rechecks_the_reader_first(tmp_path):
    env, _, card = setup(tmp_path)
    env.diskutil.infos["disk4"]["Size"] = 1
    with pytest.raises(ReaderError, match="no longer the card"):
        store(env, card, Manifest("B2", "pi", ()))
    assert read_manifest(tmp_path / "volume") is None

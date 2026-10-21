#!/usr/bin/env python3
# test_cards — tests for the `microsd card` and `microsd cards` commands
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-20
# Updated: 2026-10-20
# Open Source Under MIT license

from microsd_utils.cards import run_card, run_cards
from microsd_utils.manifest import Manifest, read_manifest
from microsd_utils.session import EXIT_OK
from tests.fakes import NOW_TEXT, Recorder, make_test_env, tag

CARD_BYTES = 62599987200


def card_env(tmp_path, answers=(), is_tagged=False):
    volume = tmp_path / "volume"
    volume.mkdir()
    if is_tagged:
        tag(volume)
    recorder = Recorder(answers=answers)
    return make_test_env(recorder, {}, CARD_BYTES, work_dir=tmp_path), recorder


def test_card_tags_an_untagged_card_after_yes(tmp_path):
    env, recorder = card_env(tmp_path, ["a1", "robot", "y"])
    assert run_card(env, is_dry_run=False) == EXIT_OK
    written = read_manifest(tmp_path / "volume")
    assert (written.card_id, written.contents) == ("A1", "robot")
    assert env.registry.lookup("A1") == written
    assert recorder.opened == []


def test_card_tag_declined_writes_nothing(tmp_path):
    env, recorder = card_env(tmp_path, ["a1", "robot", ""])
    run_card(env, is_dry_run=False)
    assert read_manifest(tmp_path / "volume") is None
    assert "Nothing written." in recorder.lines


def test_card_dry_run_shows_manifest_writes_nothing(tmp_path):
    env, recorder = card_env(tmp_path, ["a1", "robot"])
    run_card(env, is_dry_run=True)
    assert read_manifest(tmp_path / "volume") is None
    assert "A1: robot" in recorder.text
    assert "Dry run: nothing written." in recorder.lines


def test_card_shows_tagged_card_and_keeps_it(tmp_path):
    env, recorder = card_env(tmp_path, [""], is_tagged=True)
    run_card(env, is_dry_run=False)
    assert f"A1: raspios\n  {NOW_TEXT}  tagged" in recorder.lines
    assert read_manifest(tmp_path / "volume").contents == "raspios"
    assert len(recorder.prompts) == 1


def test_card_updates_contents_of_tagged_card(tmp_path):
    env, _ = card_env(tmp_path, ["pi robot v2", "y"], is_tagged=True)
    run_card(env, is_dry_run=False)
    assert read_manifest(tmp_path / "volume").contents == "pi robot v2"
    assert env.registry.lookup("A1").contents == "pi robot v2"


def test_cards_lists_registry(tmp_path):
    env, recorder = card_env(tmp_path)
    tagged = tag(tmp_path / "volume")
    env.registry.record(tagged, NOW_TEXT)
    env.registry.record(Manifest("B2", "", ()), NOW_TEXT)
    assert run_cards(env) == EXIT_OK
    assert recorder.lines[0].startswith("A1    raspios")
    assert f"last: tagged {NOW_TEXT}" in recorder.lines[0]
    assert recorder.lines[1].startswith("B2    -")
    assert "no events" in recorder.lines[1]


def test_cards_empty_registry(tmp_path):
    env, recorder = card_env(tmp_path)
    run_cards(env)
    assert recorder.lines[0].startswith("No cards recorded yet")

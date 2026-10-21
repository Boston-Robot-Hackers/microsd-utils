#!/usr/bin/env python3
# test_manifest — tests for card IDs, the manifest file and the registry
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-20
# Updated: 2026-10-20
# Open Source Under MIT license

import json

import pytest

from microsd_utils.manifest import (
    Event,
    IdentityError,
    Manifest,
    Registry,
    make_event,
    manifest_path,
    parse_id,
    read_manifest,
    to_dict,
    write_manifest,
)

TAGGED = Event("2026-10-20T14:05:00", "tagged", "")
CARD = Manifest("A1", "raspios", (TAGGED,))


@pytest.mark.parametrize(
    "text, card_id", [("A1", "A1"), ("pi7", "PI7"), (" b ", "B"), ("1234", "1234")]
)
def test_parse_id_accepts_and_upper_cases(text, card_id):
    assert parse_id(text) == card_id


@pytest.mark.parametrize("text", ["", "ABCDE", "A-1", "A 1", "É1", "../x"])
def test_parse_id_refuses_anything_else(text):
    with pytest.raises(IdentityError, match="bad card ID"):
        parse_id(text)


def test_unknown_event_refused():
    with pytest.raises(IdentityError, match="unknown event"):
        make_event("2026-10-20T14:05:00", "painted")


def test_with_event_appends_and_optionally_sets_contents():
    flash = Event("2026-10-21T09:00:00", "flash", "pi.img.gz")
    kept = CARD.with_event(flash)
    assert kept.history == (TAGGED, flash)
    assert kept.contents == "raspios"
    assert CARD.with_event(flash, "pi.img.gz").contents == "pi.img.gz"


def test_write_then_read_round_trip(tmp_path):
    write_manifest(tmp_path, CARD)
    assert read_manifest(tmp_path) == CARD
    assert json.loads(manifest_path(tmp_path).read_text())["id"] == "A1"
    assert not list(tmp_path.glob("**/*.partial"))


def test_no_manifest_reads_as_none(tmp_path):
    assert read_manifest(tmp_path) is None


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "{}",
        '{"id": "A1", "contents": "x"}',
        '{"id": "toolong", "contents": "x", "history": []}',
        '{"id": "A1", "contents": "x", "history": [{"at": "t", "event": "painted",'
        ' "detail": ""}]}',
        '{"id": "A1", "contents": "x", "history": "nope"}',
    ],
)
def test_malformed_manifest_raises_naming_the_file(tmp_path, content):
    path = manifest_path(tmp_path)
    path.parent.mkdir()
    path.write_text(content)
    with pytest.raises(IdentityError, match=str(path)):
        read_manifest(tmp_path)


def test_registry_empty_when_missing(tmp_path):
    registry = Registry(tmp_path / "tools" / "cards.json")
    assert registry.all_cards() == []
    assert registry.lookup("A1") is None


def test_registry_record_creates_dir_and_upserts(tmp_path):
    registry = Registry(tmp_path / "tools" / "cards.json")
    registry.record(CARD, "2026-10-20T14:05:00")
    newer = CARD.with_event(Event("2026-10-21T09:00:00", "flash", "pi"), "pi")
    registry.record(newer, "2026-10-21T09:00:00")
    registry.record(Manifest("B2", "", (TAGGED,)), "2026-10-21T10:00:00")
    assert registry.lookup("A1") == newer
    assert [(card.card_id, seen) for card, seen in registry.all_cards()] == [
        ("A1", "2026-10-21T09:00:00"),
        ("B2", "2026-10-21T10:00:00"),
    ]
    stored = json.loads(registry.path.read_text())
    assert stored["A1"] == to_dict(newer) | {"last_seen": "2026-10-21T09:00:00"}


def test_registry_files_given_to_sudo_user(tmp_path):
    chowned = []
    registry = Registry(
        tmp_path / "tools" / "cards.json",
        owner=(501, 20),
        chown=lambda path, uid, gid: chowned.append((path, uid, gid)),
    )
    registry.record(CARD, "2026-10-20T14:05:00")
    assert chowned == [
        (tmp_path / "tools", 501, 20),
        (tmp_path / "tools" / "cards.json", 501, 20),
    ]


def test_malformed_registry_raises(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text('{"A1": {"id": "A1"}}')
    with pytest.raises(IdentityError, match="entry A1"):
        Registry(path).lookup("A1")

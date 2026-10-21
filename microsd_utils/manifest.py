#!/usr/bin/env python3
# manifest — a card's identity: its label ID, contents and history
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-20
# Updated: 2026-10-20
# Open Source Under MIT license
"""The manifest each card carries, and the repo's registry of known cards.

Every physical card has a label with a 1–4 character ID (`A–Z`, `0–9`). The
card stores `.microsd_tools/manifest.json` on its FAT volume:

    {"id": "A1", "contents": "raspios-lite",
     "history": [{"at": "2026-10-20T14:05:00", "event": "flash",
                  "detail": "raspios-lite"}]}

The repo keeps `.microsd_tools/cards.json` (git-ignored): every card seen,
keyed by ID, holding the latest copy of its manifest plus `last_seen`.

A malformed manifest or registry raises `IdentityError`; it is never replaced
silently, since that would erase a card's history.
"""

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from microsd_utils.images import Owner, give_to_owner

TOOLS_DIR_NAME = ".microsd_tools"
MANIFEST_NAME = "manifest.json"
REGISTRY_PATH = Path(__file__).resolve().parent.parent / TOOLS_DIR_NAME / "cards.json"
ID_RE = re.compile(r"[A-Z0-9]{1,4}")
EVENTS = ("tagged", "formatted", "stress", "flash", "copy")


class IdentityError(Exception):
    """A card ID, manifest or registry can't be used."""


@dataclass(frozen=True)
class Event:
    at: str
    event: str
    detail: str


@dataclass(frozen=True)
class Manifest:
    card_id: str
    contents: str
    history: tuple[Event, ...]

    def with_event(self, event: Event, contents: str | None = None) -> "Manifest":
        return replace(
            self,
            history=(*self.history, event),
            contents=self.contents if contents is None else contents,
        )


def parse_id(text: str) -> str:
    """A label ID typed by the user, upper-cased; raises if it isn't one."""
    card_id = text.strip().upper()
    if not ID_RE.fullmatch(card_id):
        raise IdentityError(f"bad card ID {text!r}: use 1-4 letters or digits")
    return card_id


def make_event(at: str, event: str, detail: str = "") -> Event:
    if event not in EVENTS:
        raise IdentityError(f"unknown event {event!r}")
    return Event(at, event, detail)


def to_dict(manifest: Manifest) -> dict:
    return {
        "id": manifest.card_id,
        "contents": manifest.contents,
        "history": [vars(event) for event in manifest.history],
    }


def from_dict(fields: dict, source: str) -> Manifest:
    """Build a Manifest from parsed JSON; `source` names it in errors."""
    try:
        history = tuple(
            make_event(entry["at"], entry["event"], entry["detail"])
            for entry in fields["history"]
        )
        return Manifest(parse_id(fields["id"]), fields["contents"], history)
    except (KeyError, TypeError, AttributeError, IdentityError) as error:
        raise IdentityError(f"malformed manifest in {source}: {error}") from error


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise IdentityError(f"{path} is not valid JSON: {error}") from error


def manifest_path(volume: Path) -> Path:
    return volume / TOOLS_DIR_NAME / MANIFEST_NAME


def read_manifest(volume: Path) -> Manifest | None:
    """The manifest on a mounted card volume, or None if it has none."""
    path = manifest_path(volume)
    if not path.exists():
        return None
    return from_dict(load_json(path), str(path))


def write_manifest(volume: Path, manifest: Manifest) -> None:
    """Write via a temp file and rename, so a pulled card never holds half a
    manifest."""
    path = manifest_path(volume)
    path.parent.mkdir(exist_ok=True)
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(to_dict(manifest), indent=2) + "\n")
    partial.replace(path)


class Registry:
    """Every card seen, keyed by ID, in the repo's git-ignored cards.json."""

    def __init__(
        self,
        path: Path = REGISTRY_PATH,
        owner: Owner | None = None,
        chown: Callable[[Path, int, int], None] = os.chown,
    ):
        self.path = path
        self.owner = owner
        self.chown = chown

    def entries(self) -> dict:
        if not self.path.exists():
            return {}
        return load_json(self.path)

    def lookup(self, card_id: str) -> Manifest | None:
        fields = self.entries().get(card_id)
        if fields is None:
            return None
        return from_dict(fields, f"{self.path} entry {card_id}")

    def all_cards(self) -> list[tuple[Manifest, str]]:
        """(manifest, last seen) for every card, sorted by ID."""
        return [
            (from_dict(fields, f"{self.path} entry {card_id}"), fields["last_seen"])
            for card_id, fields in sorted(self.entries().items())
        ]

    def record(self, manifest: Manifest, seen_at: str) -> None:
        cards = self.entries()
        cards[manifest.card_id] = to_dict(manifest) | {"last_seen": seen_at}
        if not self.path.parent.exists():
            self.path.parent.mkdir(parents=True)
            give_to_owner(self.path.parent, self.owner, self.chown)
        self.path.write_text(json.dumps(cards, indent=2) + "\n")
        give_to_owner(self.path, self.owner, self.chown)

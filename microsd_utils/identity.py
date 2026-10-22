#!/usr/bin/env python3
# identity — find out which labelled card is in the reader, and keep it recorded
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-20
# Updated: 2026-10-22
# Open Source Under MIT license
"""Which card is this? The flow every command shares.

- `peek` reads the manifest from the card's FAT volume without asking
  anything; read-only commands use it to show the ID.
- `identify` peeks, and for an untagged card asks for the ID on its label.
  An ID already in the registry is shown and confirmed, so a card wiped
  elsewhere gets its history back. `forbidden_id` keeps a copy from taking
  the master's ID.
- `store` re-checks the reader, writes the manifest to the card's FAT volume
  and records it in the registry. With no FAT volume (an image that has
  none) the registry still gets it, with a warning.

FAT is the only filesystem macOS can write on a Pi card, so the manifest
lives there: `bootfs` on a Pi card, the whole card after a format.
"""

from pathlib import Path

from microsd_utils.manifest import (
    Event,
    IdentityError,
    Manifest,
    make_event,
    parse_id,
    read_manifest,
    write_manifest,
)
from microsd_utils.reader import CardInfo, recheck
from microsd_utils.session import Env, is_yes

FAT_CONTENTS = (
    "DOS_FAT_32",
    "Windows_FAT_32",
    "DOS_FAT_16",
    "Windows_FAT_16",
    "Microsoft Basic Data",
)
ID_TRIES = 3
UNTAGGED_HINT = "untagged; run `make card` to tag it"
ASK_HINT = "untagged; you'll be asked for the ID on its label"
ASK_HINT = "untagged; you'll be asked for the ID on its label"


def stamp(env: Env) -> str:
    return env.now().isoformat(timespec="seconds")


def card_volume(env: Env, card: CardInfo) -> Path | None:
    """Mount the card's FAT partition and return where; None if it has none."""
    fats = [part for part in card.partitions if part.content in FAT_CONTENTS]
    if not fats:
        return None
    if len(fats) > 1:
        env.out(f"The card has {len(fats)} FAT partitions; using {fats[0].identifier}.")
    return Path(env.diskutil.mount(fats[0].identifier))


def peek(env: Env, card: CardInfo) -> Manifest | None:
    volume = card_volume(env, card)
    manifest = None if volume is None else read_manifest(volume)
    if manifest is not None:
        env.registry.record(manifest, stamp(env))
    return manifest


def id_line(manifest: Manifest | None, untagged: str = UNTAGGED_HINT) -> str:
    if manifest is None:
        return f"Card ID: {untagged}"
    return f"Card ID: {manifest.card_id}  {manifest.contents}".rstrip()


def describe(manifest: Manifest) -> str:
    lines = [f"{manifest.card_id}: {manifest.contents or '(contents not recorded)'}"]
    lines += [
        f"  {entry.at}  {entry.event:<9} {entry.detail}".rstrip()
        for entry in manifest.history
    ]
    return "\n".join(lines)


def new_manifest(env: Env, card_id: str) -> Manifest:
    contents = env.ask("What's on this card? (Enter to skip): ").strip()
    return Manifest(card_id, contents, (make_event(stamp(env), "tagged"),))


def ask_for_id(env: Env, forbidden_id: str | None) -> Manifest:
    """Ask for the label ID until it names a new card or the user confirms
    a known one; give up after ID_TRIES answers."""
    for _ in range(ID_TRIES):
        try:
            card_id = parse_id(
                env.ask("ID on this card's label (1-4 letters/digits): ")
            )
        except IdentityError as error:
            env.out(str(error))
            continue
        if card_id == forbidden_id:
            env.out(f"{card_id} is the master card's ID; the new card needs its own.")
            continue
        known = env.registry.lookup(card_id)
        if known is None:
            return new_manifest(env, card_id)
        env.out(f"Known card:\n{describe(known)}")
        if is_yes(env.ask(f"Is this card {card_id}? [y/N] ")):
            return known
        env.out(f"{card_id} belongs to another card; check the label.")
    raise IdentityError(f"no usable card ID after {ID_TRIES} tries")


def identify(env: Env, card: CardInfo, forbidden_id: str | None = None) -> Manifest:
    manifest = peek(env, card)
    if manifest is None:
        env.out("This card has no manifest.")
        return ask_for_id(env, forbidden_id)
    if manifest.card_id == forbidden_id:
        raise IdentityError(
            f"this card's manifest says {forbidden_id}, the master's ID. "
            "Is it the master? Nothing written."
        )
    env.out(id_line(manifest))
    return manifest


def store(env: Env, card: CardInfo, manifest: Manifest) -> None:
    recheck(env.diskutil, env.fingerprint, card)
    volume = card_volume(env, card)
    if volume is None:
        env.out(
            f"WARNING: the card has no FAT partition, so {manifest.card_id} is "
            "recorded in the registry only, not on the card."
        )
    else:
        write_manifest(volume, manifest)
        env.out(f"Manifest written: {manifest.card_id}")
    env.registry.record(manifest, stamp(env))


def event(env: Env, kind: str, detail: str = "") -> Event:
    return make_event(stamp(env), kind, detail)


def record_event(
    env: Env, manifest: Manifest, kind: str, detail: str, contents: str | None = None
) -> Manifest:
    """Add an event to the card's history and save it in the registry."""
    updated = manifest.with_event(event(env, kind, detail), contents)
    env.registry.record(updated, stamp(env))
    return updated

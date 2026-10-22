#!/usr/bin/env python3
# cards — the `microsd card` and `microsd history` commands
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-20
# Updated: 2026-10-22
# Open Source Under MIT license
"""Look at card identities.

- **card**: show the card in the reader (ID, contents, history). An untagged
  card is tagged: ask for its label ID, show the manifest, write it after a
  `y`. A tagged card can have its contents description updated.
- **history**: list every card in the registry with its last event.

Neither touches the raw device, so they run without sudo; the manifest is
written as a file on the card's mounted FAT volume.
"""

from dataclasses import replace

from microsd_utils.identity import describe, identify, peek, store
from microsd_utils.manifest import Manifest
from microsd_utils.reader import discover
from microsd_utils.session import EXIT_OK, Env, card_line, is_yes


def update_contents(env: Env, manifest: Manifest) -> Manifest | None:
    """Ask for a new contents description; None if the user keeps it."""
    answer = env.ask("New description of what's on it (Enter to keep): ").strip()
    return replace(manifest, contents=answer) if answer else None


def run_card(env: Env, is_dry_run: bool) -> int:
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    manifest = peek(env, card)
    if manifest is None:
        manifest = identify(env, card)
        prompt = "Write this manifest to the card? [y/N] "
    else:
        env.out(describe(manifest))
        manifest = update_contents(env, manifest)
        if manifest is None:
            return EXIT_OK
        prompt = "Save the new description? [y/N] "
    env.out(describe(manifest))
    if is_dry_run:
        env.out("Dry run: nothing written.")
    elif is_yes(env.ask(prompt)):
        store(env, card, manifest)
    else:
        env.out("Nothing written.")
    return EXIT_OK


def run_history(env: Env) -> int:
    cards = env.registry.all_cards()
    if not cards:
        env.out(f"No cards recorded yet in {env.registry.path}.")
    for manifest, last_seen in cards:
        last = manifest.history[-1] if manifest.history else None
        latest = f"{last.event} {last.at}" if last else "no events"
        env.out(
            f"{manifest.card_id:<4}  {manifest.contents or '-':<24}  "
            f"last: {latest}  seen: {last_seen}"
        )
    return EXIT_OK

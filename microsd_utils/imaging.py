#!/usr/bin/env python3
# imaging — the backup, flash and copy commands
# Author: Pito Salas and Claude Code
# Version: 1
# Created: 2026-10-19
# Updated: 2026-10-19
# Open Source Under MIT license
"""`microsd backup`, `flash` and `copy`, all on the card in the designated reader.

- **backup NAME**: unmount the card and copy it, up to the end of its last
  partition, into `images/NAME.img.gz` with a sidecar recording size and hash.
- **flash IMAGE**: erase the card with an image (a stored name or any
  `.img`/`.img.gz`/`.img.xz` path), read it back to verify, eject it.
- **copy NAME**: back up the master card, have the user swap it for a new
  card in the same reader, then flash and verify the new card.

Every command shows its plan and re-runs itself under sudo before touching a
device. Anything that overwrites a card first shows the erase warning and
asks for "yes" and the card's identifier. In `copy`, the master stays
unmounted but is not ejected, so the reader keeps reporting it until it is
physically pulled; only then is a new card accepted.
"""

from datetime import date

from microsd_utils.images import ImageInfo, ImageSource
from microsd_utils.passes import BYTES_PER_MB, PassResult
from microsd_utils.reader import CardInfo, discover
from microsd_utils.session import (
    EXIT_ERROR,
    EXIT_OK,
    Env,
    card_line,
    confirmed_erase,
    erase_warning,
    gigabytes,
    preflight,
    progress_printer,
)
from microsd_utils.swap import wait_for_insert, wait_for_removal
from microsd_utils.transfer import (
    backup_card,
    check_fits,
    copy_length,
    verify_card,
    write_image,
)


def timing_line(label: str, timing: PassResult) -> str:
    return (
        f"{label}: {timing.total_bytes / BYTES_PER_MB:,.0f} MB in "
        f"{timing.seconds:.0f} s, {timing.mb_per_s:.1f} MB/s"
    )


def backup_into(env: Env, card: CardInfo, name: str) -> ImageInfo:
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, False) as device:
        length = copy_length(device.read_at, card.size_bytes, card.block_size_bytes)
        env.out(f"Copying {gigabytes(length)}, up to the end of the last partition.")
        with env.images.create(name) as stream:
            on_progress = progress_printer("Backup", env.out)
            timing, sha256 = backup_card(device.read_at, length, stream, on_progress)
    info = ImageInfo(
        name=name,
        source_media_name=card.media_name,
        source_size_bytes=card.size_bytes,
        data_bytes=length,
        sha256=sha256,
        created=date.today().isoformat(),
    )
    env.images.save_info(info)
    env.out(timing_line("Backup ", timing))
    env.out(f"Saved  : {env.images.image_path(name)}")
    return info


def flash_onto(env: Env, card: CardInfo, source: ImageSource) -> None:
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, True) as device:
        on_write = progress_printer("Flash", env.out)
        on_verify = progress_printer("Verify", env.out)
        written = write_image(device.write_at, source, on_write)
        verified = verify_card(device.read_at, source, on_verify)
    env.diskutil.eject(card.identifier)
    env.out(timing_line("Flash  ", written))
    env.out(timing_line("Verify ", verified))
    env.out("Verified: OK. The card has been ejected.")


def run_backup(env: Env, name: str, is_dry_run: bool) -> int:
    env.images.check_new_name(name)
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    plan = (
        f"Plan: unmount {card.identifier} and copy its partitions into "
        f"{env.images.image_path(name)}. The card is only read."
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    backup_into(env, card, name)
    return EXIT_OK


def run_flash(env: Env, image: str, is_dry_run: bool) -> int:
    path = env.images.locate(image)
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    plan = (
        f"Plan: write {path} to {card.raw_device}, read it back to verify, "
        f"then eject the card.\n{erase_warning(card)}"
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    source = env.images.find(image)
    check_fits(source, card.size_bytes, card.block_size_bytes)
    if not confirmed_erase(env, card):
        env.out("Not confirmed. Nothing written.")
        return EXIT_ERROR
    flash_onto(env, card, source)
    return EXIT_OK


def take_master(env: Env) -> CardInfo:
    master = env.poll()
    if master is None:
        env.out("Insert the MASTER card into the reader.")
        master = wait_for_insert(env.poll, **env.wait_timing)
    env.out(card_line("Master", master))
    return master


def layout(card: CardInfo) -> tuple:
    """Size and partition types/sizes; identifiers and mount points differ
    every time a card is inserted, so they're left out."""
    parts = tuple((part.content, part.size_bytes) for part in card.partitions)
    return card.size_bytes, parts


def take_new_card(env: Env, master: CardInfo) -> CardInfo:
    env.out("Remove the MASTER card from the reader now.")
    wait_for_removal(env.poll, **env.wait_timing)
    env.out("Insert the NEW card. It will be erased.")
    card = wait_for_insert(env.poll, **env.wait_timing)
    env.out(card_line("New card", card))
    if layout(card) == layout(master):
        env.out("CAUTION: this card has the same size and partitions as the master.")
    return card


def run_copy(env: Env, name: str, is_dry_run: bool) -> int:
    env.images.check_new_name(name)
    plan = (
        f"Plan: back up the MASTER card into {env.images.image_path(name)}, ask "
        "you to swap in a NEW card, then flash and verify the new card. "
        "The new card will be ERASED."
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    master = take_master(env)
    backup_into(env, master, name)
    card = take_new_card(env, master)
    source = env.images.find(name)
    check_fits(source, card.size_bytes, card.block_size_bytes)
    env.out(erase_warning(card))
    if not confirmed_erase(env, card):
        env.out(f"Not confirmed. Nothing written; the image is saved as {name}.")
        return EXIT_ERROR
    flash_onto(env, card, source)
    env.out("Copy complete.")
    return EXIT_OK

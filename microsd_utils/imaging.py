#!/usr/bin/env python3
# imaging — the backup, flash and copy commands
# Author: Pito Salas and Claude Code
# Version: 4
# Created: 2026-10-19
# Updated: 2026-10-22
# Open Source Under MIT license
"""`microsd backup`, `flash` and `copy`, all on the card in the designated reader.

- **backup NAME**: unmount the card and copy it, up to the end of its last
  partition, into `images/NAME.img.gz` with a sidecar recording size and hash.
- **flash IMAGE**: erase the card with an image (a stored name or any
  `.img`/`.img.gz`/`.img.xz` path), read it back to verify, eject it.
- **copy NAME**: back up the master card, have the user swap it for a new
  card in the same reader, then flash and verify the new card.
- **verify IMAGE**: unmount the card, read it, and compare it with an image
  chunk by chunk; say where it differs. Only reads the card.

Flash's own read-back uses the same comparison. A failed flash or copy is
recorded in the target card's registry history before the error propagates.

Flash and copy identify the target card before writing (asking for its label
ID if untagged) and write its own manifest back into the new FAT partition
afterwards, so the card keeps its ID and history. A copy never takes the
master's ID. Backup only reads: it records the master's ID in the sidecar.

Every command shows its plan and re-runs itself under sudo before touching a
device. Anything that overwrites a card first shows the erase warning and
asks for "yes" and the card's identifier. In `copy`, the master stays
unmounted but is not ejected, so the reader keeps reporting it until it is
physically pulled; only then is a new card accepted.
"""

from datetime import date
from pathlib import Path

from microsd_utils.identity import (
    ASK_HINT,
    UNTAGGED_HINT,
    event,
    id_line,
    identify,
    peek,
    record_event,
    store,
)
from microsd_utils.images import ImageInfo, ImageSource
from microsd_utils.manifest import Manifest
from microsd_utils.passes import BYTES_PER_MB, PassResult, ReadAt
from microsd_utils.reader import CardInfo, NoCardError, discover
from microsd_utils.session import (
    EXIT_ERROR,
    EXIT_OK,
    Env,
    card_line,
    confirmed_erase,
    erase_warning,
    human_size,
    preflight,
    progress_printer,
)
from microsd_utils.swap import wait_for_insert, wait_for_removal
from microsd_utils.transfer import (
    TransferError,
    backup_card,
    check_fits,
    compare_card,
    copy_length,
    difference_lines,
    write_image,
)

WAITING = "(Waiting as long as it takes; Ctrl-C to stop.)"


def timing_line(label: str, timing: PassResult) -> str:
    return (
        f"{label}: {timing.total_bytes / BYTES_PER_MB:,.0f} MB in "
        f"{timing.seconds:.0f} s, {timing.mb_per_s:.1f} MB/s"
    )


def backup_into(env: Env, card: CardInfo, name: str, card_id: str | None) -> ImageInfo:
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, False) as device:
        length = copy_length(device.read_at, card.size_bytes, card.block_size_bytes)
        env.out(f"Copying {human_size(length)}, up to the end of the last partition.")
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
        source_card_id=card_id,
    )
    env.images.save_info(info)
    env.out(timing_line("Backup ", timing))
    env.out(f"Saved  : {env.images.image_path(name)}")
    return info


def holds_image(env: Env, read_at: ReadAt, card: CardInfo, source: ImageSource) -> bool:
    """Compare the card with the image and report; True if they match."""
    comparison = compare_card(read_at, source, progress_printer("Verify", env.out))
    env.out(timing_line("Verify ", comparison.timing))
    if not comparison.differing_spans:
        env.out("Verified: OK.")
        return True
    for line in difference_lines(source, card.block_size_bytes, comparison):
        env.out(line)
    return False


def flash_onto(env: Env, card: CardInfo, source: ImageSource) -> None:
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, True) as device:
        on_write = progress_printer("Flash", env.out)
        written = write_image(device.write_at, source, on_write)
        env.out(timing_line("Flash  ", written))
        is_verified = holds_image(env, device.read_at, card, source)
    if not is_verified:
        raise TransferError("verification failed: the card doesn't hold the image")


def flash_and_restore(
    env: Env, card: CardInfo, source: ImageSource, before: Manifest, after: Manifest
) -> None:
    """Flash, verify, and write `after` (the target's manifest with this
    flash's event) back. A failure is recorded against the card as that
    event's kind with `failed: <error>`, then raised."""
    try:
        flash_onto(env, card, source)
        restore_manifest(env, card, after)
    except Exception as error:
        record_event(env, before, after.history[-1].event, f"failed: {error}")
        raise


def restore_manifest(env: Env, card: CardInfo, manifest: Manifest) -> None:
    """After a flash: have macOS mount the new partitions, put the target's
    manifest back, eject."""
    env.diskutil.mount_disk(card.identifier)
    flashed = env.poll()
    if flashed is None:
        raise NoCardError(
            f"the card was removed before {manifest.card_id}'s manifest was "
            "written; put it back and run `make card`"
        )
    store(env, flashed, manifest)
    env.diskutil.eject(flashed.identifier)
    env.out("The card has been ejected.")


def run_backup(env: Env, name: str, is_dry_run: bool) -> int:
    env.images.check_new_name(name)
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    manifest = peek(env, card)
    env.out(id_line(manifest, UNTAGGED_HINT))
    plan = (
        f"Plan: unmount {card.identifier} and copy its partitions into "
        f"{env.images.image_path(name)}. The card is only read."
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    backup_into(env, card, name, manifest.card_id if manifest else None)
    return EXIT_OK


def run_flash(env: Env, image: str, is_dry_run: bool) -> int:
    path = env.images.locate(image)
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    env.out(id_line(peek(env, card), ASK_HINT))
    plan = (
        f"Plan: write {path} to {card.raw_device}, read it back to verify, "
        f"write the card's manifest back, then eject it.\n{erase_warning(card)}"
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    source = env.images.find(image)
    check_fits(source, card.size_bytes, card.block_size_bytes)
    manifest = identify(env, card)
    if not confirmed_erase(env, card):
        env.out("Not confirmed. Nothing written.")
        return EXIT_ERROR
    image_name = Path(image).name
    flashed = manifest.with_event(event(env, "flash", image_name), image_name)
    flash_and_restore(env, card, source, manifest, flashed)
    return EXIT_OK


def run_verify(env: Env, image: str, is_dry_run: bool) -> int:
    path = env.images.locate(image)
    card = discover(env.diskutil, env.fingerprint)
    env.out(card_line("Card", card))
    env.out(id_line(peek(env, card), UNTAGGED_HINT))
    plan = (
        f"Plan: unmount {card.identifier} and compare it with {path}. "
        "The card is only read."
    )
    code = preflight(env, plan, is_dry_run)
    if code is not None:
        return code
    source = env.images.find(image)
    check_fits(source, card.size_bytes, card.block_size_bytes)
    env.diskutil.unmount_disk(card.identifier)
    with env.open_device(card, False) as device:
        is_verified = holds_image(env, device.read_at, card, source)
    return EXIT_OK if is_verified else EXIT_ERROR


def take_master(env: Env) -> CardInfo:
    master = env.poll()
    if master is None:
        env.out(f"Insert the MASTER card into the reader. {WAITING}")
        master = wait_for_insert(env.poll, env.sleep)
    env.out(card_line("Master", master))
    return master


def layout(card: CardInfo) -> tuple:
    """Size and partition types/sizes; identifiers and mount points differ
    every time a card is inserted, so they're left out."""
    parts = tuple((part.content, part.size_bytes) for part in card.partitions)
    return card.size_bytes, parts


def take_new_card(env: Env, master: CardInfo) -> CardInfo:
    env.out(f"Remove the MASTER card from the reader now. {WAITING}")
    wait_for_removal(env.poll, env.sleep)
    env.out(f"Insert the NEW card. It will be erased. {WAITING}")
    card = wait_for_insert(env.poll, env.sleep)
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
    master_manifest = peek(env, master)
    env.out(id_line(master_manifest, "untagged"))
    master_id = master_manifest.card_id if master_manifest else None
    backup_into(env, master, name, master_id)
    card = take_new_card(env, master)
    source = env.images.find(name)
    check_fits(source, card.size_bytes, card.block_size_bytes)
    manifest = identify(env, card, forbidden_id=master_id)
    env.out(erase_warning(card))
    if not confirmed_erase(env, card):
        env.out(f"Not confirmed. Nothing written; the image is saved as {name}.")
        return EXIT_ERROR
    detail = f"from {master_id or 'an untagged master'} via image {name}"
    copied = manifest.with_event(event(env, "copy", detail), name)
    flash_and_restore(env, card, source, manifest, copied)
    env.out("Copy complete.")
    return EXIT_OK

#!/usr/bin/env python3
# cli — command-line entry point for the microsd tools
# Author: Pito Salas and Claude Code
# Version: 3
# Created: 2026-10-19
# Updated: 2026-10-21
# Open Source Under MIT license
"""Command-line entry point: `microsd <command>`.

Commands never take a disk argument; they find the card in the designated
reader themselves (see `reader.py`).
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from functools import partial
from typing import NoReturn

from microsd_utils.cards import run_card, run_cards
from microsd_utils.check import run_check
from microsd_utils.device import open_card
from microsd_utils.diskutil import Diskutil
from microsd_utils.images import ImageError, ImageStore, sudo_owner
from microsd_utils.imaging import run_backup, run_copy, run_flash
from microsd_utils.manifest import IdentityError, Registry
from microsd_utils.partitions import PartitionError
from microsd_utils.passes import CardDisconnected
from microsd_utils.random_io import RANDOM_SECONDS
from microsd_utils.reader import ReaderError, load_fingerprint
from microsd_utils.session import EXIT_ERROR, Env
from microsd_utils.swap import SwapError, card_poll
from microsd_utils.transfer import TransferError

EXPECTED_ERRORS = (
    ReaderError,
    ImageError,
    IdentityError,
    PartitionError,
    TransferError,
    SwapError,
    CardDisconnected,
    OSError,
    subprocess.CalledProcessError,
)


def add_command(commands, name: str, help_text: str) -> argparse.ArgumentParser:
    command = commands.add_parser(name, help=help_text)
    command.add_argument(
        "--dry-run",
        dest="is_dry_run",
        action="store_true",
        help="Print the plan; touch nothing.",
    )
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="microsd", description="Tools for the microSD card in the card reader."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = add_command(commands, "check", "Check the card for errors and wear.")
    check.add_argument(
        "--destructive",
        dest="is_destructive",
        action="store_true",
        help="Write and verify every block. WIPES THE CARD.",
    )
    backup = add_command(commands, "backup", "Save the card as images/NAME.img.gz.")
    backup.add_argument("name", help="Image name: letters, digits, '.', '_', '-'.")
    flash = add_command(commands, "flash", "Write an image to the card. ERASES IT.")
    flash.add_argument(
        "image", help="A stored image name, or an .img/.img.gz/.img.xz path."
    )
    copy = add_command(commands, "copy", "Copy a master card to a new card.")
    copy.add_argument("name", help="Name to save the master's image under.")
    add_command(commands, "card", "Show the card's ID and history; tag it if new.")
    commands.add_parser("cards", help="List every card in the registry.")
    return parser


def elevate() -> NoReturn:
    """Replace this process with the same command under sudo."""
    command = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    os.execvp("sudo", ["sudo", "-p", "Mac login password for %u: ", *command])


def real_env() -> Env:
    diskutil = Diskutil()
    fingerprint = load_fingerprint()
    owner = sudo_owner(os.environ)
    return Env(
        diskutil=diskutil,
        fingerprint=fingerprint,
        open_device=partial(open_card, diskutil, fingerprint),
        list_volume=os.listdir,
        ask=input,
        out=partial(print, flush=True),
        is_root=os.geteuid() == 0,
        elevate=elevate,
        random_seconds=RANDOM_SECONDS,
        images=ImageStore(owner=owner),
        registry=Registry(owner=owner),
        poll=card_poll(diskutil, fingerprint),
        clock=time.monotonic,
        sleep=time.sleep,
        now=datetime.now,
    )


COMMANDS = {
    "check": lambda env, args: run_check(env, args.is_destructive, args.is_dry_run),
    "backup": lambda env, args: run_backup(env, args.name, args.is_dry_run),
    "flash": lambda env, args: run_flash(env, args.image, args.is_dry_run),
    "copy": lambda env, args: run_copy(env, args.name, args.is_dry_run),
    "card": lambda env, args: run_card(env, args.is_dry_run),
    "cards": lambda env, args: run_cards(env),
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](real_env(), args)
    except EXPECTED_ERRORS as error:
        print(f"microsd: {error}", file=sys.stderr)
        return EXIT_ERROR

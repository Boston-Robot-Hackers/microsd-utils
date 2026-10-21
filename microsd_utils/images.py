#!/usr/bin/env python3
# images — the image store in the repo's images/ directory
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-20
# Open Source Under MIT license
"""Card images, kept in `images/` at the repo root (git-ignored).

A backup named `pi-robot` is stored as `pi-robot.img.gz` plus a
`pi-robot.json` sidecar recording where it came from, how many bytes of card
data it holds and their SHA-256. Flash uses the sidecar's size and hash to
check the target card fits and to verify the write.

Images are written to a `.partial` file and renamed only when complete, so a
failed backup never leaves something that looks like a good image.

The tools run as root under sudo; new files are handed back to the invoking
user (`SUDO_UID`/`SUDO_GID`) so they can be moved or deleted without sudo.

`flash` also accepts any `.img`, `.img.gz` or `.img.xz` path, such as a
Raspberry Pi OS download. Those have no sidecar, so their size and hash are
measured by decompressing once.
"""

import gzip
import hashlib
import json
import lzma
import os
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import BinaryIO

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# Level 1: Pi images are mostly empty space, and higher levels make the
# compressor, not the card, the bottleneck.
GZIP_LEVEL = 1
READ_CHUNK_BYTES = 4 * 1024 * 1024

Owner = tuple[int, int]


class ImageError(Exception):
    """An image name or file can't be used."""


@dataclass(frozen=True)
class ImageInfo:
    name: str
    source_media_name: str
    source_size_bytes: int
    data_bytes: int
    sha256: str
    created: str
    source_card_id: str | None


@dataclass(frozen=True)
class ImageSource:
    path: Path
    data_bytes: int
    sha256: str


def sudo_owner(environ: Mapping[str, str]) -> Owner | None:
    """The user who ran sudo, or None when not running under sudo."""
    if "SUDO_UID" not in environ:
        return None
    return int(environ["SUDO_UID"]), int(environ["SUDO_GID"])


def give_to_owner(
    path: Path, owner: Owner | None, chown: Callable[[Path, int, int], None]
) -> None:
    """Hand a file made as root back to the sudo user; no-op without sudo."""
    if owner is not None:
        chown(path, *owner)


IMAGE_OPENERS = {
    ".img.gz": partial(gzip.open, mode="rb"),
    ".img.xz": partial(lzma.open, mode="rb"),
    ".img": partial(Path.open, mode="rb"),
}


def require_image_suffix(path: Path) -> str:
    for suffix in IMAGE_OPENERS:
        if path.name.endswith(suffix):
            return suffix
    raise ImageError(f"{path} is not an .img, .img.gz or .img.xz file")


def open_image(path: Path) -> BinaryIO:
    """Open an image for reading, decompressing by suffix."""
    return IMAGE_OPENERS[require_image_suffix(path)](path)


def read_chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(READ_CHUNK_BYTES):
        yield chunk


def measure(path: Path) -> tuple[int, str]:
    """Data size and SHA-256 of an image, by reading it through once."""
    digest = hashlib.sha256()
    data_bytes = 0
    with open_image(path) as stream:
        for chunk in read_chunks(stream):
            digest.update(chunk)
            data_bytes += len(chunk)
    return data_bytes, digest.hexdigest()


class ImageStore:
    def __init__(
        self,
        directory: Path = IMAGES_DIR,
        owner: Owner | None = None,
        chown: Callable[[Path, int, int], None] = os.chown,
    ):
        self.directory = directory
        self.owner = owner
        self.chown = chown

    def image_path(self, name: str) -> Path:
        return self.directory / f"{name}.img.gz"

    def info_path(self, name: str) -> Path:
        return self.directory / f"{name}.json"

    def check_new_name(self, name: str) -> None:
        if not NAME_RE.fullmatch(name):
            raise ImageError(
                f"bad image name {name!r}: use letters, digits, '.', '_' and '-'"
            )
        if self.image_path(name).exists() or self.info_path(name).exists():
            raise ImageError(f"image {name!r} already exists in {self.directory}")

    def give_to_owner(self, path: Path) -> None:
        give_to_owner(path, self.owner, self.chown)

    @contextmanager
    def create(self, name: str) -> Iterator[BinaryIO]:
        """Yield a compressed stream for a new image; publish it only if the
        block completes, otherwise delete the partial file."""
        self.check_new_name(name)
        if not self.directory.exists():
            self.directory.mkdir(parents=True)
            self.give_to_owner(self.directory)
        partial = self.directory / f"{name}.img.gz.partial"
        try:
            with gzip.open(partial, "wb", compresslevel=GZIP_LEVEL) as stream:
                yield stream
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        partial.rename(self.image_path(name))
        self.give_to_owner(self.image_path(name))

    def save_info(self, info: ImageInfo) -> None:
        path = self.info_path(info.name)
        path.write_text(json.dumps(asdict(info), indent=2) + "\n")
        self.give_to_owner(path)

    def is_stored(self, name_or_path: str) -> bool:
        return bool(NAME_RE.fullmatch(name_or_path)) and (
            self.info_path(name_or_path).exists()
        )

    def locate(self, name_or_path: str) -> Path:
        """The image file for a stored name or a path, without reading it."""
        if self.is_stored(name_or_path):
            return self.image_path(name_or_path)
        path = Path(name_or_path)
        if not path.is_file():
            raise ImageError(
                f"no image named {name_or_path!r} in {self.directory}, and no such file"
            )
        require_image_suffix(path)
        return path

    def find(self, name_or_path: str) -> ImageSource:
        """A stored image by name (size and hash from its sidecar), or any
        image file by path (size and hash measured, which reads it all)."""
        path = self.locate(name_or_path)
        if self.is_stored(name_or_path):
            info = json.loads(self.info_path(name_or_path).read_text())
            return ImageSource(path, info["data_bytes"], info["sha256"])
        data_bytes, sha256 = measure(path)
        return ImageSource(path, data_bytes, sha256)

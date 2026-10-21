#!/usr/bin/env python3
# test_images — tests for the image store
# Author: Pito Salas and Claude Code
# Version: 2
# Created: 2026-10-19
# Updated: 2026-10-20
# Open Source Under MIT license

import gzip
import hashlib
import json
import lzma

import pytest

from microsd_utils.images import (
    ImageError,
    ImageInfo,
    ImageStore,
    measure,
    open_image,
    sudo_owner,
)

DATA = bytes(range(256)) * 4096


@pytest.fixture
def store(tmp_path):
    return ImageStore(tmp_path / "images")


def info_for(name, data=DATA):
    return ImageInfo(
        name=name,
        source_media_name="1081CS0",
        source_size_bytes=62599987200,
        data_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        created="2026-10-19",
        source_card_id="A1",
    )


def test_create_round_trip_and_find_by_name(store):
    with store.create("pi-robot") as stream:
        stream.write(DATA)
    store.save_info(info_for("pi-robot"))
    with open_image(store.image_path("pi-robot")) as stream:
        assert stream.read() == DATA
    source = store.find("pi-robot")
    assert source.path == store.image_path("pi-robot")
    assert source.data_bytes == len(DATA)
    assert source.sha256 == hashlib.sha256(DATA).hexdigest()
    assert json.loads(store.info_path("pi-robot").read_text())["name"] == "pi-robot"


def test_directory_created_when_missing(store):
    assert not store.directory.exists()
    with store.create("x") as stream:
        stream.write(b"x")
    assert store.directory.is_dir()


def test_failed_create_leaves_nothing(store):
    with pytest.raises(OSError), store.create("broken") as stream:
        stream.write(DATA)
        raise OSError("card read failed")
    assert list(store.directory.iterdir()) == []


@pytest.mark.parametrize("name", ["", ".hidden", "a/b", "../x", "pi robot", "-x"])
def test_bad_names_refused(store, name):
    with pytest.raises(ImageError, match="bad image name"):
        store.check_new_name(name)


def test_existing_name_refused(store):
    with store.create("pi-robot") as stream:
        stream.write(DATA)
    with pytest.raises(ImageError, match="already exists"):
        store.check_new_name("pi-robot")


def test_new_files_given_to_sudo_user(tmp_path):
    chowned = []
    store = ImageStore(
        tmp_path / "images",
        owner=(501, 20),
        chown=lambda path, uid, gid: chowned.append((path.name, uid, gid)),
    )
    with store.create("pi") as stream:
        stream.write(b"x")
    store.save_info(info_for("pi", b"x"))
    assert chowned == [
        ("images", 501, 20),
        ("pi.img.gz", 501, 20),
        ("pi.json", 501, 20),
    ]


def test_sudo_owner():
    assert sudo_owner({"SUDO_UID": "501", "SUDO_GID": "20"}) == (501, 20)
    assert sudo_owner({}) is None


@pytest.mark.parametrize(
    "suffix, compress",
    [(".img", bytes), (".img.gz", gzip.compress), (".img.xz", lzma.compress)],
)
def test_find_by_path_measures_each_format(store, tmp_path, suffix, compress):
    path = tmp_path / f"download{suffix}"
    path.write_bytes(compress(DATA))
    source = store.find(str(path))
    assert source.data_bytes == len(DATA)
    assert source.sha256 == hashlib.sha256(DATA).hexdigest()
    assert measure(path) == (source.data_bytes, source.sha256)


def test_unknown_suffix_refused(tmp_path):
    path = tmp_path / "card.zip"
    path.write_bytes(b"x")
    with pytest.raises(ImageError, match="not an .img"):
        open_image(path)


def test_missing_image_refused(store):
    with pytest.raises(ImageError, match="no image named"):
        store.find("nothing-here")

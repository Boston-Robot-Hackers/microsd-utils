---
version: "1.1"
generated: "2026-10-20"
---

# images — the image store

## What lives where

Backups are kept in `images/` at the repo root (git-ignored). A backup named `pi-robot` is two files:

- **`pi-robot.img.gz`** — the card's bytes up to the end of its last partition, gzip-compressed.
- **`pi-robot.json`** — a *sidecar* describing it:

```json
{
  "name": "pi-robot",
  "source_media_name": "1081CS0",
  "source_size_bytes": 62599987200,
  "data_bytes": 4295229440,
  "sha256": "…",
  "created": "2026-10-19"
}
```

The sidecar is what makes flashing safe and fast: `data_bytes` tells flash whether the image fits a card *before* writing anything, and `sha256` is what both the write and the read-back are checked against.

## Names are validated at the boundary

An image name ends up in a filesystem path, so it's checked once, strictly:

```python
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
```

No slashes (so no `../` escapes), no leading dot or dash (no hidden files, nothing that looks like an option). An existing name is refused rather than overwritten — a backup is often the only copy of a working system.

## Atomic publish

A 60 GB backup can fail at minute 10. The store must never leave behind a file that *looks* like a good image:

```python
@contextmanager
def create(self, name):
    partial = self.directory / f"{name}.img.gz.partial"
    try:
        with gzip.open(partial, "wb", compresslevel=GZIP_LEVEL) as stream:
            yield stream
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(self.image_path(name))
```

This is the classic **write-then-rename** pattern. `rename` within one directory is atomic on POSIX filesystems, so the final name appears only when the file is complete. Catching `BaseException` (and re-raising) means Ctrl-C also cleans up.

## Ownership under sudo

The tools run as root, so every file they create would be owned by root and undeletable without `sudo`. `sudo` exports the invoking user's IDs as `SUDO_UID` and `SUDO_GID`; the store hands each new file and the directory back to that user. The `chown` call is injected so tests can check it without being root.

The hand-back itself is a module-level `give_to_owner(path, owner, chown)`, so the card registry (`16-manifest.md`) shares it instead of keeping a copy. The sidecar also records **`source_card_id`** — the label ID of the card that was backed up, or `null` for an untagged card. Old sidecars without the field still load, since `find` only reads `data_bytes` and `sha256`.

## Three formats in, one format out

Backups are always written as `.img.gz`. Flash accepts more, because Raspberry Pi OS is distributed as `.img.xz`:

```python
IMAGE_OPENERS = {
    ".img.gz": partial(gzip.open, mode="rb"),
    ".img.xz": partial(lzma.open, mode="rb"),
    ".img": partial(Path.open, mode="rb"),
}
```

A downloaded image has no sidecar, so `find` **measures** it: one full decompression to count its bytes and hash them. `locate` does only the cheap checks (exists, known suffix), which is what the unprivileged plan step uses — so the user isn't made to wait for a decompression twice, before and after the password prompt.

### Why gzip level 1

Compression runs in the same thread as the card read. At gzip's default level 6, Python compresses at roughly the speed of the card or slower, so the compressor becomes the bottleneck. Level 1 is several times faster, and a Pi card image — mostly empty filesystem space — compresses well at any level. (To be confirmed by the TF02.9 measurements.)

## Observations and possible improvements

1. **Sidecar trust.** A stored image is trusted to match its sidecar until flash checks the hash *during* the write. A `microsd verify-image NAME` command could check an image at rest.
2. **Listing images.** There's no `microsd images` command yet; `ls images/` works, but a listing with sizes, sources and dates from the sidecars would be friendlier.
3. **Parallel compression.** If gzip does turn out to be the bottleneck, compressing in a second thread (or using `zstd` via a dependency) would decouple it from the card read.

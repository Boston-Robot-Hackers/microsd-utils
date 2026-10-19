---
version: "1.1"
generated: "2026-10-19"
---

# device — the single doorway to the raw card

## The rule this module enforces

Exactly one function in the project opens a device node: `open_card`. Its body is two lines, and the order of those lines is the whole point:

```python
def open_card(diskutil, fingerprint, card, is_writable) -> RawDevice:
    recheck(diskutil, fingerprint, card)
    return RawDevice(card.raw_device, is_writable)
```

**Re-check, then open.** There is no other path to a file descriptor on `/dev/rdiskN`, so no caller can forget the safety check. This is a *chokepoint* design: concentrate a dangerous capability behind one small, auditable function.

## `RawDevice`: positioned I/O

`RawDevice` wraps a raw file descriptor and offers exactly two operations, both **positioned**:

```python
def read_at(self, offset: int, length: int) -> bytes:
    return os.pread(self.fd, length, offset)


def write_at(self, offset: int, data: bytes) -> None:
    written = os.pwrite(self.fd, data, offset)
    if written != len(data):
        raise OSError(...)
```

Why `pread`/`pwrite` instead of `seek` + `read`?

- **No shared file position.** Each call carries its own offset, so there is no hidden cursor state to get out of sync after an error.
- **Error recovery is trivial.** When a chunk fails, the next call simply asks for the next offset — no re-seeking.
- **One syscall per chunk** instead of two.

A **short write** is promoted to an `OSError`. On a raw device it means the card stopped accepting data part-way, which the write pass should count as a failed chunk — not silently ignore.

## Raw devices on macOS

The card is opened as `/dev/rdiskN` — the *character* device — rather than `/dev/diskN`, the *block* device:

| | `/dev/diskN` | `/dev/rdiskN` |
|---|---|---|
| Buffer cache | yes | no |
| Large sequential I/O | slower | close to hardware speed |
| Reads reflect the card | may be served from cache | always from the card |

Bypassing the cache matters twice over for a health check: it is faster, and a verify pass genuinely reads back from the card rather than from RAM. Raw access requires root, which is why the tool re-runs itself under `sudo`.

Writes need the volume unmounted first (`diskutil unmountDisk`), or `open(O_RDWR)` fails with "resource busy". Reads work while mounted — confirmed on the real card on 2026-10-18.

## Context management

`RawDevice` implements `__enter__`/`__exit__`, so callers write:

```python
with env.open_device(card, False) as device:
    read = read_pass(device.read_at, ...)
```

The descriptor is closed even if a pass raises. The passes themselves only ever see the bound methods `device.read_at` / `device.write_at`, never the descriptor.

## Observations and possible improvements

1. **Exclusive open.** Opening with `O_EXLOCK` (macOS) would stop another process from writing the card during a stress test, and surface a clear error if one already is.
2. **Alignment is assumed, not checked.** Raw devices require offsets and lengths that are multiples of the block size (512 here). The 4 MiB chunk size guarantees it, but `read_at`/`write_at` could assert it to protect future callers.
3. **`RawDevice` is constructible directly.** The chokepoint is a convention: nothing prevents `RawDevice("/dev/rdisk0", True)`. Making the constructor private to the module (or taking a `CardInfo` that `open_card` stamps) would turn the convention into a rule.

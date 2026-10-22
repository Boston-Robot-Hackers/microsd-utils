# F06 — Verify a card against an image

**Priority**: High

**Date Created:** 2026-10-21

**Done:** yes

**Tasks File Created:** yes

**Tests Written:** yes

**Test Passing:** yes

**Description**: A read-only `microsd verify IMAGE` (`make verify
IMAGE=<name or path>`) that checks the card in the reader holds an image, and
says where it doesn't.

### Why

On 2026-10-21 a flash of `dome-2-master` onto R2 wrote 100%, then the reader
reset at 50% of verify. Checking R2 afterwards took a hand-typed `dd | head |
shasum` pipeline, and its mismatch proved nothing: macOS had mounted R2's
`bootfs` after the reset, and any mount changes a few bytes there. One hash
can't tell "macOS touched bootfs" from "the flash is bad". The only way out
was a 35-minute re-flash.

### Scope

- **`verify IMAGE`**: find the card by the reader fingerprint, show its ID,
  unmount it, open it **read-only**, and compare it chunk by chunk with the
  image (a stored name or any `.img`/`.img.gz`/`.img.xz` path) up to the
  image's length. Report `Verified: OK`, or how many 4 MiB chunks differ and
  where.

- **Where the differences are**: map each differing chunk to a partition of
  the image's own partition table. If every difference is inside a FAT
  partition, say so: that is what a macOS mount does, not a bad flash.

- **Flash uses the same comparison** for its read-back, so a failed flash
  also says where the card differs, instead of only "doesn't hold the image".

- **Flash gaps found on 2026-10-21**, folded in:
  - a failed flash is recorded in the card's registry history
    (`flash failed: <error>`), as stress already does;
  - a reader that drops mid-flash or mid-verify reports "card disconnected"
    (F05's check) instead of a raw `[Errno 6] Device not configured`.

### Decisions

- **Compare bytes, not one hash.** Hashing the whole card gives a yes/no;
  comparing chunk by chunk against the decompressed image gives the
  offsets. Decompressing on the fly (~200+ MB/s) is faster than the card
  (~70 MB/s), so it costs no time.

- **Verify never writes the card.** It unmounts it (so macOS can't change it
  mid-read) and opens it `O_RDONLY`; it doesn't write a manifest or history
  entry to the card. Same safety as `backup`.

- **No registry entry for verify.** It changes nothing on the card, and a new
  event kind would change the manifest format. It can be added later.

- **Exit code**: 0 when verified, 1 when the card differs or can't be read.

## How to Demo

**Setup**: R2 in the reader, as left after the interrupted flash (fully
written, `bootfs` since mounted by macOS); `images/dome-2-master.img.gz`.

**Steps**:
1. `make verify IMAGE=dome-2-master`
2. `make flash IMAGE=dome-2-master` (re-flash R2)
3. `make verify IMAGE=dome-2-master` again

**Expected output**: step 1 either says `Verified: OK` or lists the
differing chunks and whether they all fall in the FAT boot partition; step 2
ends `Verified: OK`; step 3 says `Verified: OK` (or only `bootfs`
differences, if macOS mounted the card in between).

## Process Gate

After creating this feature file and the corresponding task file, **stop and present the plan to the user**. Do not write any code or content until the user gives explicit approval to proceed.

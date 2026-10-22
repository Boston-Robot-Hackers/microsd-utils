# Notes

Durable architecture notes for microsd-utils.

## Card reader (measured 2026-10-18)

- **Reader**: USB NORELSYS 1081CS0 on port `usb-drd2-port-ss@02200000`
  (SuperSpeed). Fingerprint in `sd_reader.json`.

- **No wear data**: `diskutil info` reports `SMARTStatus: Not Supported` and an
  empty SMART dictionary. The verdict can only use errors, speed and layout.

- **Raw reads work while mounted**: `/dev/rdisk4` opened read-only as root
  with the FAT boot partition mounted; no unmount needed for `validate`.

## Throughput

| Date | Card | Mode | Size | Time | Speed | Result |
|---|---|---|---|---|---|---|
| 2026-10-18 | 64 GB, Pi system (2 partitions) | read-only | 62.6 GB | 893 s | 70.1 MB/s | 0 bad chunks, STILL OK |
| 2026-10-18 | same card | stress: write | 62.6 GB | 1160 s | 54.0 MB/s | 0 bad chunks |
| 2026-10-18 | same card | stress: verify | 62.6 GB | 870 s | 72.0 MB/s | 0 bad chunks, STILL OK |
| 2026-10-21 | same card (R2) | stress: write | 62.6 GB | 1046 s | 59.9 MB/s | 0 bad chunks |
| 2026-10-21 | same card (R2) | stress: verify | 62.6 GB | 879 s | 71.2 MB/s | 0 bad chunks, FAIR (random) |

- **~70 MB/s is near the ceiling**: `iostat` showed 17–18 requests/s of 4 MiB
  each during the run. UHS-I cards and readers top out around 90–100 MB/s, so
  the read pass is hardware-bound; expect ~15 min per 64 GB.
- **Stress takes ~35 min per 64 GB** on this card: writes are slower than
  reads (54 vs 72 MB/s). Full advertised capacity verified, so not a fake.
- **After stress the card holds only test pattern**: no partition table, so
  macOS may say the disk is unreadable. Reformat it before reuse.

## Backup (measured 2026-10-21)

| Date | Card | Data | Time | Speed | Image |
|---|---|---|---|---|---|
| 2026-10-21 | dome-2-master, 64 GB Pi system card (untagged) | 62.6 GB | 1032 s | 60.7 MB/s | 12.1 GB `.img.gz` |

- **The rootfs fills the card.** Pi OS expands its root partition on first
  boot, so "up to the end of the last partition" is 62,599,970,304 of
  62,599,987,200 bytes: the whole card. Flashing it needs a target at least
  that big.

- **gzip costs ~15%.** 60.7 MB/s against ~70–72 MB/s raw reads through the
  same reader: about 2.5 min on a 17-min backup. Keeping `.img.gz`; a plain
  `.img` would take 62.6 GB of disk instead of 12.1 GB.

## Flash (measured 2026-10-21)

| Date | Card | Image | Write | Verify | Result |
|---|---|---|---|---|---|
| 2026-10-21 | R2 | dome-2-master | 1011 s, 61.9 MB/s | 813 s, 77.0 MB/s | Verified OK, manifest written, ejected |
| 2026-10-22 | R4 (via `make copy` from R1) | dome-2-copy2 | 1048 s, 59.7 MB/s | 845 s, 74.0 MB/s | Verified OK, manifest written, ejected |

- **`copy` swap works with this reader**: pulling the master makes the disk
  vanish from `diskutil`, and the new card shows up as `disk4` again. A full
  copy of a 64 GB card takes ~49 min (17 backup + 17 flash + 14 verify),
  plus the swap.

- **First attempt failed at 50% of verify**: the reader dropped off USB at
  18:21:39 and again at 18:22:06 (`log show`: "SS usb device removed from
  the root hub port <0>", re-attached within ms) with the Mac awake and
  `caffeinate` held. macOS reported it as `[Errno 6] Device not configured`
  (ENXIO). A read of the whole card right after, and the re-flash, ran
  clean, so it looks like a one-off reader/link glitch.

- **macOS sees the new partitions after a raw flash** without reinsertion:
  `mountDisk` then `Manifest written: R2` (F04 assumption confirmed).

- **A hash of the card after a reader reset proves nothing**: macOS
  auto-mounted `bootfs` when the reader came back, which changes it. This is
  why F06 (`make verify`) compares chunk by chunk and names the partition.

## Verify (measured 2026-10-21)

| Date | Card | Image | Time | Speed | Result |
|---|---|---|---|---|---|
| 2026-10-21 | R2, after flash + `make card` writes | dome-2-master | 838 s | 74.7 MB/s | 8 of 14,925 chunks differ: 1 "partition table", 7 FAT32 |
| 2026-10-22 | same, after the labelling fix | dome-2-master | 835 s | 75.0 MB/s | 9 chunks differ, all FAT32; FAT-only note shown; Linux root matches |

- **Pi images don't start `bootfs` on a chunk boundary.** `dome-2-master`'s
  FAT32 partition starts at sector 2048 (1 MiB) and its Linux root at
  513 MiB, so chunk 0 holds the MBR *and* the FAT boot sector and tables.
  The first `verify` labelled chunks by where they start, so that chunk
  read as "partition table" and hid the FAT-only note. Fixed the same day:
  each differing chunk is now labelled by its first and last differing byte.

## Random 4 KB I/O (measured 2026-10-21)

| Date | Card | Read IOPS | Write IOPS | Grade |
|---|---|---|---|---|
| 2026-10-21 | R2, 64 GB, via NORELSYS reader | 1,499 | 980 | FAIR (read 1 short of A1) |

- **Python is not the cap.** The `timed_random_pass` loop alone runs at
  0.2 µs per op (no-op), 0.4 µs with a 4 KB copy, 0.7 µs with two
  syscalls. At 1,500 IOPS each op takes 667 µs, so the loop adds ~0.1%.
  The measured rate is the card plus the USB reader.

- **Queue depth 1 through USB.** One 4 KB request at a time, each a full
  USB mass-storage round trip. A card's A1 rating is measured in an SD
  host, so a reader may read a little below the rated IOPS (unverified:
  no native SD slot to compare).

- **`iostat` agrees with the tool.** `iostat -d -w 1 disk4` during two
  `make validate` random-read phases (both stopped with Ctrl-C before the
  sequential pass) showed 4.00 KB/t at ~1,500 tps, the same as the 1,499
  IOPS the tool reported in stress.

- **Cold start is slower.** First run: ~1,395 tps for 8 s, then ~1,510
  (mean ~1,475). Second run, started warm right after: steady ~1,505.

- **R2 sits on the A1 line.** Run-to-run spread is about ±2% around 1,500,
  so the 1,500 cutoff flips this card between GOOD and FAIR on noise.

- **Recalibrated toward GOOD** (TF03.6): within 5% of an A-class counts
  as meeting it (`READER_MARGIN`, A1 read ≥ 1,425), and the first 20% of
  each 30 s pass is uncounted warm-up (`WARMUP_SHARE`). R2 now grades GOOD.

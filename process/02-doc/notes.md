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

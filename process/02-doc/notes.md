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

- **~70 MB/s is near the ceiling**: `iostat` showed 17–18 requests/s of 4 MiB
  each during the run. UHS-I cards and readers top out around 90–100 MB/s, so
  the read pass is hardware-bound; expect ~15 min per 64 GB.
- **Stress takes ~35 min per 64 GB** on this card: writes are slower than
  reads (54 vs 72 MB/s). Full advertised capacity verified, so not a fake.
- **After stress the card holds only test pattern**: no partition table, so
  macOS may say the disk is unreadable. Reformat it before reuse.

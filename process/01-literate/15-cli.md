---
version: "2.2"
generated: "2026-10-21"
---

# cli — the `microsd` command

## Role

`cli.py` is the *composition root*: the one place where real implementations are chosen and wired together. It does three things:

1. **Parse arguments** into a subcommand and its options.
2. **Build the real `Env`** (`12-session.md`).
3. **Dispatch** to the command, translating expected failures into exit code 1.

## The command surface

```
microsd check  [--destructive] [--dry-run]
microsd backup NAME            [--dry-run]
microsd flash  IMAGE           [--dry-run]
microsd copy   NAME            [--dry-run]
microsd card                   [--dry-run]
microsd cards
```

`card` and `cards` (see `18-cards.md`) never open the raw device, so they don't re-run under sudo. `cards` takes no `--dry-run` because it never writes.

**No command takes a disk.** The card is always found by the reader fingerprint; accepting a disk argument would reintroduce exactly the risk the fingerprint removes. `--dry-run` is added to every subcommand by one helper, `add_command`, so it can't be forgotten on a new one. Flags map to boolean names (`dest="is_dry_run"`).

Users normally go through the Makefile (`make validate`, `make backup NAME=…`), which calls the venv's script directly; under `sudo`, `uv run` would leave root-owned files in `.venv`.

## Dispatch as data

```python
COMMANDS = {
    "check": lambda env, args: run_check(env, args.is_destructive, args.is_dry_run),
    "backup": lambda env, args: run_backup(env, args.name, args.is_dry_run),
    "flash": lambda env, args: run_flash(env, args.image, args.is_dry_run),
    "copy": lambda env, args: run_copy(env, args.name, args.is_dry_run),
}
```

A lookup table instead of an `if` chain: each entry adapts `argparse`'s namespace to the command's explicit signature, so the command functions never see `args`. The lambdas look up `run_check` etc. at call time, which is what lets tests monkeypatch them.

## Building the environment

```python
return Env(
    diskutil=diskutil,
    fingerprint=fingerprint,
    open_device=partial(open_card, diskutil, fingerprint),
    ...
    images=ImageStore(owner=sudo_owner(os.environ)),
    poll=card_poll(diskutil, fingerprint),
    clock=time.monotonic,
    sleep=time.sleep,
)
```

`functools.partial` curries `open_card` so commands open a device without knowing that a fingerprint re-check happens inside. The image store learns the invoking user from `SUDO_UID`/`SUDO_GID` so new images aren't left owned by root.

## Re-running under sudo

```python
def elevate() -> NoReturn:
    command = [os.path.abspath(sys.argv[0]), *sys.argv[1:]]
    os.execvp("sudo", ["sudo", "-p", "Mac login password for %u: ", *command])
```

- `execvp` **replaces** the process — one process, one exit code — hence `NoReturn`.
- An absolute path makes the re-run independent of `PATH` and sudo's `secure_path`.
- `-p` names the password being asked for; sudo's default `Password:` doesn't.

## The error boundary

```python
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
```

Each module raises its own exception type for failures a user can act on — no card, bad image name, corrupt partition table, verification failed, swap timed out, card disconnected mid-pass. A `diskutil` command that times out raises `DiskutilTimeout`, an `OSError`, so it needs no entry of its own. These become a one-line `microsd: …` message and exit code 1. Anything else is a bug and keeps its full traceback.

## Observations and possible improvements

1. **`--version`** from package metadata would help when comparing reports.
2. **Exit codes in `--help`.** They're documented in the README only; an `epilog` would put them where script authors look.
3. **An `images` subcommand** to list stored images from their sidecars would round out the backup/flash workflow.

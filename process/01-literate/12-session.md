---
version: "1.2"
generated: "2026-10-22"
---

# session — what every command shares

## Why it exists

With one command (`check`), its helpers lived in `check.py`. When `backup`, `flash` and `copy` arrived, four commands needed the same things: the injected environment, the "explain, then re-run under sudo" step, the erase warning and its confirmation, and progress printing. `session.py` is where they moved, so each exists exactly once.

## `Env`: every side effect in one place

```python
@dataclass
class Env:
    diskutil: DiskutilCommands
    fingerprint: Fingerprint
    open_device: Callable[[CardInfo, bool], object]
    list_volume: Callable[[str], list[str]]
    ask: Callable[[str], str]
    out: Callable[..., None]
    is_root: bool
    elevate: Callable[[], int]
    random_seconds: float
    images: ImageStore
    registry: Registry
    poll: Poll
    sleep: Callable[[float], None]
    now: Callable[[], datetime]
```

Two fields came with card identity: **`registry`**, the repo's list of known cards, and **`now`**, the wall clock used to timestamp history entries; injecting it makes history entries exact in tests. There is no monotonic `clock` any more: it existed only for the card-swap timeout, which was removed on 2026-10-22 (see `11-swap.md`). `sleep` remains, so the swap polling runs instantly in tests.

Production builds one in `cli.real_env()`; tests build one in `tests/fakes.make_test_env()` with recording fakes. Because *every* interaction with the world goes through these fields, the tests can assert negatives — "nothing was opened", "nothing was unmounted" — that would otherwise need real hardware to check.

`DiskutilCommands` is a `Protocol` extending `reader.DiskutilQueries` with the state-changing calls: `unmount_disk`, `eject`, and for card identity `mount_disk`, `mount` and `erase_fat32`. Discovery only needs the queries; only commands get the power to change state.

## `preflight`: the gate before any device

```python
def preflight(env, plan, is_dry_run) -> int | None:
    env.out(plan)
    if is_dry_run:
        env.out("Dry run: nothing touched.")
        return EXIT_OK
    if not env.is_root:
        env.out(SUDO_NOTE)
        return env.elevate()
    return None
```

Every command calls this after discovery and before touching a device. It encodes one rule: **the user always sees the plan before anything happens** — before a dry run ends, and before a password prompt. Returning `None` means "carry on, you're root"; any integer is the exit code to return immediately.

## The erase confirmation

Anything that overwrites a card — `check --destructive`, `flash`, the second half of `copy` — shows the same banner and asks two separate questions:

```python
if env.ask("ARE YOU SURE you want to ERASE this card? Type yes: ").strip() != "yes":
    return False
answer = env.ask(f"Type {card.identifier} to confirm which card to erase: ")
return answer.strip() == card.identifier
```

Two prompts defend against two different mistakes:

- **"yes"** defends against *reflex* — Enter or `y` typed without reading.
- **The identifier** defends against *the wrong card* — the user must look at the line that names it.

`is_yes` is the lighter `y/N` used for low-stakes questions (tagging a card, saving a description); erasing never uses it.

## Progress

`progress_printer` returns a closure that redraws one line with `\r` only when the integer percentage changes — about 100 writes per pass regardless of card size.

## Observations and possible improvements

1. **`Env` is growing.** Thirteen fields is fine for a composition root, but `check` doesn't use `images`/`poll`, and `backup` doesn't use `random_seconds`. If a fifth command arrives, splitting per-command environments may read better.
2. **`open_device` returns `object`.** A `Protocol` for the device (`read_at`, `write_at`, context manager) would let a type checker verify fakes match `RawDevice`.
3. **Prompts aren't localised or scriptable.** Fine for a single-user tool; a `--yes-i-mean-disk4` style flag for automation would need careful design and isn't in scope.

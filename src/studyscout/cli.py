"""CLI entry — launch the TUI, or headless commands.

  studyscout                    launch the TUI
  studyscout search             headless ClinicalTrials.gov refresh
  studyscout doctor             pre-flight diagnostic (profile, key, API, db)
        --offline                 skip the network probe
        --ping                    add one tiny paid AI call to verify the key
  studyscout backup [dest]      roll profile + site.md + db into one tar.gz
  studyscout restore <tar.gz>   put a backup back (snapshots current state first)
        --yes                     skip the confirmation prompt
  studyscout where              print config + data paths
  studyscout version
"""
from __future__ import annotations

import asyncio
import sys

from . import __version__


def _search() -> int:
    from .engine import Engine
    eng = Engine()
    total, new, errs = asyncio.run(eng.refresh(lambda s, m, n: print(f"  [{s}] {m}" + (f" ({n})" if n is not None else ""))))
    print(f"\n{total} studies · {new} new")
    for e in errs:
        print("  -", e)
    return 0


def _doctor(argv) -> int:
    from .doctor import FAIL, render, run_doctor
    rep = asyncio.run(run_doctor(offline="--offline" in argv, ping="--ping" in argv))
    print(render(rep, color=sys.stdout.isatty()))
    return 1 if rep.worst == FAIL else 0


def _backup(argv) -> int:
    from .backup import backup
    out = backup(argv[0] if argv else None)
    print(f"black box written: {out}  ({out.stat().st_size // 1024} KB)")
    print("contains your API keys — keep it private (already chmod 600).")
    return 0


def _restore(argv) -> int:
    from .backup import peek, restore
    args = [a for a in argv if a != "--yes"]
    if not args:
        print("usage: studyscout restore <backup.tar.gz> [--yes]")
        return 2
    try:
        names = peek(args[0])
    except Exception as exc:  # noqa: BLE001
        print(f"refusing: {exc}")
        return 1
    print(f"{args[0]}: {len(names)} entries (config + data).")
    if "--yes" not in argv:
        try:
            answer = input("overwrite the live rig with this backup? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("aborted — nothing touched.")
            return 1
    src, snap = restore(args[0])
    if snap:
        print(f"pre-restore snapshot: {snap}")
    print(f"restored from {src}. Run `studyscout doctor` to verify.")
    return 0


def _where() -> int:
    from .config import Config, data_dir
    cfg = Config()
    print("profile :", cfg.path)
    print("site.md :", cfg.me_path())
    print("data    :", data_dir())
    print("AI key  :", "set" if cfg.api_key() else "NOT set")
    return 0


def main(argv=None) -> int:
    from .childenv import scrub_environ
    scrub_environ()            # frozen binary: don't leak bundled libs into the browser
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "tui"
    if cmd in ("-h", "--help", "help"):
        print(__doc__); return 0
    if cmd in ("-v", "--version", "version"):
        print(f"StudyScout {__version__}"); return 0
    if cmd == "search":
        return _search()
    if cmd == "doctor":
        return _doctor(argv[1:])
    if cmd == "backup":
        return _backup(argv[1:])
    if cmd == "restore":
        return _restore(argv[1:])
    if cmd == "where":
        return _where()
    from .tui import StudyScoutApp
    StudyScoutApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Backup & restore — the pipeline's black box.

`studyscout backup [dest]` rolls the whole rig — profile.toml, site.md, and
the database (studies, BD pipeline, sponsor notes, outreach history, deltas,
reg checklists) — into one tarball. `studyscout restore <tarball>` puts it
back, snapshotting the current state first so a restore is itself revertible.

The tarball contains your API keys in plaintext (they live in profile.toml).
It is written 0600; treat it like a key.
"""

from __future__ import annotations

import os
import tarfile
import time
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

from .config import APP


def _roots() -> tuple[Path, Path]:
    """(config root, data root) honoring the env overrides."""
    cfg_env = os.environ.get("STUDYSCOUT_PROFILE")
    cfg_root = Path(cfg_env).expanduser().parent if cfg_env else Path(user_config_dir(APP))
    data_root = Path(os.environ.get("STUDYSCOUT_DATA", user_data_dir(APP)))
    return cfg_root, data_root


def backup(dest: str | Path | None = None) -> Path:
    """Write config+data to a timestamped tar.gz. Returns the tarball path."""
    cfg_root, data_root = _roots()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(dest).expanduser() if dest else Path.home() / f"studyscout-backup-{stamp}.tar.gz"
    if out.is_dir():
        out = out / f"studyscout-backup-{stamp}.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)

    def _skip_caches(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        name = Path(info.name).name
        if name == "__pycache__" or name.endswith((".pyc", ".db-journal", ".db-wal", ".db-shm")):
            return None
        return info

    with tarfile.open(out, "w:gz") as tar:
        if cfg_root.exists():
            tar.add(cfg_root, arcname="config", filter=_skip_caches)
        if data_root.exists():
            tar.add(data_root, arcname="data", filter=_skip_caches)
    try:
        out.chmod(0o600)
    except OSError:
        pass
    return out


def peek(tarball: str | Path) -> list[str]:
    """Member names inside a backup (validated safe) — for the restore preview."""
    with tarfile.open(tarball, "r:gz") as tar:
        names = tar.getnames()
    for n in names:
        p = Path(n)
        if p.is_absolute() or ".." in p.parts or p.parts[0] not in ("config", "data"):
            raise ValueError(f"unsafe member in tarball: {n!r} — refusing")
    return names


def restore(tarball: str | Path, snapshot: bool = True) -> tuple[Path, Path | None]:
    """Extract a backup over the live roots.

    Returns (restored-from, pre-restore snapshot path). Existing files are
    overwritten member-by-member; files that exist only locally are kept.
    """
    tarball = Path(tarball).expanduser()
    peek(tarball)  # validate before touching anything
    cfg_root, data_root = _roots()

    snap = None
    if snapshot and (cfg_root.exists() or data_root.exists()):
        snap = backup(tarball.parent / f"pre-restore-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz")

    cfg_root.parent.mkdir(parents=True, exist_ok=True)
    data_root.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            root = cfg_root if parts[0] == "config" else data_root
            member.name = str(Path(*parts[1:]) if len(parts) > 1 else Path("."))
            tar.extract(member, root, filter="data")
    return tarball, snap

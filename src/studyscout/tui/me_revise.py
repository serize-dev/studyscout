"""Helpers for the 'Wintermute revises me.md' flow: render a diff for confirm."""

from __future__ import annotations

import difflib

from rich.text import Text


def diff_text(old: str, new: str) -> Text:
    """A compact colored unified diff of the me.md change."""
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    t = Text()
    t.append("Wintermute proposes this update to your me.md:\n\n", style="#ffb000")
    any_change = False
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=2):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("@@"):
            t.append(line + "\n", style="#1f9e46")
        elif line.startswith("+"):
            t.append(line + "\n", style="#33ff88"); any_change = True
        elif line.startswith("-"):
            t.append(line + "\n", style="#ff6b6b"); any_change = True
        else:
            t.append(line + "\n", style="#2bbf5a")
    if not any_change:
        t.append("(no changes)\n", style="#1f9e46")
    return t

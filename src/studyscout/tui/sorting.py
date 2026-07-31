"""Robust sorting: named sort specs for studies and sponsors + a picker modal.

The whole universe fits in memory (this isn't a genomics db), so every sort is
instant, stable, and reversible. Press `s`, pick a field; pick the same field
again to flip direction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..models import KANBAN_ORDER

_DATE_MIN = date(1900, 1, 1)
_DT_MIN = datetime(1900, 1, 1)


def _phase_rank(study) -> float:
    """Highest numeric phase; EARLY_PHASE1 counts as 0.5, N/A as -1."""
    best = -1.0
    for p in study.phases:
        if "EARLY" in p:
            best = max(best, 0.5)
        else:
            digits = "".join(ch for ch in p if ch.isdigit())
            if digits:
                best = max(best, float(digits[0]))
    return best


_STATUS_RANK = {  # live demand first
    "RECRUITING": 0, "NOT_YET_RECRUITING": 1, "ENROLLING_BY_INVITATION": 2,
    "ACTIVE_NOT_RECRUITING": 3, "SUSPENDED": 4, "COMPLETED": 5,
    "TERMINATED": 6, "WITHDRAWN": 7,
}


@dataclass(frozen=True)
class SortSpec:
    key: str                       # short id shown in the status bar
    label: str                     # human line in the picker
    fn: Callable                   # row -> sort value
    reverse: bool = False          # natural direction ("best first")


# rows are (Study, Stage, notes) tuples
STUDY_SORTS: list[SortSpec] = [
    SortSpec("start", "start date — newest study first",
             lambda r: r[0].start or _DATE_MIN, True),
    SortSpec("status", "status — recruiting first",
             lambda r: _STATUS_RANK.get(r[0].status, 9)),
    SortSpec("phase", "phase — latest phase first", lambda r: _phase_rank(r[0]), True),
    SortSpec("enrollment", "enrollment — biggest n first",
             lambda r: r[0].enrollment or 0, True),
    SortSpec("sites", "site count — multi-site first", lambda r: r[0].n_sites, True),
    SortSpec("contact", "direct contact — reachable first",
             lambda r: r[0].has_contact, True),
    SortSpec("sponsor", "sponsor — A→Z, industry first",
             lambda r: (r[0].sponsor_class != "INDUSTRY", (r[0].sponsor or "~").lower())),
    SortSpec("stage", "pipeline stage — furthest along first",
             lambda r: KANBAN_ORDER.index(r[1]) if r[1] in KANBAN_ORDER else 99, True),
    SortSpec("title", "title — A→Z", lambda r: r[0].title.lower()),
]

# rows are SponsorDossier objects
SPONSOR_SORTS: list[SortSpec] = [
    SortSpec("bd", "BD value — industry · recruiting · reachable",
             lambda d: d.bd_key, True),
    SortSpec("trials", "trials in your net — most first", lambda d: d.n_trials, True),
    SortSpec("recruiting", "recruiting now — most first", lambda d: d.recruiting, True),
    SortSpec("pipeline", "your pipeline — most in play first", lambda d: d.in_pipeline, True),
    SortSpec("touch", "last touch — most recently worked first",
             lambda d: d.last_touch or _DT_MIN, True),
    SortSpec("fresh", "newest activity — latest study start first",
             lambda d: d.newest_start or _DATE_MIN, True),
    SortSpec("name", "sponsor name — A→Z", lambda d: d.name.lower()),
]


def apply_sort(rows: list, specs: list[SortSpec], key: str, flipped: bool) -> list:
    spec = next((s for s in specs if s.key == key), specs[0])
    return sorted(rows, key=spec.fn, reverse=spec.reverse ^ flipped)


def sort_arrow(specs: list[SortSpec], key: str, flipped: bool) -> str:
    spec = next((s for s in specs if s.key == key), specs[0])
    return "↓" if (spec.reverse ^ flipped) else "↑"


class SortModal(ModalScreen):
    """Pick a sort field (1-9). Picking the current field flips direction.

    dismiss() → (key, flipped) or None on escape.
    """

    BINDINGS = [("escape,q,s", "cancel", "close")]

    def __init__(self, specs: list[SortSpec], current: str, flipped: bool):
        super().__init__()
        self._specs = specs
        self._current = current
        self._flipped = flipped

    def compose(self) -> ComposeResult:
        t = Text()
        for i, sp in enumerate(self._specs, start=1):
            on = sp.key == self._current
            arrow = sort_arrow(self._specs, sp.key, self._flipped) if on else " "
            style = "bold #ffb000" if on else "#33ff66"
            t.append(f"  {i}  ", style="bold #00ff88")
            t.append(f"{sp.label} {arrow}\n", style=style)
        with Vertical(id="modal-box", classes="modal"):
            yield Static(Text.from_markup("[#ffb000 b]SORT BY[/]  [dim](same field again flips direction)[/]"),
                         classes="modal-title")
            yield Static(t, classes="modal-help")
            yield Static(Text.from_markup("[dim]1-9 pick · esc close[/]"), classes="modal-help")

    def on_key(self, event) -> None:
        if event.key and event.key.isdigit():
            i = int(event.key) - 1
            if 0 <= i < len(self._specs):
                sp = self._specs[i]
                flipped = (not self._flipped) if sp.key == self._current else False
                self.dismiss((sp.key, flipped))
                event.stop()

    def action_cancel(self) -> None:
        self.dismiss(None)

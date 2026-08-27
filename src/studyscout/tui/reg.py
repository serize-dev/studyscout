"""Regulatory handoff — the paperwork gauntlet after a study is won.

Press R on a study: a checklist grouped into PHASES (seeded from
`regulatory.phases` in the profile — edit it to match your site's SOP) you
work through with j/k + space. `-` marks an item N/A (doesn't apply to this
study), `a` adds an ad-hoc item, `e` notes an item, `d` drops an ad-hoc one,
`p` prints. State persists per study; the REGULATORY board (G) places the
study by what's still open; the briefing nags open items.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from .. import regulatory as reg
from ..models import Study
from .modals import NotesModal


def checklist_text(study: Study, items: list[reg.RegItem], days: int | None,
                   cursor: int = -1) -> Text:
    """The checklist body — phases as headers, items with box/date/note."""
    t = Text()
    phase = None
    for i, it in enumerate(items):
        if it.phase != phase:
            phase = it.phase
            t.append(f"\n  ── {phase} ──\n", style="bold #1f9e46")
        cur = i == cursor
        if it.done == reg.DONE:
            style = "bold #00ff88" if cur else "#1f9e46"
        elif it.done == reg.NA:
            style = "bold #8899aa" if cur else "#556677"
        else:
            style = "bold #ffb000" if cur else "#33ff66"
        t.append(f"  {'▶' if cur else ' '} {it.box} {it.item}", style=style)
        if it.custom:
            t.append(" ·custom", style="#8899aa")
        if it.done and it.updated_at:
            t.append(f"  {it.updated_at[5:10].replace('-', '/')}", style="#1f9e46")
        t.append("\n")
        if it.note:
            t.append(f"        └ {it.note[:70]}\n", style="#e8a33d")
    return t


def checklist_export(study: Study, items: list[reg.RegItem], days: int | None) -> str:
    from datetime import datetime
    done, total = reg.progress(items)
    lines = [f"STUDY//SCOUT · REG HANDOFF · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"{study.nct} · {study.title}", f"sponsor: {study.sponsor or '—'}",
             f"progress: {done}/{total}" + (f" · startup day {days}" if days is not None else ""),
             ""]
    phase = None
    for it in items:
        if it.phase != phase:
            phase = it.phase
            lines += ["", f"== {phase} =="]
        stamp = f"  ({it.updated_at[:10]})" if it.done and it.updated_at else ""
        lines.append(f"  {it.box} {it.item}{stamp}")
        if it.note:
            lines.append(f"        note: {it.note}")
    lines.append("")
    return "\n".join(lines)


class RegModal(ModalScreen):
    BINDINGS = [
        ("escape,q,R", "close", "close"),
        ("j,down", "down", "down"),
        ("k,up", "up", "up"),
        ("space,enter", "toggle", "toggle"),
        ("minus", "na", "n/a"),
        ("a,plus", "add", "add item"),
        ("e", "note", "note"),
        ("d", "drop", "drop custom"),
        ("p", "print", "print"),
    ]

    def __init__(self, engine, study: Study):
        super().__init__()
        self.engine = engine
        self.study = study
        self.items: list[reg.RegItem] = engine.reg_detail(study.id)
        self.days = engine.reg_started_days(study.id)
        self.cursor = next((i for i, it in enumerate(self.items) if not it.complete), 0)

    def _reload(self) -> None:
        self.items = self.engine.reg_detail(self.study.id)
        self.days = self.engine.reg_started_days(self.study.id)
        self.cursor = max(0, min(self.cursor, len(self.items) - 1))

    def _title(self) -> Text:
        done, total = reg.progress(self.items)
        col = reg.column_of(self.items, self.engine.reg_phases())
        clock = f"  [dim]startup day {self.days}[/]" if self.days is not None else ""
        return Text.from_markup(
            f"[#ffb000 b]REG HANDOFF · {self.study.nct}[/]  "
            f"[{'#00ff88' if done == total else '#33ff66'}]{done}/{total}[/]  "
            f"[#33ccff]{col}[/]{clock}  [dim]{self.study.sponsor[:26]}[/]")

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box", classes="modal"):
            yield Static(self._title(), id="reg-title", classes="modal-title")
            with VerticalScroll():
                yield Static(checklist_text(self.study, self.items, self.days, self.cursor),
                             id="reg-list", classes="modal-help")
            yield Static(Text.from_markup(
                "[dim]j/k move · [#ffb000 b]space[/][dim] done · [#ffb000 b]-[/][dim] n/a · "
                "a add item · e note · d drop custom · p print · esc close · "
                "template: profile.toml → regulatory.phases[/]"),
                classes="modal-help")

    def _redraw(self) -> None:
        self.query_one("#reg-list", Static).update(
            checklist_text(self.study, self.items, self.days, self.cursor))
        self.query_one("#reg-title", Static).update(self._title())

    def action_down(self) -> None:
        self.cursor = min(self.cursor + 1, len(self.items) - 1)
        self._redraw()

    def action_up(self) -> None:
        self.cursor = max(self.cursor - 1, 0)
        self._redraw()

    def action_toggle(self) -> None:
        if not self.items:
            return
        it = self.items[self.cursor]
        new = self.engine.reg_toggle(self.study.id, it.item)
        self._reload()
        if new and self.cursor < len(self.items) - 1:
            self.cursor += 1          # checked one off — advance to the next
        self._redraw()

    def action_na(self) -> None:
        if not self.items:
            return
        it = self.items[self.cursor]
        self.engine.reg_set(self.study.id, it.item, reg.OPEN if it.done == reg.NA else reg.NA)
        self._reload()
        self._redraw()

    def action_add(self) -> None:
        def got(v):
            if v and v.strip():
                self.engine.reg_add_item(self.study.id, v.strip())
                self._reload()
                self.cursor = len(self.items) - 1
                self._redraw()
        self.app.push_screen(NotesModal("", title="ADD CHECKLIST ITEM (this study only)"), got)

    def action_note(self) -> None:
        if not self.items:
            return
        it = self.items[self.cursor]

        def got(v):
            if v is not None:
                self.engine.reg_note(self.study.id, it.item, v.strip())
                self._reload()
                self._redraw()
        self.app.push_screen(NotesModal(it.note, title=f"NOTE · {it.item[:50]}"), got)

    def action_drop(self) -> None:
        if not self.items:
            return
        it = self.items[self.cursor]
        if not it.custom:
            self.notify("only ad-hoc items can be dropped — mark template items N/A with -",
                        severity="warning")
            return
        self.engine.reg_delete_item(self.study.id, it.item)
        self._reload()
        self._redraw()

    def action_print(self) -> None:
        from .export import export_text
        export_text(self.app, self.study.nct.lower(),
                    checklist_export(self.study, self.items, self.days), prefix="reg")

    def action_close(self) -> None:
        self.dismiss(reg.progress(self.items))

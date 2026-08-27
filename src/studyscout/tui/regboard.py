"""REGULATORY — the startup gauntlet as a board (v1.9.0).

Columns are the checklist PHASES (FEASIBILITY → REG DOCS → IRB → CONTRACTS →
ACTIVATION → ACTIVATED). Nothing is dragged: a study sits in the first phase
with an open item and moves itself as you check things off (R / enter opens
the checklist right here). Cards carry progress, the startup-day clock and
the next open item. `C` promotes an activated study to CONDUCTING — the
handoff from paperwork to the live book.
"""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from .. import regulatory as reg
from ..models import Stage
from .widgets import STAGE_COLOR

_PHASE_COLORS = ["#ffb000", "#33ccff", "#ff66cc", "#c0a000", "#33ff88", "#b58cff", "#8899aa"]


def _col_id(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower())


class RegBoardScreen(Screen):
    BINDINGS = [
        ("escape,G,q", "back", "back"),
        ("left,h", "col_left", "←"), ("right,l", "col_right", "→"),
        ("up,k", "up", "↑"), ("down,j", "down", "↓"),
        ("enter,R", "checklist", "checklist"),
        ("o", "open", "open"),
        ("C", "conducting", "→ conducting"),
        ("t", "due", "follow-up"),
        ("p", "print_column", "print col"),
        ("P", "print_board", "print board"),
    ]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.cols: list[str] = []
        self.cards: dict[str, list[dict]] = {}
        self.col = 0
        self.sel = 0

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        yield Horizontal(id="regboard")
        yield Footer()

    def on_mount(self) -> None:
        self._update_topbar()
        self.call_after_refresh(self._rebuild)

    def _update_topbar(self, total: int = -1) -> None:
        empty = ("   [#ffb000]nothing in startup — studies land here once they hit "
                 "MEETING / WON / CONDUCTING on the pipeline (K)[/]" if total == 0 else "")
        self.query_one("#topbar", Static).update(Text.from_markup(
            "[b #33ff88]STUDY//SCOUT · REGULATORY[/]  [#ffb000]startup gauntlet[/]" + empty +
            "   [dim]h/l phase · j/k card · enter/R checklist · C → conducting · t follow-up · "
            "o open · p/P print · esc back[/]"))

    # ---- data → widgets ---------------------------------------------------- #
    async def _rebuild(self) -> None:
        self.cols, self.cards = self.engine.reg_board()
        total = sum(len(v) for v in self.cards.values())
        self._update_topbar(total)
        self.col = max(0, min(self.col, len(self.cols) - 1))
        items = self.cards.get(self.cols[self.col], []) if self.cols else []
        self.sel = max(0, min(self.sel, max(0, len(items) - 1)))

        board = self.query_one("#regboard", Horizontal)
        await board.remove_children()          # ASYNC — the duplicate-id lesson
        widgets = []
        for ci, name in enumerate(self.cols):
            items = self.cards.get(name, [])
            color = "#00ff88" if name == reg.ACTIVATED else _PHASE_COLORS[ci % len(_PHASE_COLORS)]
            head = Text()
            head.append(f" {'✓' if name == reg.ACTIVATED else '▤'} {name} ", style=f"bold {color}")
            head.append(f"({len(items)})", style="#1f9e46")
            col = Vertical(classes="kcol", id=f"col-{_col_id(name)}")
            widgets.append((col, head, items))
        if widgets:
            await board.mount(*[w for w, _h, _i in widgets])
        for col, head, items in widgets:
            lst = VerticalScroll(classes="kcol-list")
            # Nothing on this board takes focus: the columns are rebuilt
            # wholesale, and a focused-then-removed container silently eats
            # every keystroke (the v1.5.1 focus lesson, board edition).
            lst.can_focus = False
            col.can_focus = False
            await col.mount(Static(head, classes="kcol-head"), lst)
            cards = [Static(self._card_text(c, False), classes="kcard") for c in items]
            if cards:
                await lst.mount(*cards)
            else:
                await lst.mount(Static(Text("  —", style="#1f4a2a"), classes="kcard-empty"))
        if self.app.focused is not None and self.app.screen is self:
            self.app.set_focus(None)
        self._restyle()

    def _card_text(self, c: dict, selected: bool) -> Text:
        study, stage = c["study"], c["stage"]
        t = Text()
        t.append("› " if selected else "  ", style="bold #ffb000")
        t.append(f"{study.nct[-8:]}", style="#b58cff" if study.is_lead else "#33ccff")
        t.append(f" {stage.glyph} {stage.label}", style=STAGE_COLOR.get(stage, "#33ff66"))
        t.append("\n")
        t.append(("  " + study.title[:64]), style="#aaffcc" if selected else "#33ff66")
        t.append("\n")
        t.append(f"  {(study.sponsor or '')[:30]}", style="#ffb000" if selected else "#1f9e46")
        t.append("\n")
        done, total = c["done"], c["total"]
        t.append(f"  ▤ {done}/{total}", style="bold #00ff88" if done == total else "bold #ffb000")
        if c["days"] is not None:
            t.append(f"  day {c['days']}", style="#e8a33d" if c["days"] > 60 else "#1f9e46")
        if c["next"]:
            t.append(f"\n  → {c['next'][:52]}", style="#33ff88")
        elif done == total:
            t.append("\n  ✓ activated — C marks it CONDUCTING", style="#00ff88")
        return t

    def _restyle(self) -> None:
        for ci, name in enumerate(self.cols):
            items = self.cards.get(name, [])
            try:
                col_widget = self.query_one(f"#col-{_col_id(name)}", Vertical)
                lst = col_widget.query_one(VerticalScroll)
            except Exception:
                continue
            cards = [w for w in lst.children if "kcard" in w.classes]
            for ii, card in enumerate(cards):
                selected = (ci == self.col and ii == self.sel)
                card.set_class(selected, "kcard-sel")
                if ii < len(items):
                    card.update(self._card_text(items[ii], selected))
                if selected:
                    card.scroll_visible()
            col_widget.set_class(ci == self.col, "kcol-active")

    # ---- navigation --------------------------------------------------------- #
    def action_col_left(self) -> None:
        if self.cols:
            self.col = (self.col - 1) % len(self.cols)
            self.sel = 0
            self._restyle()

    def action_col_right(self) -> None:
        if self.cols:
            self.col = (self.col + 1) % len(self.cols)
            self.sel = 0
            self._restyle()

    def action_up(self) -> None:
        self.sel = max(0, self.sel - 1)
        self._restyle()

    def action_down(self) -> None:
        items = self.cards.get(self.cols[self.col], []) if self.cols else []
        self.sel = min(max(0, len(items) - 1), self.sel + 1)
        self._restyle()

    def _current(self) -> dict | None:
        if not self.cols:
            return None
        items = self.cards.get(self.cols[self.col], [])
        return items[self.sel] if items and 0 <= self.sel < len(items) else None

    # ---- actions ------------------------------------------------------------ #
    def action_checklist(self) -> None:
        c = self._current()
        if not c:
            return
        from .reg import RegModal

        async def closed(_res):
            await self._rebuild()
        self.app.push_screen(RegModal(self.engine, c["study"]), closed)

    async def action_conducting(self) -> None:
        c = self._current()
        if not c:
            return
        study = c["study"]
        self.engine.set_stage(study.id, Stage.CONDUCTING)
        if c["done"] < c["total"]:
            self.notify(f"{study.nct} → CONDUCTING with {c['total'] - c['done']} paperwork items "
                        "still open — it stays on this board until they clear", severity="warning")
        else:
            self.notify(f"{study.nct} → CONDUCTING · the live book", severity="information")
        await self._rebuild()

    def action_due(self) -> None:
        c = self._current()
        if not c:
            return
        from .followup_screen import ask_due
        ask_due(self, self.engine, c["study"], lambda: self.call_later(self._rebuild))

    def action_open(self) -> None:
        c = self._current()
        if c and c["study"].url:
            try:
                webbrowser.open(c["study"].url)
            except Exception:
                pass

    def action_back(self) -> None:
        self.app.pop_screen()

    # ---- print / export ----------------------------------------------------- #
    def _export_text(self, cols: list[str]) -> str:
        from datetime import datetime
        lines = [f"STUDY//SCOUT · REGULATORY · {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
        for name in cols:
            items = self.cards.get(name, [])
            lines += ["", "=" * 62, f"▤ {name}  ({len(items)})", "=" * 62]
            if not items:
                lines.append("  —")
                continue
            for c in items:
                s = c["study"]
                lines += ["", f"• {s.nct} · {c['stage'].label} · {c['done']}/{c['total']}"
                          + (f" · startup day {c['days']}" if c["days"] is not None else ""),
                          f"  {s.title}", f"  sponsor: {s.sponsor or '—'}"]
                if c["next"]:
                    lines.append(f"  next:    {c['next']}")
                open_items = [i.item for i in c["items"] if not i.complete]
                if len(open_items) > 1:
                    lines.append(f"  open:    {len(open_items)} items — "
                                 + "; ".join(open_items[1:5]) + (" …" if len(open_items) > 5 else ""))
                if c["notes"]:
                    lines.append(f"  notes:   {c['notes']}")
        lines.append("")
        return "\n".join(lines)

    def action_print_column(self) -> None:
        if self.cols:
            from .export import export_text
            name = self.cols[self.col]
            export_text(self.app, _col_id(name), self._export_text([name]), prefix="reg")

    def action_print_board(self) -> None:
        from .export import export_text
        export_text(self.app, "board", self._export_text(list(self.cols)), prefix="reg")

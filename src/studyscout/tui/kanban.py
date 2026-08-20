"""Kanban — the BD pipeline as a dedicated board (v1.4.0).

Worked stages only: the inbox (NEW) lives on the deck, not here — so `0`/`u`
on a card removes it from the board entirely (back to inbox). Columns are
real scrollable containers with per-card gridlines, sized for the eyes.
"""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..models import Stage
from .widgets import STAGE_COLOR

# The board shows the WORKED pipeline. NEW is deliberately absent:
# un-flagging (0/u) drops a study back to the deck inbox — off the board.
BOARD_ORDER = [
    Stage.FLAGGED, Stage.CONTACTED, Stage.WAITING, Stage.REPLIED,
    Stage.MEETING, Stage.WON, Stage.CONDUCTING, Stage.FUTURE, Stage.DECLINED,
    Stage.UNAVAILABLE, Stage.CLOSED,
]

MOVE_KEYS = {
    "1": Stage.FLAGGED, "2": Stage.CONTACTED, "3": Stage.WAITING, "4": Stage.REPLIED,
    "5": Stage.MEETING, "6": Stage.WON, "7": Stage.DECLINED, "8": Stage.CLOSED,
    "9": Stage.FUTURE, "0": Stage.NEW, "u": Stage.NEW, "x": Stage.UNAVAILABLE,
    "C": Stage.CONDUCTING,
}


class KanbanScreen(Screen):
    BINDINGS = [
        ("escape,K,q", "back", "back"),
        ("left,h", "col_left", "←"), ("right,l", "col_right", "→"),
        ("up,k", "up", "↑"), ("down,j", "down", "↓"),
        ("o,enter", "open", "open"),
        ("a", "toggle_all", "all/filtered"),
        ("p", "print_column", "print col"),
        ("P", "print_board", "print board"),
    ]

    def __init__(self, engine, text_filter: str = ""):
        super().__init__()
        self.engine = engine
        self.cols = BOARD_ORDER
        self.board: dict = {}
        self.col = 0
        self.sel = 0
        # v1.4.1 — the board inherits the deck's / filter; `a` lifts it
        self.text_filter = (text_filter or "").strip()
        self.show_all = not self.text_filter

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="board"):
            for st in self.cols:
                with Vertical(classes="kcol", id=f"col-{st.value}"):
                    yield Static("", classes="kcol-head", id=f"head-{st.value}")
                    yield VerticalScroll(id=f"list-{st.value}", classes="kcol-list")
        yield Footer()

    def on_mount(self) -> None:
        self._update_topbar()
        self.call_after_refresh(self._rebuild)

    def _update_topbar(self, total: int = -1) -> None:
        flt = ""
        if self.text_filter:
            flt = (f"   [#00ff88]/{self.text_filter}[/]" +
                   ("[dim] (a = filtered)[/]" if self.show_all else "[dim] (a = show all)[/]"))
        empty = ("   [#ffb000]board empty — search results live on the deck (inbox); "
                 "flag one there (key 1) to start the pipeline[/]" if total == 0 else "")
        self.query_one("#topbar", Static).update(Text.from_markup(
            "[b #33ff88]STUDY//SCOUT · PIPELINE BOARD[/]" + flt + empty + "   "
            "[dim]h/l column · j/k card · 1-9 stage · C conducting · x not-accepting · [#ffb000]0/u → inbox[/] · "
            "p/P print col/board · o open · esc back[/]"))

    def _match(self, study) -> bool:
        if self.show_all or not self.text_filter:
            return True
        q = self.text_filter.lower()
        hay = f"{study.title} {study.sponsor} {study.nct} {' '.join(study.conditions)}".lower()
        return q in hay

    async def action_toggle_all(self) -> None:
        if not self.text_filter:
            return
        self.show_all = not self.show_all
        self._update_topbar()
        await self._rebuild()

    # ---- data → widgets ---------------------------------------------------- #
    async def _rebuild(self) -> None:
        rows = self.engine.load()
        self.board = {st: [] for st in self.cols}
        for study, stage, notes in rows:
            if stage in self.board and self._match(study):
                self.board[stage].append((study, notes))
        self.col = max(0, min(self.col, len(self.cols) - 1))
        items = self.board.get(self.cols[self.col], [])
        self.sel = max(0, min(self.sel, max(0, len(items) - 1)))
        total = 0
        for st in self.cols:
            total += len(self.board.get(st, []))
        self._update_topbar(total)

        for st in self.cols:
            items = self.board.get(st, [])
            color = STAGE_COLOR.get(st, "#33ff66")
            head = Text()
            head.append(f" {st.glyph} {st.label.upper()} ", style=f"bold {color}")
            head.append(f"({len(items)})", style="#1f9e46")
            self.query_one(f"#head-{st.value}", Static).update(head)

            lst = self.query_one(f"#list-{st.value}", VerticalScroll)
            await lst.remove_children()          # ASYNC — the duplicate-id lesson
            cards = []
            for study, notes in items:
                card = Static(self._card_text(study, notes, False), classes="kcard")
                cards.append(card)
            if cards:
                await lst.mount(*cards)
            else:
                await lst.mount(Static(Text("  —", style="#1f4a2a"), classes="kcard-empty"))
        self._restyle()

    def _card_text(self, study, notes, selected: bool) -> Text:
        t = Text()
        t.append("› " if selected else "  ", style="bold #ffb000")
        t.append(f"{study.nct[-8:]}", style="#33ccff")
        t.append(f" {study.phase_str[:6]}", style="#33ff88")
        t.append(" @" if study.has_contact else "  ", style="#00ff88")
        t.append("\n")
        t.append(("  " + study.title[:64]), style="#aaffcc" if selected else "#33ff66")
        t.append("\n")
        t.append(f"  {(study.sponsor or '')[:30]}", style="#ffb000" if selected else "#1f9e46")
        if notes:
            t.append(f"\n  └ {notes[:56]}", style="#e8a33d")
        return t

    def _restyle(self) -> None:
        """Update selection highlight + scroll the selected card into view."""
        for ci, st in enumerate(self.cols):
            items = self.board.get(st, [])
            try:
                lst = self.query_one(f"#list-{st.value}", VerticalScroll)
            except Exception:
                continue
            cards = [w for w in lst.children if "kcard" in w.classes]
            for ii, card in enumerate(cards):
                selected = (ci == self.col and ii == self.sel)
                card.set_class(selected, "kcard-sel")
                if ii < len(items):
                    card.update(self._card_text(items[ii][0], items[ii][1], selected))
                if selected:
                    card.scroll_visible()
            col_widget = self.query_one(f"#col-{st.value}", Vertical)
            col_widget.set_class(ci == self.col, "kcol-active")

    # ---- navigation --------------------------------------------------------- #
    def action_col_left(self) -> None:
        self.col = (self.col - 1) % len(self.cols)
        self.sel = 0
        self._restyle()

    def action_col_right(self) -> None:
        self.col = (self.col + 1) % len(self.cols)
        self.sel = 0
        self._restyle()

    def action_up(self) -> None:
        self.sel = max(0, self.sel - 1)
        self._restyle()

    def action_down(self) -> None:
        items = self.board.get(self.cols[self.col], [])
        self.sel = min(max(0, len(items) - 1), self.sel + 1)
        self._restyle()

    def _current(self):
        items = self.board.get(self.cols[self.col], [])
        return items[self.sel][0] if items and 0 <= self.sel < len(items) else None

    def action_open(self) -> None:
        s = self._current()
        if s:
            try:
                webbrowser.open(s.url)
            except Exception:
                pass

    def action_back(self) -> None:
        self.app.pop_screen()

    # ---- print / export (v1.6.0) -------------------------------------------- #
    def _export_text(self, cols) -> str:
        """A printable, detailed listing of the given columns."""
        from datetime import datetime
        lines = []
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines.append(f"STUDY//SCOUT · PIPELINE · {stamp}")
        if self.text_filter and not self.show_all:
            lines.append(f"filter: /{self.text_filter}")
        for st in cols:
            items = self.board.get(st, [])
            lines.append("")
            lines.append(f"{'=' * 62}")
            lines.append(f"{st.glyph} {st.label.upper()}  ({len(items)})")
            lines.append(f"{'=' * 62}")
            if not items:
                lines.append("  —")
                continue
            for study, notes in items:
                lines.append("")
                lines.append(f"• {study.nct} · {study.phase_str} · {study.status_short}")
                lines.append(f"  {study.title}")
                lines.append(f"  sponsor: {study.sponsor or '—'}")
                contact = study.best_contact()
                if contact and contact.has_direct:
                    lines.append(f"  contact: {contact.render()}")
                if notes:
                    lines.append(f"  notes:   {notes}")
                lines.append(f"  {study.url}")
        lines.append("")
        return "\n".join(lines)

    def _export(self, cols, scope: str) -> None:
        from datetime import datetime

        from ..config import data_dir
        text = self._export_text(cols)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = data_dir() / f"pipeline-{scope}-{stamp}.txt"
        try:
            path.write_text(text, encoding="utf-8")
            saved = f"saved → {path}"
        except Exception as exc:  # noqa: BLE001
            saved = f"save failed: {exc}"
        from .modals import TextModal
        title = f"PRINT · {scope.upper()}  [dim]· c copy · saved to disk — print with: lp {path.name}[/]"
        self.app.push_screen(TextModal(title, text, copyable=True))
        self.notify(saved, severity="information")

    def action_print_column(self) -> None:
        self._export([self.cols[self.col]], self.cols[self.col].value)

    def action_print_board(self) -> None:
        self._export(list(self.cols), "board")

    async def on_key(self, event) -> None:
        if event.key in MOVE_KEYS:
            s = self._current()
            if s:
                target = MOVE_KEYS[event.key]
                self.engine.set_stage(s.id, target)
                if target == Stage.NEW:
                    self.notify(f"{s.nct} → inbox (removed from board)", severity="information")
                await self._rebuild()
                event.stop()

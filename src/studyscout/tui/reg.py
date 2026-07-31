"""Regulatory handoff — the paperwork gauntlet after a study is won.

Press R on a study: a checklist (seeded from `regulatory.checklist` in the
profile — edit it to match your site's SOP) you work through with j/k + space.
State persists per study; the morning briefing nags about open items on
won/meeting studies so nothing dies in startup.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..models import Study


class RegModal(ModalScreen):
    BINDINGS = [
        ("escape,q,R", "close", "close"),
        ("j,down", "down", "down"),
        ("k,up", "up", "up"),
        ("space,enter", "toggle", "toggle"),
    ]

    def __init__(self, engine, study: Study):
        super().__init__()
        self.engine = engine
        self.study = study
        self.items: list[tuple[str, bool]] = engine.reg_state(study.id)
        self.cursor = next((i for i, (_it, d) in enumerate(self.items) if not d), 0)

    def _body(self) -> Text:
        t = Text()
        for i, (item, done) in enumerate(self.items):
            cur = i == self.cursor
            box = "[x]" if done else "[ ]"
            style = ("bold #00ff88" if done else "bold #ffb000") if cur else \
                    ("#1f9e46" if done else "#33ff66")
            t.append(f"  {'▶' if cur else ' '} {box} {item}\n", style=style)
        return t

    def _title(self) -> Text:
        done = sum(1 for _i, d in self.items if d)
        return Text.from_markup(
            f"[#ffb000 b]REG HANDOFF · {self.study.nct}[/]  "
            f"[{'#00ff88' if done == len(self.items) else '#33ff66'}]{done}/{len(self.items)}[/]  "
            f"[dim]{self.study.sponsor[:30]}[/]")

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box", classes="modal"):
            yield Static(self._title(), id="reg-title", classes="modal-title")
            with VerticalScroll():
                yield Static(self._body(), id="reg-list", classes="modal-help")
            yield Static(Text.from_markup(
                "[dim]j/k move · [#ffb000 b]space[/][dim] toggle · esc close · "
                "edit the template in profile.toml → regulatory.checklist[/]"),
                classes="modal-help")

    def _redraw(self) -> None:
        self.query_one("#reg-list", Static).update(self._body())
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
        item, _done = self.items[self.cursor]
        new = self.engine.reg_toggle(self.study.id, item)
        self.items[self.cursor] = (item, new)
        if new and self.cursor < len(self.items) - 1:
            self.cursor += 1          # checked one off — advance to the next
        self._redraw()

    def action_close(self) -> None:
        done = sum(1 for _i, d in self.items if d)
        self.dismiss((done, len(self.items)))

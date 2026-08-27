"""FOLLOW-UP — the tickle file as a ledger (v1.9.0).

`t` anywhere puts a date on a study or lead. This screen is the whole
pressure picture in one place: overdue → today → upcoming → later, then the
un-dated pressure Scout already tracked (quiet sponsors, FUTURE call-backs
due, open startup paperwork). enter jumps to the row on the deck.
"""

from __future__ import annotations

from datetime import date

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Static

from ..followup import Ledger, due_label, parse_due
from ..models import Stage
from .modals import NotesModal
from .widgets import STAGE_COLOR


def ask_due(screen, engine, study, after=None) -> None:
    """Shared `t` handler: prompt, parse forgivingly, persist, report."""
    current = engine.due_map().get(study.id, "")

    def got(v):
        if v is None:
            return
        try:
            d = parse_due(v)
        except ValueError as exc:
            screen.notify(str(exc), severity="warning")
            return
        engine.set_due(study.id, d.isoformat() if d else None)
        if d:
            label, _c = due_label(d.isoformat())
            screen.notify(f"{study.nct} · follow-up {d.isoformat()} ({label}) · T lists them",
                          severity="information")
        else:
            screen.notify(f"{study.nct} · follow-up cleared", severity="information")
        if after:
            after()
    screen.app.push_screen(NotesModal(
        current, title=f"FOLLOW-UP DATE · {study.nct}",
        placeholder="9/15 · +7 · +2w · mon · 2026-09-15 · blank clears"), got)


class FollowupScreen(Screen):
    BINDINGS = [
        ("escape,T,q", "back", "back"),
        ("up,k", "up", "↑"), ("down,j", "down", "↓"),
        ("enter", "jump", "go to study"),
        ("t", "due", "reschedule"),
        ("space", "done", "done (clear)"),
        ("R", "reg", "reg checklist"),
        ("p", "print", "print"),
    ]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.ledger: Ledger = Ledger()
        self.entries: list[tuple[str, object]] = []    # (kind, payload) — navigable rows
        self.sel = 0

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Vertical(id="fu-box"):
            with VerticalScroll(id="fu-scroll"):
                yield Static(id="fu-body")
        yield Static(id="statusbar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#topbar", Static).update(Text.from_markup(
            "[b #33ff88]STUDY//SCOUT · FOLLOW-UP[/]  [#ffb000]the tickle file[/]   "
            "[dim]j/k move · enter → deck · t reschedule · space done · R reg · p print · esc back[/]"))
        self.reload()

    # ---- data ---- #
    def reload(self) -> None:
        self.ledger = self.engine.ledger()
        led = self.ledger
        self.entries = []
        for row in led.overdue + led.today + led.upcoming + led.later:
            self.entries.append(("due", row))
        for item in led.reg:
            self.entries.append(("reg", item))
        self.sel = max(0, min(self.sel, len(self.entries) - 1))
        self._draw()

    def _row_text(self, kind: str, payload, selected: bool) -> Text:
        t = Text()
        t.append("› " if selected else "  ", style="bold #ffb000")
        if kind == "due":
            study, stage, notes, due = payload
            label, color = due_label(due)
            t.append(f"{label:<12}", style=f"bold {color}")
            t.append(f"{stage.glyph} ", style=f"bold {STAGE_COLOR.get(stage, '#33ff66')}")
            t.append(f"{study.nct:<12}", style="#b58cff" if study.is_lead else "#33ccff")
            t.append(study.title[:54], style="#aaffcc" if selected else "#33ff66")
            t.append(f"  {(study.sponsor or '')[:24]}", style="#1f9e46")
            if notes:
                t.append(f"\n                └ {notes[:70]}", style="#e8a33d")
        else:
            study, done, total = payload
            t.append(f"{done}/{total:<9}", style="bold #ffb000")
            t.append("▤ ", style="bold #ffb000")
            t.append(f"{study.nct:<12}", style="#33ccff")
            t.append(study.title[:54], style="#aaffcc" if selected else "#33ff66")
            t.append(f"  {(study.sponsor or '')[:24]}", style="#1f9e46")
        t.append("\n")
        return t

    def _draw(self) -> None:
        led = self.ledger
        t = Text()
        idx = 0

        def section(title: str, rows, style="bold #ffb000"):
            nonlocal idx
            t.append(f"\n{title}\n", style=style)
            if not rows:
                t.append("   —\n", style="#1f4a2a")
            for kind, payload in rows:
                t.append(self._row_text(kind, payload, idx == self.sel))
                idx += 1

        section(f"⏰ OVERDUE  ({len(led.overdue)})", [("due", r) for r in led.overdue], "bold #ff5555")
        section(f"◆ DUE TODAY  ({len(led.today)})", [("due", r) for r in led.today], "bold #ffb000")
        section(f"▶ UPCOMING  (next {led.horizon}d · {len(led.upcoming)})",
                [("due", r) for r in led.upcoming], "bold #33ff88")
        if led.later:
            section(f"· LATER  ({len(led.later)})", [("due", r) for r in led.later], "#1f9e46")
        section(f"▤ REG HANDOFF OPEN  ({len(led.reg)})  [R works the list · G the board]",
                [("reg", r) for r in led.reg], "bold #ffb000")

        t.append(f"\n⏰ QUIET SPONSORS  (≥ {self.engine.cfg.get('followup.nudge_days', 7)}d in "
                 f"Contacted/Waiting · {len(led.quiet)})  [S then m]\n", style="bold #c0a000")
        for name, days, n in led.quiet[:10] or []:
            t.append(f"    {days:>3}d  {name[:40]}  ({n} pending)\n", style="#33ff66")
        if not led.quiet:
            t.append("   —\n", style="#1f4a2a")
        t.append(f"\n⟳ FUTURE CALL-BACKS DUE  (parked ≥ "
                 f"{self.engine.cfg.get('followup.future_nudge_days', 45)}d · {len(led.future)})\n",
                 style="bold #b58cff")
        for name, days, n in led.future[:10] or []:
            t.append(f"    {days:>3}d  {name[:40]}  ({n} parked)\n", style="#33ff66")
        if not led.future:
            t.append("   —\n", style="#1f4a2a")
        t.append("\nt on any study or lead (deck · board · leads) sets its date — "
                 "9/15 · +7 · +2w · mon · blank clears\n", style="dim")
        self.query_one("#fu-body", Static).update(t)
        self.query_one("#statusbar", Static).update(Text.from_markup(
            f"[#ff5555]overdue {len(led.overdue)}[/]   [#ffb000]today {len(led.today)}[/]   "
            f"[#33ff88]upcoming {len(led.upcoming)}[/]   [dim]later {len(led.later)} · "
            f"reg open {len(led.reg)} · quiet {len(led.quiet)} · future {len(led.future)}[/]"))

    # ---- nav / actions ---- #
    def _current(self):
        return self.entries[self.sel] if self.entries and 0 <= self.sel < len(self.entries) else None

    def _study(self):
        cur = self._current()
        if not cur:
            return None
        return cur[1][0]

    def action_up(self) -> None:
        self.sel = max(0, self.sel - 1)
        self._draw()

    def action_down(self) -> None:
        self.sel = min(max(0, len(self.entries) - 1), self.sel + 1)
        self._draw()

    def action_jump(self) -> None:
        s = self._study()
        self.dismiss(s.id if s else None)

    def action_due(self) -> None:
        s = self._study()
        if s:
            ask_due(self, self.engine, s, self.reload)

    def action_done(self) -> None:
        cur = self._current()
        if not cur or cur[0] != "due":
            return
        s = cur[1][0]
        self.engine.set_due(s.id, None)
        self.notify(f"{s.nct} · follow-up done (date cleared) — t sets the next one",
                    severity="information")
        self.reload()

    def action_reg(self) -> None:
        s = self._study()
        if not s:
            return
        from .reg import RegModal
        self.app.push_screen(RegModal(self.engine, s), lambda _r=None: self.reload())

    def action_print(self) -> None:
        from datetime import datetime

        from .export import export_text
        led = self.ledger
        lines = [f"STUDY//SCOUT · FOLLOW-UP · {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
        for title, rows in (("OVERDUE", led.overdue), ("DUE TODAY", led.today),
                            (f"UPCOMING ({led.horizon}d)", led.upcoming), ("LATER", led.later)):
            lines += ["", f"== {title} ({len(rows)}) =="]
            for study, stage, notes, due in rows:
                lines.append(f"  {due}  {stage.label:<12} {study.nct}  {study.title}"
                             f"  [{study.sponsor or '—'}]" + (f"  — {notes}" if notes else ""))
        lines += ["", f"== REG HANDOFF OPEN ({len(led.reg)}) =="]
        for study, done, total in led.reg:
            lines.append(f"  {done}/{total}  {study.nct}  {study.title}  [{study.sponsor or '—'}]")
        lines += ["", f"== QUIET SPONSORS ({len(led.quiet)}) =="]
        for name, days, n in led.quiet:
            lines.append(f"  {days:>3}d  {name}  ({n} pending)")
        lines += ["", f"== FUTURE CALL-BACKS DUE ({len(led.future)}) =="]
        for name, days, n in led.future:
            lines.append(f"  {days:>3}d  {name}  ({n} parked)")
        lines.append("")
        export_text(self.app, "ledger", "\n".join(lines), prefix="followup")

    def action_back(self) -> None:
        self.dismiss(None)

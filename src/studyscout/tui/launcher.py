"""Launcher — the retro menu shown before the deck."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from .connections import ConnectionsScreen
from .filters_screen import FiltersScreen
from .me_editor import MeEditorScreen
from .models_screen import ModelsScreen

BUTTONS = [
    ("jack", "▶  JACK IN — open the deck"),
    ("sponsors", "⊞  SPONSORS — dossier view (the BD lens)"),
    ("kanban", "▦  PIPELINE — kanban board (worked stages)"),
    ("reg", "▤  REGULATORY — startup board: CDA → IRB → CTA → SIV, per-study checklists"),
    ("leads", "◎  LEADS — off-registry prospects (no NCT): PIs, programs, acts, networks"),
    ("followup", "⏰  FOLLOW-UP — the tickle file: dated call-backs, quiet sponsors, open reg"),
    ("filters", "◇  FILTERS — search settings (age, phase, US/intl, site count…)"),
    ("search", "⟲  SEARCH NOW — query ClinicalTrials"),
    ("conn", "⌁  CONNECTIONS — API key"),
    ("models", "◈  MODELS — provider & model"),
    ("site", "✎  SITE PROFILE — what Wintermute pitches"),
    ("quit", "✕  QUIT"),
]


class LauncherScreen(ModalScreen):
    BINDINGS = [("escape,q", "quit_app", "quit"), ("up,k", "up", "up"), ("down,j", "down", "down")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Static(Text.from_markup("[#ffb000 b]S T U D Y // S C O U T[/]  [dim]· bd intel[/]"),
                         classes="modal-title")
            yield Static(self._status_text(), id="menu-status", classes="modal-help")
            with Vertical(id="menu-buttons"):
                for bid, label in BUTTONS:
                    yield Button(label, id=f"b_{bid}")
            yield Static(Text.from_markup("[dim]↑↓ / tab move · enter select · Jack in → deck · esc quits[/]"),
                         classes="modal-help")

    def on_mount(self) -> None:
        self.query_one("#b_jack", Button).focus()

    def _status_text(self) -> Text:
        cfg = self.engine.cfg
        wm = (f"[#33ff88]●[/] Wintermute armed [dim]({cfg.provider()}:{cfg.model_for('consigliere')})[/]"
              if self.engine.ai_ready else "[#ff5555]○[/] Wintermute dark — add a key in Connections")
        n = len(self.engine.load())
        return Text.from_markup(f"  {wm}    [dim]· {n} studies in deck[/]")

    def _refresh(self, *_a) -> None:
        try:
            self.query_one("#menu-status", Static).update(self._status_text())
        except Exception:
            pass

    def _run_search(self) -> None:
        self.dismiss()
        from .main_screen import MainScreen
        if isinstance(self.app.screen, MainScreen):
            self.app.screen.action_refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = (event.button.id or "")[2:]
        if bid == "jack":
            self.dismiss()
        elif bid == "sponsors":
            self.dismiss()
            from .main_screen import MainScreen
            if isinstance(self.app.screen, MainScreen):
                self.app.screen.action_sponsors()
        elif bid == "kanban":
            self.dismiss()
            from .kanban import KanbanScreen
            from .main_screen import MainScreen
            tf = next((scr.text_filter for scr in reversed(self.app.screen_stack)
                       if isinstance(scr, MainScreen)), "")
            self.app.push_screen(KanbanScreen(self.engine, text_filter=tf))
        elif bid == "reg":
            self.dismiss()
            from .regboard import RegBoardScreen
            self.app.push_screen(RegBoardScreen(self.engine))
        elif bid == "leads":
            self.dismiss()
            from .leads import LeadsScreen
            self.app.push_screen(LeadsScreen(self.engine))
        elif bid == "followup":
            self.dismiss()
            from .followup_screen import FollowupScreen
            from .main_screen import MainScreen
            main = next((scr for scr in reversed(self.app.screen_stack)
                         if isinstance(scr, MainScreen)), None)
            self.app.push_screen(FollowupScreen(self.engine),
                                 (main.landed_from_followup if main else None))
        elif bid == "filters":
            def done(run):
                if run:
                    self._run_search()
            self.app.push_screen(FiltersScreen(self.engine), done)
        elif bid == "search":
            self._run_search()
        elif bid == "conn":
            self.app.push_screen(ConnectionsScreen(self.engine), self._refresh)
        elif bid == "models":
            self.app.push_screen(ModelsScreen(self.engine), self._refresh)
        elif bid == "site":
            self.app.push_screen(MeEditorScreen(self.engine))
        elif bid == "quit":
            self.app.exit()

    def action_up(self) -> None:
        self.focus_previous()

    def action_down(self) -> None:
        self.focus_next()

    def action_quit_app(self) -> None:
        self.app.exit()

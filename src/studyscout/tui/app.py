"""The Textual App — splash → menu → deck."""
from __future__ import annotations

from textual.app import App

from ..engine import Engine
from .launcher import LauncherScreen
from .main_screen import MainScreen
from .splash import Splash


class StudyScoutApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "StudyScout"
    SUB_TITLE = "bd intel terminal"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, engine: Engine | None = None):
        super().__init__()
        self.engine = engine or Engine()

    def on_mount(self) -> None:
        self.push_screen(MainScreen(self.engine))
        if self.engine.cfg.get("ui.splash", True):
            self.push_screen(Splash(on_done=self._post_splash))
        elif self.engine.cfg.get("ui.show_menu", True):
            self.push_screen(LauncherScreen(self.engine))

    def _post_splash(self) -> None:
        self.pop_screen()
        if self.engine.cfg.get("ui.show_menu", True):
            self.push_screen(LauncherScreen(self.engine))

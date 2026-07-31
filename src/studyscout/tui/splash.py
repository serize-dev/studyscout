"""Splash — the StudyScout logo in bright phosphor green. Any key enters."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

LOGO = r"""
 _______ __            __         _______                    __
|     __|  |_.--.--.--|  |.--.--.|     __|.----.-----.--.--.|  |_
|__     |   _|  |  |  _  ||  |  ||__     ||  __|  _  |  |  ||   _|
|_______|____|_____|_____||___  ||_______||____|_____|_____||____|
                          |_____|
"""

SUB = "ctgov.v2  ::  bd intel terminal"


class Splash(ModalScreen):
    def __init__(self, on_done):
        super().__init__()
        self._on_done = on_done

    def compose(self) -> ComposeResult:
        with Vertical(id="splash-box"):
            yield Static(self._logo())

    def _logo(self) -> Text:
        t = Text(justify="center")
        t.append(LOGO, style="bold #33ff66")
        t.append("\n" + SUB, style="italic #ffb000")
        return t

    def on_key(self, event: events.Key) -> None:
        event.stop()
        self._dismiss()

    def on_click(self) -> None:
        self._dismiss()

    def _dismiss(self) -> None:
        if self._on_done:
            cb, self._on_done = self._on_done, None
            cb()

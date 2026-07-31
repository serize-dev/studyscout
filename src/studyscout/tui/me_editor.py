"""Me — edit the 'rules of the game' file Wintermute reads, right in the app."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea


class MeEditorScreen(ModalScreen):
    BINDINGS = [("ctrl+s", "save", "save"), ("escape", "maybe_close", "close")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._dirty = False
        self._path = engine.cfg.ensure_me()

    def compose(self) -> ComposeResult:
        text = self._path.read_text(errors="ignore") if self._path.exists() else ""
        with Vertical(id="me-box"):
            yield Static(Text.from_markup("[#ffb000 b]SITE PROFILE[/]  [dim](Wintermute pitches with this)[/]"),
                         classes="modal-title")
            ta = TextArea(text, id="me-editor", soft_wrap=True)
            ta.show_line_numbers = False
            yield ta
            yield Static(Text.from_markup(
                "[#ffb000 b]ctrl+s[/] save    [#ffb000 b]esc[/] close    "
                f"[dim]{self._path}[/]"), classes="modal-help")

    def on_mount(self) -> None:
        self.query_one("#me-editor", TextArea).focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._dirty = True

    def action_save(self) -> None:
        text = self.query_one("#me-editor", TextArea).text
        try:
            self._path.write_text(text)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"save failed: {exc}", severity="error")
            return
        self._dirty = False
        self.notify("Saved. Wintermute will use this next time.", severity="information")

    def action_maybe_close(self) -> None:
        if self._dirty:
            self.notify("Unsaved — press ctrl+s to save, or esc again to discard.", severity="warning")
            self._dirty = False  # next esc closes
            return
        self.dismiss()

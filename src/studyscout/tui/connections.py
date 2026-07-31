"""Connections — paste & save the API key for Wintermute."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

FIELDS = [
    ("Claude / Wintermute — Anthropic API key  (or $ANTHROPIC_API_KEY)", "ai.api_key", True),
    ("OpenRouter — API key  (or $OPENROUTER_API_KEY)", "ai.openrouter_key", True),
    ("OpenAI — API key  (or $OPENAI_API_KEY)", "ai.openai_key", True),
]

SIGNUP = ("[dim]keys →  Claude: console.anthropic.com   OpenRouter: openrouter.ai/keys   "
          "OpenAI: platform.openai.com   ·   pick the active model in Models.[/]")


def _slug(path: str) -> str:
    return "f_" + path.replace(".", "_")


class ConnectionsScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close"), ("ctrl+s", "save", "save"), ("ctrl+t", "test", "test")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def compose(self) -> ComposeResult:
        with Vertical(id="conn-box"):
            yield Static(Text.from_markup("[#ffb000 b]CONNECTIONS · API KEYS[/]"), classes="modal-title")
            yield Static(self._status_text(), id="conn-status", classes="modal-help")
            with VerticalScroll(id="conn-fields"):
                for label, path, secret in FIELDS:
                    yield Static(Text.from_markup(f"[#33ff66]{label}[/]"))
                    yield Input(value=str(self.engine.cfg.get(path, "") or ""), password=secret,
                                placeholder="paste here…", id=_slug(path))
            yield Static(Text.from_markup(SIGNUP), classes="modal-help")
            yield Static(Text.from_markup(
                "[#ffb000 b]ctrl+s[/] save & arm    [#ffb000 b]ctrl+t[/] test    [#ffb000 b]esc[/] close"),
                classes="modal-help")

    def on_mount(self) -> None:
        self.query_one(f"#{_slug('ai.api_key')}", Input).focus()

    def _status_text(self) -> Text:
        cfg = self.engine.cfg
        wm = "●" if self.engine.ai_ready else "○"
        c = "#33ff88" if self.engine.ai_ready else "#ff5555"
        key = cfg.api_key()
        info = f"key: {cfg.api_key_source()}" + (f" …{key[-4:]} ({len(key)} ch)" if key else "")
        return Text.from_markup(f"  Wintermute [{c}]{wm}[/]   [dim]{info}[/]\n"
                                "  [dim]● live · ○ waiting · ctrl+t tests the live connection[/]")

    def _refresh_status(self) -> None:
        self.query_one("#conn-status", Static).update(self._status_text())

    def action_save(self) -> None:
        cfg = self.engine.cfg
        for _label, path, secret in FIELDS:
            raw = self.query_one(f"#{_slug(path)}", Input).value
            cfg.set(path, "".join(raw.split()) if secret else raw.strip())
        try:
            cfg.save()
        except Exception as exc:  # noqa: BLE001
            self.notify(f"save failed: {exc}", severity="error")
            return
        self.engine.reload_brain()
        self._refresh_status()
        self.notify("Saved. Wintermute " + ("armed ✓" if self.engine.ai_ready else "still needs a key."),
                    severity="information")

    @work(exclusive=True)
    async def action_test(self) -> None:
        self.action_save()
        if not self.engine.ai_ready:
            self.notify("No key to test — paste one and ctrl+s first.", severity="warning")
            return
        self.notify("testing live connection…")
        ok, msg = await self.engine.brain.ping()
        self.notify(msg, severity="information" if ok else "error", timeout=8)
        self._refresh_status()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_save()

"""Wintermute — fullscreen BD chat modal. Shares history with the pane."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import RichLog, Static

from ..models import Study
from .chatinput import ChatInput


class ChatScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close"), ("ctrl+n", "fresh", "new thread")]

    def __init__(self, consigliere, study: Study | None, notes: str = "", history: list | None = None):
        super().__init__()
        self.consigliere = consigliere
        self.study = study
        self.notes = notes
        self.history: list[dict] = history if history is not None else []

    def compose(self) -> ComposeResult:
        with Vertical(id="chat-box"):
            ctx = f"WINTERMUTE  ·  {self.study.nct}" if self.study else "WINTERMUTE"
            yield Static(Text.from_markup(f"[#ffb000 b]{ctx}[/]"), classes="modal-title")
            yield RichLog(id="chat-log", wrap=True, markup=True, highlight=False)
            yield ChatInput(placeholder="ask Wintermute…  (enter sends · ctrl+j newline · ctrl+u update site · esc)",
                            id="chat-input")

    def on_mount(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        if not self.consigliere.enabled:
            log.write(Text.from_markup("[#ffb000]Wintermute is dark — add a key in Connections (g).[/]"))
        elif self.history:
            for m in self.history:
                who = "[#ffb000 b]you>[/] " if m["role"] == "user" else "[#33ff88 b]wintermute>[/] "
                log.write(Text.from_markup(who) + Text(m["content"]))
        else:
            hook = ("I'm on this study — fit for your site, outreach, or pitch prep?"
                    if self.study else "Deck's warm. What do you need?")
            log.write(Text.from_markup(f"[#33ff88 b]wintermute>[/] {hook}"))
        self.query_one("#chat-input", ChatInput).focus()

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return
        log = self.query_one("#chat-log", RichLog)
        if not self.consigliere.enabled:
            log.write(Text.from_markup("[#ffb000]…still dark. Set your API key first.[/]"))
            return
        log.write(Text.from_markup(f"[#ffb000 b]you>[/] {msg}"))
        log.write(Text.from_markup("[dim]wintermute is thinking…[/]"))
        self._ask(msg)

    @work(exclusive=True)
    async def _ask(self, msg: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        try:
            reply = await self.consigliere.chat(self.history, self.study, self.notes, msg)
        except Exception as exc:  # noqa: BLE001
            log.write(Text.from_markup(f"[red]link error:[/] {exc}"))
            return
        self.history.append({"role": "user", "content": msg})
        self.history.append({"role": "assistant", "content": reply})
        log.write(Text.from_markup("[#33ff88 b]wintermute>[/] ") + Text(reply))

    def action_fresh(self) -> None:
        """Wipe the shared thread — momentum reset without restarting the app."""
        self.history.clear()
        try:
            self.consigliere._chat_study_id = None
        except Exception:
            pass
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        log.write(Text.from_markup("[#33ff88 b]wintermute>[/] Fresh thread. Same me, clean slate."))

    def on_chat_input_revise(self, event: ChatInput.Revise) -> None:
        self._revise()

    @work(exclusive=True)
    async def _revise(self) -> None:
        from .me_revise import diff_text
        from .modals import ConfirmModal
        log = self.query_one("#chat-log", RichLog)
        if not self.consigliere.enabled or not self.history:
            log.write(Text.from_markup("[#ffb000]Chat first, then Ctrl+U to update your site profile.[/]"))
            return
        log.write(Text.from_markup("[dim]drafting an update to your site profile…[/]"))
        try:
            new = await self.consigliere.revise_site(self.history)
        except Exception as exc:  # noqa: BLE001
            log.write(Text.from_markup(f"[red]couldn't draft:[/] {exc}"))
            return
        cfg = self.consigliere.cfg
        old = cfg.me_text(limit=100000)
        if new.strip() == (old or "").strip():
            log.write(Text.from_markup("[#33ff88]site.md already matches.[/]"))
            return

        def confirm(yes):
            if yes:
                try:
                    cfg.me_path().write_text(new)
                    log.write(Text.from_markup("[#33ff88 b]site.md updated ✓[/]"))
                except Exception as exc:  # noqa: BLE001
                    log.write(Text.from_markup(f"[red]save failed:[/] {exc}"))
        self.app.push_screen(ConfirmModal("UPDATE SITE PROFILE?", diff_text(old, new)), confirm)

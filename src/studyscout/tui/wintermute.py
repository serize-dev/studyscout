"""The persistent Wintermute BD pane — context-aware on the selected study."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from ..models import Study
from .chatinput import ChatInput


class WintermutePane(Vertical):
    def __init__(self, consigliere):
        super().__init__(id="wm")
        self.consigliere = consigliere
        self.history: list[dict] = []
        self.study: Study | None = None
        self.notes: str = ""
        self.border_title = "WINTERMUTE"

    def compose(self) -> ComposeResult:
        yield Static(self._ctx_line(), id="wm-ctx")
        yield RichLog(id="wm-log", wrap=True, markup=True, highlight=False)
        yield ChatInput(placeholder="ask Wintermute…", id="wm-input")

    def on_mount(self) -> None:
        self._greet()

    def _greet(self) -> None:
        log = self.query_one("#wm-log", RichLog)
        if not self.consigliere.enabled:
            log.write(Text.from_markup("[#ffb000]○ dark[/] — add an API key in [b]Connections[/] (g)."))
        else:
            log.write(Text.from_markup(
                "[#33ff88 b]wintermute>[/] deck's warm. select a study — I'll size up the fit for your "
                "site, draft the outreach, or prep your pitch.  "
                "[dim](c = full screen · ctrl+e = fold chat into an email · ctrl+u = update site profile)[/]"))

    def _ctx_line(self) -> Text:
        if self.study:
            return Text.from_markup(f"[dim]▸ {self.study.nct} · {self.study.title[:34]}[/]")
        return Text.from_markup("[dim]▸ no study selected[/]")

    def set_study(self, study: Study | None, notes: str = "") -> None:
        self.study = study
        self.notes = notes
        try:
            self.query_one("#wm-ctx", Static).update(self._ctx_line())
        except Exception:
            pass

    def focus_input(self) -> None:
        self.query_one("#wm-input", ChatInput).focus()

    def rebuild_log(self) -> None:
        try:
            log = self.query_one("#wm-log", RichLog)
        except Exception:
            return
        log.clear()
        self._greet()
        for m in self.history:
            who = "[#ffb000 b]you>[/] " if m["role"] == "user" else "[#33ff88 b]wintermute>[/] "
            log.write(Text.from_markup(who) + Text(m["content"]))

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        if event.value:
            self._send(event.value)

    def _send(self, msg: str) -> None:
        log = self.query_one("#wm-log", RichLog)
        if not self.consigliere.enabled:
            log.write(Text.from_markup("[#ffb000]…still dark. Add a key in Connections (g).[/]"))
            return
        log.write(Text.from_markup(f"[#ffb000 b]you>[/] {msg}"))
        log.write(Text.from_markup("[dim]…thinking[/]"))
        self._ask(msg)

    @work(exclusive=True)
    async def _ask(self, msg: str) -> None:
        log = self.query_one("#wm-log", RichLog)
        try:
            reply = await self.consigliere.chat(self.history, self.study, self.notes, msg)
        except Exception as exc:  # noqa: BLE001
            log.write(Text.from_markup(f"[red]link error:[/] {exc}"))
            return
        self.history.append({"role": "user", "content": msg})
        self.history.append({"role": "assistant", "content": reply})
        log.write(Text.from_markup("[#33ff88 b]wintermute>[/] ") + Text(reply))

    def on_chat_input_revise(self, event: ChatInput.Revise) -> None:
        self._revise()

    def on_chat_input_compose(self, event: ChatInput.Compose) -> None:
        self._compose_email()

    @work(exclusive=True)
    async def _compose_email(self) -> None:
        from .modals import TextModal
        log = self.query_one("#wm-log", RichLog)
        if not self.consigliere.enabled or not self.history:
            log.write(Text.from_markup("[#ffb000]Chat first, then Ctrl+E to fold it into an email.[/]"))
            return
        log.write(Text.from_markup("[dim]folding the conversation into an email…[/]"))
        try:
            draft = await self.consigliere.email_from_chat(self.history, self.study, self.notes)
        except Exception as exc:  # noqa: BLE001
            log.write(Text.from_markup(f"[red]couldn't draft:[/] {exc}"))
            return
        to = self.study.best_contact().email if self.study else None
        subject = f"Site interest — {self.study.nct}" if self.study else "Site outreach"
        mail_ctx = (to, subject, self.consigliere.cfg.get("ui.mail_command", ""))
        title = f"OUTREACH · {self.study.nct}" if self.study else "OUTREACH · from chat"
        self.app.push_screen(TextModal(title, draft, amber=True, copyable=True, mail=mail_ctx))
        log.write(Text.from_markup("[#33ff88 b]draft ready[/] [dim]· c copy · o open in mail[/]"))

    @work(exclusive=True)
    async def _revise(self) -> None:
        from .me_revise import diff_text
        from .modals import ConfirmModal
        log = self.query_one("#wm-log", RichLog)
        if not self.consigliere.enabled or not self.history:
            log.write(Text.from_markup("[#ffb000]Chat first, then Ctrl+U to fold it into your site profile.[/]"))
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
            log.write(Text.from_markup("[#33ff88]site.md already matches — nothing to change.[/]"))
            return

        def confirm(yes):
            if yes:
                try:
                    cfg.me_path().write_text(new)
                    log.write(Text.from_markup("[#33ff88 b]site.md updated ✓[/]"))
                except Exception as exc:  # noqa: BLE001
                    log.write(Text.from_markup(f"[red]save failed:[/] {exc}"))
        self.app.push_screen(ConfirmModal("UPDATE SITE PROFILE?", diff_text(old, new)), confirm)

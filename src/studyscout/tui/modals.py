"""Reusable modal screens: F1 help, scrollable text (job detail / cold email),
notes editor, and a yes/no confirm.
"""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

HELP_TEXT = """\
[b #ffb000]NAVIGATION[/]
  [#33ff66]↑ ↓ / j k[/]   move selection
  [#33ff66]tab[/]         cycle focus: studies → detail (scroll) → Wintermute
  [#33ff66]z[/]           zoom — on the list: full table, every column, click headers to sort;
              on the detail pane: full-screen study view
  [#33ff66]\\[/]          show / hide the Wintermute pane
  [#33ff66]enter / o[/]   open the study on ClinicalTrials.gov
  [#33ff66]/[/]           filter the list by text (title / sponsor / NCT / condition)
  [#33ff66]s[/]           sort — pick a field (same field again flips direction);
              clicking a column header on the deck sorts by it too
  [#33ff66]a[/]           show / hide stale rows (inbox studies the latest search didn't catch)
  [#33ff66]S[/]           SPONSORS — the dossier view: one row per relationship
  [#33ff66]K[/]           PIPELINE BOARD — worked stages only (also in the menu);
              on the board: [#33ff66]0/u[/] sends a card back to the inbox (off the board);
              [#33ff66]p[/] prints the column · [#33ff66]P[/] the whole board (saved as a text file too)
  [#33ff66]g / esc[/]     menu — filters · connections · models · site  (esc again quits)

[b #ffb000]PIPELINE   (set the selected study's stage)[/]
  [#33ff66]1[/] flagged  [#33ff66]2[/] contacted  [#33ff66]3[/] waiting  [#33ff66]4[/] replied
  [#33ff66]5[/] meeting  [#33ff66]6[/] won  [#33ff66]C[/] conducting  [#33ff66]9[/] future outreach  [#33ff66]7[/] declined  [#33ff66]n[/] not a good fit  [#33ff66]x[/] not accepting  [#33ff66]8[/] closed  [#33ff66]0[/] inbox
  [dim]9 = relationship warm, "call us for the next study" — the briefing nags you
  when a FUTURE sponsor has been parked past followup.future_nudge_days (45d).
  The site lifecycle: 6 won (startup) → C CONDUCTING (running at your site — the
  live book) → 8 closed (completed archive).  x = never got in (not accepting).  n = screened, not for us (your call).[/]

[b #ffb000]ACTIONS[/]
  [#33ff66]b[/]   morning briefing — new trials · status flips · quiet sponsors · top 3
  [#33ff66]f[/]   filters — set the ClinicalTrials search (age, phase, US/intl, site count…)
  [#33ff66]r[/]   search now — run the filters against ClinicalTrials.gov
  [#33ff66]c[/]   Wintermute — full-screen chat about this study
  [#33ff66]m[/]   draft outreach to the PI  ([#ffb000]o[/] in the draft opens it in your mail client)
  [#33ff66]e[/]   edit notes on this study
  [#33ff66]R[/]   reg handoff — startup checklist for a won study (CDA → 1572 → IRB → CTA → SIV)

[b #ffb000]SPONSOR DOSSIERS  (press S)[/]
  One row per sponsor: their book of trials, contacts deduped across NCTs,
  your pipeline history and last touch. [#33ff66]m[/] drafts ONE consolidated
  multi-trial pitch — stronger than three cold emails to the same company.
  [#33ff66]W[/]  EXPAND the dossier — Wintermute hunts the live web for pipeline news,
      fresh signals, and who to reach; the intel is saved on the relationship,
      dated, and fed into the [#33ff66]m[/] pitch automatically  (uses tokens)
  [#33ff66]e[/] sponsor notes · [#33ff66]s[/] sort (BD value / trials / recruiting / last touch)

[b #ffb000]SYSTEM[/]
  [#33ff66]F1[/]  this help        [#33ff66]q[/]  quit

[dim]@ = a direct contact (email/phone) is listed.   SITE count: multi-site (≥2) = better odds.[/]
[dim]In chat: ctrl+e folds the conversation into an outreach email · ctrl+u into your site profile
(site.md) — both work with the focus anywhere, not just inside the input.
Mail: `o` on a draft honors ui.mail_mode — "mailto" (default) or "outlook" (Outlook Web
compose in the browser, the route for O365/Prospect Mail shops).[/]"""


class HelpModal(ModalScreen):
    # Bindings consume the key, so it can't bubble to the board (which would
    # otherwise trigger the board's escape→exit). Do NOT add a bare on_key here.
    BINDINGS = [("escape,f1,q,enter,space", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Static(Text.from_markup("[#ffb000 b]STUDY//SCOUT · FIELD MANUAL[/]"), classes="modal-title")
            with VerticalScroll():
                yield Static(Text.from_markup(HELP_TEXT), classes="modal-help")
            yield Static(Text.from_markup("[dim]press esc to close[/]"), classes="modal-help")


class TextModal(ModalScreen):
    """Scrollable text viewer. Optional clipboard copy ('c') and open-in-mail ('o')."""

    BINDINGS = [("escape,q", "dismiss", "close"), ("c", "copy", "copy"), ("o", "mail", "mail")]

    def __init__(self, title: str, body: str, amber: bool = False, copyable: bool = False,
                 mail: tuple | None = None):
        super().__init__()
        self._title = title
        self._body = body
        self._amber = amber
        self._copyable = copyable
        self._mail = mail            # (to_addr, subject_fallback, command) or None

    def compose(self) -> ComposeResult:
        box = Vertical(id="modal-box", classes="modal amber" if self._amber else "modal")
        with box:
            yield Static(Text.from_markup(self._title), classes="modal-title")
            with VerticalScroll():
                yield Static(self._body, classes="modal-help")
            hint = "[dim]esc close"
            if self._copyable:
                hint += "  ·  c copy"
            if self._mail:
                hint += "  ·  [#ffb000 b]o open in mail client[/][dim]"
            hint += "[/]"
            yield Static(Text.from_markup(hint), classes="modal-help")

    def action_copy(self) -> None:
        if not self._copyable:
            return
        try:
            self.app.copy_to_clipboard(self._body)
            self.notify("Copied to clipboard.", severity="information")
        except Exception:
            self.notify("Clipboard not available in this terminal.", severity="warning")

    def action_mail(self) -> None:
        if not self._mail:
            return
        from ..mail import open_mail, split_draft
        to_addr, subject_fallback, command, mode = (self._mail + (None, None, "", "mailto"))[:4]
        subject, body = split_draft(self._body, subject_fallback or "")
        ok, msg = open_mail(to_addr, subject, body, command or "", mode or "mailto")
        self.notify(msg, severity="information" if ok else "warning")


class NotesModal(ModalScreen):
    """Single-line notes editor that returns its value via dismiss()."""

    BINDINGS = [("escape", "cancel", "cancel")]

    def __init__(self, current: str = ""):
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box", classes="modal"):
            yield Static(Text.from_markup("NOTES — enter to save, esc to cancel"), classes="modal-title")
            yield Input(value=self._current, placeholder="e.g. emailed coordinator 6/30…", id="notes-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmModal(ModalScreen):
    """Yes/no confirm. dismiss(True/False)."""

    BINDINGS = [("y", "yes", "yes"), ("n,escape", "no", "no")]

    def __init__(self, title: str, body: str):
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        body = self._body if isinstance(self._body, Text) else Text.from_markup(self._body)
        with Vertical(id="modal-box", classes="modal amber"):
            yield Static(Text.from_markup(self._title), classes="modal-title")
            with VerticalScroll():
                yield Static(body, classes="modal-help")
            yield Static(Text.from_markup("[#ffb000 b]  y[/] apply    [#ffb000 b]n[/] cancel"), classes="modal-help")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

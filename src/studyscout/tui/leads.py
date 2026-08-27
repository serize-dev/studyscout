"""LEADS — off-registry prospects (v1.9.0).

Not everything worth chasing has an NCT: a PI you met, a state genetics
program, an act with grant money behind it, a network that said "call us".
A lead gets a LEAD-#### id and lives in the SAME store as the studies — so
it rides the pipeline (1-9 / C / x / n), the board (K), the sponsor dossier
(S), notes (e), outreach (m), chat (c), reg (R) and the tickle file (t / T)
with zero special cases. This screen is where you add, edit and drop them.
"""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Input, RadioButton, RadioSet, Static, TextArea

from ..followup import due_label
from ..models import SPONSOR_CLASS_LABEL, Stage, Study
from .modals import ConfirmModal, NotesModal, TextModal
from .widgets import STAGE_COLOR, detail_view, stage_glyph

KIND_OPTS = [("Industry", "INDUSTRY"), ("Academic / hospital", "OTHER"), ("Government", "OTHER_GOV"),
             ("NIH", "NIH"), ("Network / SMO", "NETWORK"), ("Individual (PI)", "INDIV")]
STAGE_OPTS = [Stage.FLAGGED, Stage.CONTACTED, Stage.WAITING, Stage.REPLIED,
              Stage.MEETING, Stage.FUTURE]

FIELDS = [
    ("title", "Lead — what is it? *", "e.g. Sunshine Genetics Act — PI outreach"),
    ("sponsor", "Organization (groups into the dossier)", "e.g. State Univ. Dept of Genetics"),
    ("name", "Contact name", ""),
    ("role", "Contact role / title", "e.g. PI · program director"),
    ("email", "Email", ""),
    ("phone", "Phone", ""),
    ("link", "Link (URL)", "https://…"),
    ("topics", "Topics (comma-separated)", "e.g. newborn screening, genetics"),
    ("due", "Follow-up date", "9/15 · +7 · +2w · mon · blank = none"),
]


class LeadForm(ModalScreen):
    """Add / edit a lead. dismiss(dict | None)."""

    BINDINGS = [("escape", "cancel", "cancel"), ("ctrl+s", "save", "save")]

    def __init__(self, engine, study: Study | None = None, stage: Stage | None = None,
                 due: str = ""):
        super().__init__()
        self.engine = engine
        self.study = study
        self.stage = stage or Stage.FLAGGED
        self.due = due

    def _initial(self, key: str) -> str:
        s = self.study
        if not s:
            return ""
        c = s.central_contacts[0] if s.central_contacts else None
        return {
            "title": s.title, "sponsor": s.sponsor, "link": s.link,
            "topics": ", ".join(s.conditions),
            "name": (c.name if c else "") or "", "role": (c.role if c else "") or "",
            "email": (c.email if c else "") or "", "phone": (c.phone if c else "") or "",
            "due": self.due,
        }.get(key, "")

    def compose(self) -> ComposeResult:
        head = ("EDIT LEAD · " + self.study.nct) if self.study else "NEW LEAD  (no NCT needed)"
        with Vertical(id="lead-box"):
            yield Static(Text.from_markup(f"[#ffb000 b]{head}[/]  [dim]ctrl+s save · esc cancel[/]"),
                         classes="modal-title")
            with VerticalScroll(id="lead-scroll"):
                with Grid(id="lead-grid"):
                    for key, label, ph in FIELDS:
                        with Vertical(classes="lead-field"):
                            yield Static(Text.from_markup(f"[#1f9e46]{label}[/]"))
                            yield Input(value=self._initial(key), placeholder=ph, id=f"lf-{key}")
                with Horizontal(id="lead-radios"):
                    with Vertical(classes="lead-field"):
                        yield Static(Text.from_markup("[#1f9e46]Kind[/]"))
                        kind = self.study.sponsor_class if self.study else "OTHER"
                        with RadioSet(id="lf-kind"):
                            for label, val in KIND_OPTS:
                                yield RadioButton(label, value=(val == kind), id=f"kind-{val}")
                    with Vertical(classes="lead-field"):
                        yield Static(Text.from_markup("[#1f9e46]Stage[/]"))
                        with RadioSet(id="lf-stage"):
                            for st in STAGE_OPTS:
                                yield RadioButton(f"{st.glyph} {st.label}", value=(st == self.stage),
                                                  id=f"stage-{st.value}")
                yield Static(Text.from_markup("[#1f9e46]What you know (free text — Wintermute reads this)[/]"))
                ta = TextArea(self.study.summary if self.study else "", id="lf-summary", soft_wrap=True)
                ta.show_line_numbers = False
                yield ta
            with Horizontal(id="lead-buttons"):
                yield Button("SAVE  (ctrl+s)", id="lf-save")
                yield Button("CANCEL", id="lf-cancel")

    def on_mount(self) -> None:
        self.query_one("#lf-title", Input).focus()

    def _val(self, key: str) -> str:
        return self.query_one(f"#lf-{key}", Input).value.strip()

    def _radio(self, set_id: str, prefix: str, default: str) -> str:
        rs = self.query_one(f"#{set_id}", RadioSet)
        btn = rs.pressed_button
        if btn and btn.id and btn.id.startswith(prefix):
            return btn.id[len(prefix):]
        return default

    def action_save(self) -> None:
        if not self._val("title"):
            self.notify("a lead needs at least a title", severity="warning")
            self.query_one("#lf-title", Input).focus()
            return
        due_raw = self._val("due")
        due = ""
        if due_raw:
            from ..followup import parse_due
            try:
                d = parse_due(due_raw)
                due = d.isoformat() if d else ""
            except ValueError as exc:
                self.notify(str(exc), severity="warning")
                self.query_one("#lf-due", Input).focus()
                return
        form = {
            "title": self._val("title"), "sponsor": self._val("sponsor"),
            "link": self._val("link"),
            "topics": [x.strip() for x in self._val("topics").split(",") if x.strip()],
            "contact": {"name": self._val("name"), "role": self._val("role"),
                        "email": self._val("email"), "phone": self._val("phone")},
            "summary": self.query_one("#lf-summary", TextArea).text,
            "sponsor_class": self._radio("lf-kind", "kind-", "OTHER"),
            "stage": self._radio("lf-stage", "stage-", Stage.FLAGGED.value),
            "due": due,
        }
        self.dismiss(form)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "lf-save":
            self.action_save()
        else:
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.focus_next()

    def action_cancel(self) -> None:
        self.dismiss(None)


class LeadsScreen(Screen):
    BINDINGS = [
        ("escape,L,q", "back", "back"),
        ("a,plus", "add", "add lead"),
        ("enter", "edit", "edit"),
        ("e", "notes", "notes"),
        ("t", "due", "follow-up"),
        ("d", "delete", "drop"),
        ("m", "email", "outreach"),
        ("R", "reg", "reg", ),
        ("o", "open", "open link"),
        ("p", "print", "print"),
        ("j", "cursor_down", "", ),
        ("k", "cursor_up", "", ),
    ]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.rows: list[tuple[Study, Stage, str]] = []
        self.by_id: dict[str, tuple[Study, Stage, str]] = {}
        self.due: dict[str, str] = {}
        self.current_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="panes"):
            with Vertical(id="left") as left:
                left.border_title = "LEADS"
                table = DataTable(id="leads", cursor_type="row", zebra_stripes=False)
                table.add_column("●", width=2)
                table.add_column("ID", width=9)
                table.add_column("DUE", width=11)
                table.add_column("LEAD")
                yield table
            with VerticalScroll(id="center") as center:
                center.border_title = "LEAD"
                yield Static(id="detail")
        yield Static(id="statusbar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#topbar", Static).update(Text.from_markup(
            "[b #33ff88]STUDY//SCOUT · LEADS[/]  [#b58cff]off-registry prospects[/]   "
            "[dim]a add · enter edit · 1-9/C/x/n stage · t follow-up · e notes · m outreach · "
            "R reg · d drop · esc back[/]"))
        self.query_one("#center", VerticalScroll).can_focus = True
        self.reload()
        self.query_one("#leads", DataTable).focus()

    # ---- data ---- #
    def reload(self) -> None:
        self.rows = self.engine.leads()
        self.by_id = {s.id: (s, st, n) for s, st, n in self.rows}
        self.due = self.engine.due_map()
        table = self.query_one("#leads", DataTable)
        table.clear()
        for study, stage, _n in self.rows:
            d = self.due.get(study.id, "")
            label, color = due_label(d) if d else ("·", "#1f9e46")
            table.add_row(stage_glyph(stage), Text(study.nct, style="#b58cff"),
                          Text(label, style=color),
                          Text(study.title[:60], style="#aaffcc"), key=study.id)
        if self.rows:
            row = 0
            if self.current_id:
                for i, (s, _st, _n) in enumerate(self.rows):
                    if s.id == self.current_id:
                        row = i
                        break
            table.move_cursor(row=row)
            self.current_id = self.rows[row][0].id
            self.render_detail(self.current_id)
        else:
            self.current_id = None
            self.query_one("#detail", Static).update(Text.from_markup(
                "[#33ff66]No leads yet.[/]\n\n[#ffb000 b]a[/] adds one — a PI you met, a program, "
                "an act, a network that said \"call us\". No NCT needed.\n\n"
                "[dim]A lead rides the whole pipeline: stages, the K board, the S dossier "
                "(grouped by organization), m outreach, c chat, R reg, t follow-up.[/]"))
        self.update_statusbar()

    def render_detail(self, sid: str | None) -> None:
        if sid and sid in self.by_id:
            study, stage, notes = self.by_id[sid]
            self.query_one("#detail", Static).update(
                detail_view(study, stage, notes, due=self.due.get(sid, "")))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.current_id = event.row_key.value
        self.render_detail(self.current_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.current_id = event.row_key.value
        self.action_edit()

    def selected(self):
        return self.by_id.get(self.current_id) if self.current_id else None

    def update_statusbar(self) -> None:
        dated = sum(1 for s, _st, _n in self.rows if s.id in self.due)
        alive = sum(1 for _s, st, _n in self.rows
                    if st not in (Stage.CLOSED, Stage.DECLINED, Stage.UNFIT, Stage.UNAVAILABLE))
        self.query_one("#statusbar", Static).update(Text.from_markup(
            f"[#1f9e46]leads[/] {len(self.rows)}   [#1f9e46]alive[/] [#b58cff]{alive}[/]   "
            f"[#1f9e46]dated[/] {dated}"))

    def flash(self, text: str, style="#33ff88") -> None:
        self.query_one("#statusbar", Static).update(Text.from_markup(f"[{style}]{text}[/]"))

    # ---- nav ---- #
    def action_cursor_down(self) -> None:
        self.query_one("#leads", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#leads", DataTable).action_cursor_up()

    def action_back(self) -> None:
        self.dismiss()

    # ---- stage digits (same map as the deck) ---- #
    def on_key(self, event) -> None:
        from .main_screen import STAGE_KEYS
        if event.key in STAGE_KEYS and not isinstance(self.focused, (Input, TextArea)):
            sel = self.selected()
            if not sel:
                return
            study = sel[0]
            new = STAGE_KEYS[event.key]
            self.engine.set_stage(study.id, new)
            self.reload()
            self.flash(f"{study.nct} → {new.label}", "#ffb000")
            event.stop()

    # ---- actions ---- #
    def action_add(self) -> None:
        def saved(form):
            if not form:
                return
            study = self.engine.save_lead(form, stage=Stage(form["stage"]), due=form.get("due", ""))
            self.current_id = study.id
            self.reload()
            self.flash(f"{study.nct} added · {Stage(form['stage']).label} · on the deck, the board and "
                       f"the dossier", "#b58cff")
        self.app.push_screen(LeadForm(self.engine), saved)

    def action_edit(self) -> None:
        sel = self.selected()
        if not sel:
            return
        study, stage, _n = sel

        def saved(form):
            if not form:
                return
            self.engine.save_lead(form, nct=study.nct, stage=Stage(form["stage"]),
                                  due=form.get("due", ""))
            self.reload()
            self.flash(f"{study.nct} updated")
        self.app.push_screen(LeadForm(self.engine, study, stage, self.due.get(study.id, "")), saved)

    def action_notes(self) -> None:
        sel = self.selected()
        if not sel:
            return
        study, _stage, notes = sel

        def save(v):
            if v is not None:
                self.engine.set_notes(study.id, v)
                self.reload()
                self.flash("notes saved")
        self.app.push_screen(NotesModal(notes), save)

    def action_due(self) -> None:
        sel = self.selected()
        if sel:
            from .followup_screen import ask_due
            ask_due(self, self.engine, sel[0], self.reload)

    def action_delete(self) -> None:
        sel = self.selected()
        if not sel:
            return
        study = sel[0]

        def confirmed(yes):
            if yes:
                self.engine.delete_lead(study.id)
                self.current_id = None
                self.reload()
                self.flash(f"{study.nct} dropped", "#ff5555")
        self.app.push_screen(ConfirmModal(
            f"DROP LEAD · {study.nct}",
            f"[#33ff66]{study.title[:70]}[/]\n\nThis deletes the lead, its stage, notes and "
            f"checklist. NCT studies never need this (a search brings them back); a lead "
            f"you typed in is gone for good."), confirmed)

    def action_reg(self) -> None:
        sel = self.selected()
        if not sel:
            return
        from .reg import RegModal
        self.app.push_screen(RegModal(self.engine, sel[0]), lambda _r=None: self.reload())

    def action_open(self) -> None:
        sel = self.selected()
        if not sel:
            return
        if not sel[0].url:
            self.flash("no link on this lead — enter edits it", "#ffb000")
            return
        try:
            webbrowser.open(sel[0].url)
        except Exception:
            self.app.push_screen(TextModal("LINK", sel[0].url, copyable=True))

    def action_email(self) -> None:
        sel = self.selected()
        if not sel:
            return
        if not self.engine.ai_ready:
            self.flash("Wintermute dark — add a key (g → Connections)", "#ff5555")
            return
        self.flash("drafting outreach…", "#ffb000")
        self._email(sel[0], sel[2])

    def _email(self, study: Study, notes: str) -> None:
        self.run_worker(self._email_task(study, notes), exclusive=True, group="ai")

    async def _email_task(self, study: Study, notes: str) -> None:
        try:
            draft = await self.engine.outreach_email(study, notes)
        except Exception as exc:  # noqa: BLE001
            self.flash(f"draft failed: {exc}", "#ff5555")
            return
        to = study.best_contact().email
        mail_ctx = (to, f"Site interest — {study.title[:40]}", self.engine.cfg.get("ui.mail_command", ""),
                    self.engine.cfg.get("ui.mail_mode", "mailto"))
        self.app.push_screen(TextModal(f"OUTREACH · {study.nct}", draft, amber=True,
                                       copyable=True, mail=mail_ctx))
        self.flash("draft ready · c copy · o open in mail")

    def action_print(self) -> None:
        from datetime import datetime

        from .export import export_text
        lines = [f"STUDY//SCOUT · LEADS · {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
        for study, stage, notes in self.rows:
            c = study.best_contact()
            lines += [f"• {study.nct} · {stage.label}" +
                      (f" · follow-up {self.due[study.id]}" if study.id in self.due else ""),
                      f"  {study.title}", f"  org: {study.sponsor or '—'}"
                      f"  [{SPONSOR_CLASS_LABEL.get(study.sponsor_class, study.sponsor_class or '?')}]"]
            if c.render() != "—":
                lines.append(f"  contact: {c.render()}")
            if study.conditions:
                lines.append(f"  topics: {', '.join(study.conditions)}")
            if study.link:
                lines.append(f"  {study.link}")
            if notes:
                lines.append(f"  notes: {notes}")
            if study.summary:
                lines.append(f"  {study.summary[:300]}")
            lines.append("")
        export_text(self.app, "leads", "\n".join(lines), prefix="leads")

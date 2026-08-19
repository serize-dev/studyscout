"""Sponsors — the BD lens. One row per relationship, not per NCT.

The kanban keeps the receipts; this screen is where the outreach actually
happens: who they are, their book of trials in your net, the door (contacts
deduped across trials), and your history with them.
"""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from ..models import SPONSOR_CLASS_LABEL, SponsorDossier
from .modals import NotesModal, TextModal
from .sorting import SPONSOR_SORTS, SortModal, apply_sort, sort_arrow
from .widgets import STAGE_COLOR, _STATUS_SHORT


def _ago(ts: datetime | None) -> str:
    if not ts:
        return "—"
    days = (datetime.now() - ts).days
    return "today" if days <= 0 else f"{days}d"


def dossier_view(d: SponsorDossier) -> Text:
    t = Text()
    t.append(d.name + "\n", style="bold #ffb000")
    t.append(f"[{SPONSOR_CLASS_LABEL.get(d.sponsor_class, d.sponsor_class or '?')}]",
             style="bold #00ff88" if d.is_industry else "#33ff66")
    t.append(f"   {d.n_trials} trials in your net · {d.recruiting} recruiting · "
             f"phases {d.phases}\n", style="#33ff66")
    t.append("last touch  ", style="#1f9e46")
    t.append(_ago(d.last_touch) + "\n", style="#ffb000" if d.last_touch else "#555")

    contacts = d.contacts()
    if contacts:
        t.append("\n► THE DOOR  (contacts across their trials, deduped)\n", style="bold #00ff88")
        for c in contacts:
            t.append(f"  {c.render()}\n", style="#aaffcc" if c.has_direct else "#33ff66")

    t.append("\ntheir book\n", style="#1f9e46")
    for s, st, n in d.rows[:14]:
        t.append(f"  {st.glyph} ", style=f"bold {STAGE_COLOR.get(st, '#33ff66')}")
        t.append(f"{s.nct}", style="#33ccff")
        t.append(f" {s.phase_str}", style="#33ff88")
        short, color = _STATUS_SHORT.get(s.status, (s.status[:4].title(), "#2bbf5a"))
        t.append(f" {short}", style=color)
        t.append(f"  {s.title[:56]}\n", style="#aaffcc")
        if n:
            t.append(f"      └ {n[:70]}\n", style="#ffb000")
    if d.n_trials > 14:
        t.append(f"  … +{d.n_trials - 14} more\n", style="#1f9e46")

    if d.notes:
        t.append("\nsponsor notes\n", style="#1f9e46")
        t.append(d.notes + "\n", style="#ffb000")

    if d.intel:
        t.append(f"\n◈ EXPANDED DOSSIER  (Wintermute · web · {d.intel_at[:10] or '?'})\n",
                 style="bold #00ff88")
        t.append(d.intel + "\n", style="#aaffcc")
    else:
        t.append("\n[W] expand this dossier — Wintermute hunts the live web "
                 "(pipeline news · signals · who to reach)\n", style="#1f9e46")
    return t


class SponsorScreen(Screen):
    BINDINGS = [
        Binding("escape,q", "back", "back"),
        Binding("s", "sort", "sort"),
        Binding("m", "email", "pitch sponsor"),
        Binding("W", "enrich", "web intel"),
        Binding("e", "notes", "notes"),
        Binding("z,enter", "zoom", "dossier", show=False),
        Binding("o", "open_first", "open", show=False),
        Binding("slash", "textfilter", "find", show=False),
        Binding("j", "cursor_down", "", show=False),
        Binding("k", "cursor_up", "", show=False),
    ]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.dossiers: list[SponsorDossier] = []
        self.view: list[SponsorDossier] = []
        self.by_id: dict[str, SponsorDossier] = {}
        self.sort_key = "bd"
        self.sort_flipped = False
        self.text_filter = ""
        self.current_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="panes"):
            with Vertical(id="left") as left:
                left.border_title = "SPONSORS"
                table = DataTable(id="sponsors", cursor_type="row", zebra_stripes=False)
                table.add_column("CLS", width=9)
                table.add_column("TRL", width=3)
                table.add_column("REC", width=3)
                table.add_column("PIPE", width=4)
                table.add_column("@", width=2)
                table.add_column("LAST", width=5)
                table.add_column("SPONSOR")
                yield table
            with VerticalScroll(id="center") as center:
                center.border_title = "DOSSIER"
                yield Static(id="detail")
        yield Static(id="statusbar")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#topbar", Static).update(Text.from_markup(
            "[b #33ff88]SPONSORS[/]  [#ffb000]the BD lens[/]   "
            "[dim]m pitch · W web intel · e notes · s sort · enter dossier · esc back[/]"))
        self.query_one("#center", VerticalScroll).can_focus = True
        self.reload()
        self.query_one("#sponsors", DataTable).focus()

    # ---- data / render ---- #
    def reload(self) -> None:
        self.dossiers = self.engine.dossiers()
        self.by_id = {d.id: d for d in self.dossiers}
        self.apply_view()

    def apply_view(self) -> None:
        view = self.dossiers
        if self.text_filter:
            q = self.text_filter.lower()
            view = [d for d in view
                    if q in f"{d.name} {' '.join(d.conditions)}".lower()]
        view = apply_sort(view, SPONSOR_SORTS, self.sort_key, self.sort_flipped)
        self.view = view
        self.populate()

    def populate(self) -> None:
        table = self.query_one("#sponsors", DataTable)
        table.clear()
        for d in self.view:
            cls = SPONSOR_CLASS_LABEL.get(d.sponsor_class, d.sponsor_class or "?")
            cls_cell = Text(cls[:9], style="bold #00ff88" if d.is_industry else "#2bbf5a")
            at = Text("@", style="bold #00ff88") if d.has_contact else Text("·", style="#1f9e46")
            pipe = Text(str(d.in_pipeline) if d.in_pipeline else "·",
                        style="bold #ffb000" if d.in_pipeline else "#555")
            table.add_row(
                cls_cell, Text(str(d.n_trials), style="#33ff66"),
                Text(str(d.recruiting), style="bold #33ff88" if d.recruiting else "#555"),
                pipe, at, Text(_ago(d.last_touch), style="#ffb000" if d.last_touch else "#555"),
                Text(d.name[:60], style="#aaffcc"), key=d.id,
            )
        if self.view:
            table.move_cursor(row=0)
            self.current_id = self.view[0].id
            self.render_detail(self.current_id)
        else:
            self.query_one("#detail", Static).update(
                Text("No sponsors match. Press r on the deck to search first.", style="#1f9e46"))
        self.update_statusbar()

    def render_detail(self, did: str | None) -> None:
        if did and did in self.by_id:
            self.query_one("#detail", Static).update(dossier_view(self.by_id[did]))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.current_id = event.row_key.value
        self.render_detail(self.current_id)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on the table (the table eats the key before screen bindings).
        self.current_id = event.row_key.value
        self.action_zoom()

    def selected(self) -> SponsorDossier | None:
        return self.by_id.get(self.current_id) if self.current_id else None

    def update_statusbar(self) -> None:
        arrow = sort_arrow(SPONSOR_SORTS, self.sort_key, self.sort_flipped)
        industry = sum(1 for d in self.view if d.is_industry)
        tf = f" [#00ff88]/{self.text_filter}[/]" if self.text_filter else ""
        self.query_one("#statusbar", Static).update(Text.from_markup(
            f"[#1f9e46]sponsors[/] {len(self.view)}/{len(self.dossiers)}{tf}   "
            f"[#1f9e46]industry[/] [#00ff88]{industry}[/]   "
            f"[#1f9e46]sort[/] [#ffb000]{self.sort_key}{arrow}[/]"))

    def flash(self, text: str, style="#33ff88") -> None:
        self.query_one("#statusbar", Static).update(Text.from_markup(f"[{style}]{text}[/]"))

    # ---- nav ---- #
    def action_cursor_down(self) -> None:
        self.query_one("#sponsors", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#sponsors", DataTable).action_cursor_up()

    def action_back(self) -> None:
        self.dismiss()

    # ---- actions ---- #
    def action_sort(self) -> None:
        def picked(res):
            if res:
                self.sort_key, self.sort_flipped = res
                self.apply_view()
        self.app.push_screen(SortModal(SPONSOR_SORTS, self.sort_key, self.sort_flipped), picked)

    def action_textfilter(self) -> None:
        def got(v):
            if v is not None:
                self.text_filter = v.strip()
                self.apply_view()
        self.app.push_screen(NotesModal(self.text_filter), got)

    def action_zoom(self) -> None:
        d = self.selected()
        if d:
            self.app.push_screen(TextModal(f"DOSSIER · {d.name[:40]}", dossier_view(d)))

    def action_open_first(self) -> None:
        d = self.selected()
        if d and d.rows:
            import webbrowser
            try:
                webbrowser.open(d.rows[0][0].url)
                self.flash(f"opened {d.rows[0][0].nct}")
            except Exception:
                pass

    def action_notes(self) -> None:
        d = self.selected()
        if not d:
            return

        def save(v):
            if v is None:
                return
            self.engine.set_sponsor_notes(d.name, v)
            d.notes = v
            self.render_detail(d.id)
            self.flash("sponsor notes saved")
        self.app.push_screen(NotesModal(d.notes), save)

    def action_email(self) -> None:
        d = self.selected()
        if not d:
            return
        if not self.engine.ai_ready:
            self.flash("Wintermute dark — add a key (g → Connections)", "#ff5555")
            return
        self.flash(f"drafting the consolidated pitch to {d.name[:30]}…", "#ffb000")
        self._email(d)

    def action_enrich(self) -> None:
        d = self.selected()
        if not d:
            return
        if not self.engine.ai_ready:
            self.flash("Wintermute dark — add a key (g → Connections)", "#ff5555")
            return
        self.flash(f"Wintermute is researching {d.name[:34]} on the live web… (uses tokens)",
                   "#ffb000")
        self._enrich(d)

    @work(exclusive=True, group="ai")
    async def _enrich(self, d: SponsorDossier) -> None:
        try:
            intel = await self.engine.enrich_sponsor(d)
        except Exception as exc:  # noqa: BLE001
            self.flash(f"intel hunt failed: {exc}", "#ff5555")
            return
        if not intel:
            self.flash("the web hunt came back empty — try again later", "#ffb000")
            return
        self.reload()
        self.flash(f"expanded dossier ready — {d.name[:32]} · enter to read", "#33ff88")

    @work(exclusive=True, group="ai")
    async def _email(self, d: SponsorDossier) -> None:
        try:
            draft = await self.engine.sponsor_pitch(d)
        except Exception as exc:  # noqa: BLE001
            self.flash(f"draft failed: {exc}", "#ff5555")
            return
        to = next((c.email for c in d.contacts() if c.email), None)
        mail_ctx = (to, f"Site interest — {d.name}", self.engine.cfg.get("ui.mail_command", ""),
                    self.engine.cfg.get("ui.mail_mode", "mailto"))
        self.app.push_screen(TextModal(f"PITCH · {d.name[:36]}", draft, amber=True,
                                       copyable=True, mail=mail_ctx))
        self.flash("pitch ready · c copy · o open in mail")

"""The cockpit: studies | detail | Wintermute, with the BD pipeline."""

from __future__ import annotations

import webbrowser

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Static, TextArea

from ..models import KANBAN_ORDER, Stage, Study
from .chat import ChatScreen
from .filters_screen import FiltersScreen
from .modals import ConfirmModal, HelpModal, NotesModal, TextModal
from .widgets import (
    STAGE_COLOR, contact_cell, detail_view, phase_cell, sites_cell, stage_glyph,
    status_cell, title_cell,
)
from .wintermute import WintermutePane

STAGE_KEYS = {
    "1": Stage.FLAGGED, "2": Stage.CONTACTED, "3": Stage.WAITING, "4": Stage.REPLIED,
    "5": Stage.MEETING, "6": Stage.WON, "7": Stage.DECLINED, "8": Stage.CLOSED,
    "9": Stage.FUTURE, "0": Stage.NEW, "x": Stage.UNAVAILABLE,
    "n": Stage.UNFIT,           # v1.8.0 — screened it, not for us (your call)
    "C": Stage.CONDUCTING,      # shift+c — lowercase c stays the WM chat
}


class MainScreen(Screen):
    BINDINGS = [
        Binding("f1", "help", "help"),
        Binding("f", "filters", "filters"),
        Binding("r", "refresh", "search"),
        Binding("c", "chat", "ask WM"),
        Binding("m", "email", "outreach"),
        Binding("z", "zoom", "zoom"),
        Binding("K", "kanban", "kanban"),
        Binding("escape", "escape", "menu"),
        Binding("q", "quit", "quit"),
        Binding("s", "sort", "sort", show=False),
        Binding("b", "briefing", "briefing", show=False),
        Binding("R", "reg", "reg handoff", show=False),
        Binding("S", "sponsors", "sponsors"),
        Binding("e", "notes", "notes", show=False),
        Binding("g", "settings", "menu", show=False),
        Binding("tab", "focus_toggle", "focus", show=False),
        Binding("backslash", "toggle_wm", "wm", show=False),
        Binding("o,enter", "open", "open", show=False),
        Binding("slash", "textfilter", "find", show=False),
        Binding("j", "cursor_down", "", show=False),
        Binding("k", "cursor_up", "", show=False),
        Binding("a", "stale_toggle", "stale", show=False),
        # v1.6.0 — fold-chat-to-email works from ANY pane (deck/detail too);
        # the ChatInput still consumes ctrl+e itself when it has focus.
        Binding("ctrl+e", "compose_from_chat", "email from chat", show=False),
    ]

    # deck column index → sort key (click a header to sort by it; again flips)
    COLUMN_SORT = {0: "stage", 1: "phase", 2: "status", 3: "sites", 4: "contact", 5: "title"}

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.rows: list[tuple[Study, Stage, str]] = []
        self.view: list[tuple[Study, Stage, str]] = []
        self.by_id: dict[str, tuple[Study, Stage, str]] = {}
        self.text_filter = ""
        # v1.8.0 — the sort SURVIVES restarts. Before: every launch silently reset
        # to "start" no matter what the filters panel said ("won't autosort by
        # sites"), and a header click on an already-active column flipped it to
        # ascending ("sorts back down to the lowest # of sites").
        self.sort_key, self.sort_flipped = self._load_sort()
        self.current_id: str | None = None
        self.stale: set[str] = set()
        self.show_stale = False

    _SORT_KEYS = ("start", "status", "phase", "enrollment", "sites", "contact",
                  "sponsor", "stage", "title")

    def _load_sort(self) -> tuple[str, bool]:
        cfg = self.engine.cfg
        key = str(cfg.get("ui.sort_key", "") or "")
        if key not in self._SORT_KEYS:
            key = str(cfg.get("filters.sort", "start"))
            if key not in self._SORT_KEYS:
                key = "start"
            return key, False
        return key, bool(cfg.get("ui.sort_flipped", False))

    def set_sort(self, key: str, flipped: bool, announce: bool = False) -> None:
        """Single chokepoint: every sort change lands here, gets persisted, re-sorts."""
        self.sort_key, self.sort_flipped = key, flipped
        try:
            self.engine.cfg.set("ui.sort_key", key)
            self.engine.cfg.set("ui.sort_flipped", flipped)
            self.engine.cfg.save()
        except Exception:
            pass  # a read-only profile must never break sorting
        self.apply_filter()
        if announce:
            from .sorting import STUDY_SORTS, sort_arrow
            spec = next((s for s in STUDY_SORTS if s.key == key), None)
            arrow = sort_arrow(STUDY_SORTS, key, flipped)
            natural = spec.reverse == (spec.reverse ^ flipped) if spec else True
            how = spec.label if (spec and natural) else f"{key} — reversed"
            self.flash(f"sort {key}{arrow}  {how}   (same column again flips)", "#ffb000")

    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Horizontal(id="panes"):
            with Vertical(id="left") as left:
                left.border_title = "STUDIES"
                table = DataTable(id="listings", cursor_type="row", zebra_stripes=False)
                table.add_column("●", width=2)
                table.add_column("PHASE", width=6)
                table.add_column("ST", width=4)
                table.add_column("SITE", width=4)
                table.add_column("@", width=2)
                table.add_column("TITLE")
                yield table
            with VerticalScroll(id="center") as center:
                center.border_title = "DETAIL"
                yield Static(id="detail")
            if self.engine.cfg.get("ui.wintermute_pane", True):
                yield WintermutePane(self.engine.consigliere)
        yield Static(id="statusbar")
        yield Footer()

    @property
    def wm_pane(self):
        try:
            return self.query_one("#wm", WintermutePane)
        except Exception:
            return None

    def on_mount(self) -> None:
        self.reload()
        self.query_one("#center", VerticalScroll).can_focus = True
        self.query_one("#listings", DataTable).focus()

    def on_screen_resume(self) -> None:
        if self.focused is None:
            try:
                self.query_one("#listings", DataTable).focus()
            except Exception:
                pass
        # First landing of the day → morning briefing (deferred so we only
        # fire once the deck is actually the visible screen).
        self.call_after_refresh(self._maybe_briefing)

    # ---- data / render ---- #
    def reload(self) -> None:
        self.rows = self.engine.load()
        self.by_id = {s.id: (s, st, n) for s, st, n in self.rows}
        try:
            self.stale = self.engine.store.stale_ids()
        except Exception:
            self.stale = set()
        self.apply_filter()
        self.update_topbar()

    def apply_filter(self) -> None:
        from .sorting import STUDY_SORTS, apply_sort
        view = self.rows
        if self.stale and not self.show_stale:
            view = [r for r in view if r[0].id not in self.stale]
        if self.text_filter:
            q = self.text_filter.lower()
            view = [r for r in view
                    if q in f"{r[0].title} {r[0].sponsor} {r[0].nct} {' '.join(r[0].conditions)}".lower()]
        view = apply_sort(view, STUDY_SORTS, self.sort_key, self.sort_flipped)
        # Dead deals sink regardless of the chosen sort (stable, so order holds within).
        view = sorted(view, key=lambda r: (r[1] in (Stage.CLOSED, Stage.DECLINED, Stage.UNFIT, Stage.UNAVAILABLE),))
        self.view = view
        self.populate()

    def populate(self) -> None:
        table = self.query_one("#listings", DataTable)
        table.clear()
        for study, stage, _notes in self.view:
            table.add_row(stage_glyph(stage), phase_cell(study), status_cell(study),
                          sites_cell(study), contact_cell(study), title_cell(study), key=study.id)
        if self.view:
            # v1.5.1: keep the cursor on the study the operator was working —
            # jumping to row 0 after every stage change made flags look lost.
            row = 0
            if self.current_id:
                for i, (study, _st, _n) in enumerate(self.view):
                    if study.id == self.current_id:
                        row = i
                        break
            table.move_cursor(row=row)
            self.current_id = self.view[row][0].id
            self.render_detail(self.current_id)
        else:
            self.query_one("#detail", Static).update(
                Text("No studies. Press f to set filters, then r to search.", style="#1f9e46"))
        self.update_statusbar()

    def render_detail(self, sid: str | None) -> None:
        if not sid or sid not in self.by_id:
            return
        study, stage, notes = self.by_id[sid]
        self.query_one("#detail", Static).update(detail_view(study, stage, notes))
        wm = self.wm_pane
        if wm:
            wm.set_study(study, notes)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self.current_id = event.row_key.value
        self.render_detail(self.current_id)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        key = self.COLUMN_SORT.get(event.column_index)
        if not key:
            return
        flipped = (not self.sort_flipped) if key == self.sort_key else False
        self.set_sort(key, flipped, announce=True)

    def action_stale_toggle(self) -> None:
        self.show_stale = not self.show_stale
        self.apply_filter()
        if self.show_stale:
            self.flash(f"showing {len(self.stale)} stale rows — not in the latest catch", "#ffb000")
        else:
            self.flash(f"{len(self.stale)} stale rows hidden — `a` shows them", "#33ff88")

    def selected(self):
        return self.by_id.get(self.current_id) if self.current_id else None

    # ---- bars ---- #
    def update_topbar(self) -> None:
        from .. import __version__
        prov = self.engine.cfg.provider()
        model = self.engine.brain.model.split("/")[-1]
        ai = (f"[#33ff88]Wintermute●[/] [dim]{prov}:{model}[/]" if self.engine.ai_ready
              else "[#ff5555]Wintermute○[/]")
        self.query_one("#topbar", Static).update(Text.from_markup(
            f"[b #33ff88]STUDY//SCOUT[/] [dim]v{__version__}[/]   [#ffb000]bd intel[/]   {ai}   "
            f"[dim]f filters · r search · c ask[/]"))

    def update_statusbar(self) -> None:
        from .sorting import STUDY_SORTS, sort_arrow
        c = self.engine.counts()
        seg = "  ".join(f"[dim]{st.label} {c.get(st,0)}[/]"
                        for st in (Stage.NEW, Stage.FLAGGED, Stage.CONTACTED, Stage.WAITING,
                                   Stage.REPLIED, Stage.MEETING, Stage.WON, Stage.CONDUCTING,
                                   Stage.FUTURE))
        tf = f" [#00ff88]/{self.text_filter}[/]" if self.text_filter else ""
        arrow = sort_arrow(STUDY_SORTS, self.sort_key, self.sort_flipped)
        try:
            due = self.engine.followups_due()
        except Exception:
            due = 0
        nudge = (f"   [#ffb000]⏰ {due} sponsor{'s' if due != 1 else ''} quiet (b)[/]"
                 if due else "")
        stale = ""
        if self.stale:
            stale = (f"   [#ffb000]stale shown (a hides)[/]" if self.show_stale
                     else f"   [dim]{len(self.stale)} stale hidden (a)[/]")
        self.query_one("#statusbar", Static).update(Text.from_markup(
            f"[#1f9e46]shown[/] {len(self.view)}/{len(self.rows)}{tf}   "
            f"[#1f9e46]sort[/] [#ffb000]{self.sort_key}{arrow}[/]    {seg}{nudge}{stale}"))

    def flash(self, text: str, style="#33ff88") -> None:
        self.query_one("#statusbar", Static).update(Text.from_markup(f"[{style}]{text}[/]"))

    # ---- nav / stage ---- #
    def action_cursor_down(self) -> None:
        self.query_one("#listings", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#listings", DataTable).action_cursor_up()

    def on_key(self, event) -> None:
        # v1.5.1: stage digits work from ANY pane — a stray click on the detail
        # pane used to silently kill them ("can't flag anything"). Only a
        # focused text input (Wintermute chat, etc.) keeps its keystrokes.
        if event.key in STAGE_KEYS and not isinstance(self.focused, (Input, TextArea)):
            sel = self.selected()
            if not sel:
                self.flash("no study selected — move the cursor first", "#ffb000")
                event.stop()
                return
            study, _old, notes = sel
            new = STAGE_KEYS[event.key]
            self.engine.set_stage(study.id, new)
            self.by_id[study.id] = (study, new, notes)
            self.apply_filter()
            self.flash(f"{study.nct} → {new.label}"
                       + ("  ·  now on the PIPELINE board (K)" if new not in (Stage.NEW,) else ""),
                       "#ffb000")
            event.stop()

    def action_focus_toggle(self) -> None:
        center = self.query_one("#center", VerticalScroll)
        table = self.query_one("#listings", DataTable)
        wm = self.wm_pane
        if self.focused is table:
            center.focus()
        elif self.focused is center and wm and not wm.has_class("hidden"):
            wm.focus_input()
        else:
            table.focus()

    def action_toggle_wm(self) -> None:
        wm = self.wm_pane
        if wm:
            wm.toggle_class("hidden")

    def action_compose_from_chat(self) -> None:
        wm = self.wm_pane
        if not wm or wm.has_class("hidden"):
            self.flash("Wintermute pane is hidden — \\ shows it", "#ffb000")
            return
        if not wm.history:
            self.flash("chat with Wintermute first, then ctrl+e folds it into an email", "#ffb000")
            return
        wm._compose_email()

    def action_escape(self) -> None:
        if isinstance(self.focused, (Input, TextArea)):
            self.query_one("#listings", DataTable).focus()
            return
        self.action_settings()

    # ---- morning briefing (the BD ritual) ---- #
    def action_briefing(self) -> None:
        self._show_briefing(auto=False)

    def _maybe_briefing(self) -> None:
        if self.app.screen is not self:
            return
        from datetime import date
        if self.engine.store.get_meta("last_briefing_date") == date.today().isoformat():
            return
        self._show_briefing(auto=True)

    def _show_briefing(self, auto: bool = False) -> None:
        from datetime import date
        b = self.engine.briefing()
        if auto and not (b["new_count"] or b["flips"] or b["quiet"] or b["meetings"]
                         or b["reg"] or b.get("future")):
            return  # nothing to say — don't interrupt
        self.engine.store.set_meta("last_briefing_date", date.today().isoformat())

        t = Text()

        def line(s: str, style: str = "#33ff66") -> None:
            t.append(s + "\n", style=style)

        if b["new_count"]:
            line(f"◆ {b['new_count']} new trials in your net since last visit", "#00ff88")
            for d in b["known_new"]:
                line(f"   ★ {d['sponsor'][:34]} — a sponsor you've worked posted {d['nct']}",
                     "bold #ffb000")
        else:
            line("◆ nothing new in your net since last visit", "#1f9e46")
        if b["flips"]:
            line("\n⇄ STATUS FLIPS  (the excuse-to-email feed)", "bold #ffb000")
            for d in b["flips"]:
                line(f"   {d['nct']} · {d['sponsor'][:26]} · {d['detail']}")
        if b["quiet"]:
            line(f"\n⏰ QUIET RELATIONSHIPS  (≥ {b['nudge_days']}d in Contacted/Waiting)",
                 "bold #ffb000")
            for name, days, n in b["quiet"]:
                line(f"   {days:>2}d  {name[:34]}  ({n} trial{'s' if n != 1 else ''} pending)")
        if b.get("future"):
            line(f"\n⟳ FUTURE OUTREACH DUE  (parked ≥ {b['future_days']}d — they said call back)",
                 "bold #b58cff")
            for name, days, n in b["future"]:
                line(f"   {days:>3}d  {name[:34]}  ({n} trial{'s' if n != 1 else ''} parked)")
        if b["reg"]:
            line("\n▤ REG HANDOFF — startup paperwork open  (R on the study)", "bold #ffb000")
            for study, done, total in b["reg"]:
                line(f"   {done}/{total}  {study.nct} · {study.sponsor[:30]}")

        line("\n▶ TODAY'S TOP 3", "bold #ffb000")
        n = 1
        for study, _st, _n2 in b["meetings"]:
            if n > 3:
                break
            line(f"   {n}. PREP — meeting on {study.nct} · {study.sponsor[:28]}")
            n += 1
        for name, days, _cnt in b["quiet"]:
            if n > 3:
                break
            line(f"   {n}. FOLLOW UP — {name[:32]} ({days}d silent · S then m)")
            n += 1
        for d in b["pitch"]:
            if n > 3:
                break
            line(f"   {n}. PITCH — {d.name[:30]} · {d.recruiting} recruiting · industry · untouched")
            n += 1
        if n == 1:
            line("   deck's empty — press r to search ClinicalTrials.gov", "#1f9e46")

        t.append("\n")
        line("b reopens this · S sponsors · K kanban", "dim")
        self.app.push_screen(TextModal("[#ffb000 b]MORNING BRIEFING · BD INTEL[/]", t, amber=True))

    # ---- actions ---- #
    def action_reg(self) -> None:
        sel = self.selected()
        if not sel:
            return
        from .reg import RegModal
        study = sel[0]

        def closed(res):
            if res:
                done, total = res
                color = "#00ff88" if done == total else "#ffb000"
                self.flash(f"reg handoff · {study.nct} · {done}/{total} done", color)
        self.app.push_screen(RegModal(self.engine, study), closed)

    def action_sort(self) -> None:
        from .sorting import STUDY_SORTS, SortModal

        def picked(res):
            if res:
                self.set_sort(*res, announce=True)
                self.apply_filter()
        self.app.push_screen(SortModal(STUDY_SORTS, self.sort_key, self.sort_flipped), picked)

    def action_sponsors(self) -> None:
        from .sponsors import SponsorScreen
        self.app.push_screen(SponsorScreen(self.engine), lambda _=None: self.reload())

    def action_help(self) -> None:
        self.app.push_screen(HelpModal())

    def action_settings(self) -> None:
        from .launcher import LauncherScreen
        self.app.push_screen(LauncherScreen(self.engine), lambda _=None: self.reload())

    def action_kanban(self) -> None:
        from .kanban import KanbanScreen
        self.app.push_screen(KanbanScreen(self.engine, text_filter=self.text_filter))

    def action_open(self) -> None:
        sel = self.selected()
        if not sel:
            return
        try:
            webbrowser.open(sel[0].url)
            self.flash(f"opened {sel[0].nct}")
        except Exception:
            self.app.push_screen(TextModal("LINK", sel[0].url, copyable=True))

    def action_textfilter(self) -> None:
        def got(v):
            if v is not None:
                self.text_filter = v.strip()
                self.apply_filter()
        self.app.push_screen(NotesModal(self.text_filter), got)

    def action_notes(self) -> None:
        sel = self.selected()
        if not sel:
            return
        study, stage, notes = sel

        def save(v):
            if v is None:
                return
            self.engine.set_notes(study.id, v)
            self.by_id[study.id] = (study, stage, v)
            self.render_detail(study.id)
            self.flash("notes saved")
        self.app.push_screen(NotesModal(notes), save)

    def action_zoom(self) -> None:
        ids = set()
        n = self.focused
        while n is not None:
            if getattr(n, "id", None):
                ids.add(n.id)
            n = n.parent
        if ids & {"wm", "wm-input", "wm-log", "wm-ctx"}:
            self.action_chat()
            return
        if ids & {"center", "detail"}:
            sel = self.selected()
            if sel:
                study, stage, notes = sel
                self.app.push_screen(TextModal(f"STUDY · {study.nct}",
                                               detail_view(study, stage, notes)))
            return
        # listings pane → the full table: every column, header-click sorting
        from .zoom import StudiesModal

        def landed(res):
            sid, key, flipped = (res if isinstance(res, tuple) else (res, None, None))
            if key and (key in self._SORT_KEYS) and (key, flipped) != (self.sort_key, self.sort_flipped):
                self.set_sort(key, flipped)  # v1.8.0 — zoom sort flows back to the deck
            if not sid:
                return
            for i, (study, _st, _n) in enumerate(self.view):
                if study.id == sid:
                    self.query_one("#listings", DataTable).move_cursor(row=i)
                    break
        self.app.push_screen(StudiesModal(self.view, self.sort_key, self.sort_flipped), landed)

    def action_chat(self) -> None:
        sel = self.selected()
        study = sel[0] if sel else None
        notes = sel[2] if sel else ""
        wm = self.wm_pane
        history = wm.history if wm else None
        if wm and study:
            wm.set_study(study, notes)

        def after(_=None):
            if wm:
                wm.rebuild_log()
        self.app.push_screen(ChatScreen(self.engine.consigliere, study, notes, history=history), after)

    # ---- workers ---- #
    def action_filters(self) -> None:
        def done(run):
            if run:
                # the TARGET panel's sort choice drives the deck order too —
                # otherwise the radio is theater (fetch order dies at upsert)
                chosen = str(self.engine.cfg.get("filters.sort", "start"))
                if chosen in ("start", "sites", "enrollment"):
                    self.set_sort(chosen, False)
                self.action_refresh()
        self.app.push_screen(FiltersScreen(self.engine), done)

    def action_refresh(self) -> None:
        self.flash("querying ClinicalTrials.gov…", "#ffb000")
        self._refresh()

    @work(exclusive=True, group="net")
    async def _refresh(self) -> None:
        total, new, errors = await self.engine.refresh()
        self.reload()
        msg = f"found {total} studies · {new} new"
        if errors:
            msg += f" · {len(errors)} errors"
        self.flash(msg, "#33ff88")

    def action_email(self) -> None:
        sel = self.selected()
        if not sel:
            return
        if not self.engine.ai_ready:
            self.flash("Wintermute dark — add a key (g → Connections)", "#ff5555")
            return
        self.flash("drafting outreach…", "#ffb000")
        self._email(sel[0], sel[2])

    @work(exclusive=True, group="ai")
    async def _email(self, study: Study, notes: str) -> None:
        try:
            draft = await self.engine.outreach_email(study, notes)
        except Exception as exc:  # noqa: BLE001
            self.flash(f"draft failed: {exc}", "#ff5555")
            return
        to = study.best_contact().email
        mail_ctx = (to, f"Site interest — {study.nct}", self.engine.cfg.get("ui.mail_command", ""),
                    self.engine.cfg.get("ui.mail_mode", "mailto"))
        self.app.push_screen(TextModal(f"OUTREACH · {study.nct}", draft, amber=True,
                                       copyable=True, mail=mail_ctx))
        self.flash("draft ready · c copy · o open in mail")

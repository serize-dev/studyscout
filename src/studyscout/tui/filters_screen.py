"""FILTERS — the ClinicalTrials.gov search panel (his TARGET / STATUS terminal)."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RadioButton, RadioSet, SelectionList, Static
from textual.widgets.selection_list import Selection

STATUS_OPTS = [("Recruiting", "RECRUITING"), ("Not yet recruiting", "NOT_YET_RECRUITING"),
               ("Active, not recruiting", "ACTIVE_NOT_RECRUITING"),
               ("Enrolling by invitation", "ENROLLING_BY_INVITATION"), ("Completed", "COMPLETED")]
PHASE_OPTS = [("Early Phase 1", "0"), ("Phase 1", "1"), ("Phase 2", "2"),
              ("Phase 3", "3"), ("Phase 4", "4"), ("N/A (device/behavioral)", "na")]
AGE_OPTS = [("Child (0–17, incl. neonatal)", "child"), ("Adult (18–64)", "adult"), ("Older (65+)", "older")]
FUNDER_OPTS = [("Industry", "industry"), ("NIH", "nih"), ("Federal", "fed"),
               ("Academic / other", "other"), ("Network", "network")]

# Single-choice groups — inline radio sets, never overlay dropdowns (a Select's
# popup used to open on top of the Phase/Funder checkbox lists).
RADIO_GROUPS: dict[str, tuple[str, list[tuple[str, str]], str]] = {
    "study_type": ("Type", [("Interventional", "int"), ("Observational", "obs"),
                            ("All types", "")], "int"),
    "country": ("Where", [("USA only", "United States"),
                          ("International / anywhere", "")], "United States"),
    "site_mode": ("Sites", [("Any # sites", "any"), ("Multi-site (≥2)", "multi"),
                            ("Single-site", "single")], "any"),
    "sort": ("Sort deck by", [("Newest", "start"), ("Most sites", "sites"),
                              ("Biggest enroll", "enrollment")], "start"),
}


class FiltersScreen(ModalScreen):
    BINDINGS = [("escape", "cancel", "close"), ("ctrl+s", "run", "search")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def _f(self, key, default=None):
        return self.engine.cfg.get(f"filters.{key}", default)

    @staticmethod
    def _net_banner(keyword: str) -> Text:
        """The seeded-net trap, made visible (v1.4.0): a live keyword silently
        ANDs into every search — the 'covid-19 yields pediatric studies' bug."""
        if keyword.strip():
            n = keyword.count(" OR ") + 1
            return Text.from_markup(
                f"[#ffb000]⚠ keyword net ACTIVE ({n} terms) — every search is "
                f"Condition AND net. Clear the box above to search by condition alone.[/]")
        return Text.from_markup("[dim]no keyword net — searches use Condition alone[/]")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "keyword":
            try:
                self.query_one("#net-banner", Static).update(self._net_banner(event.value))
            except Exception:
                pass

    def action_new_hunt(self) -> None:
        """Clean slate in place: clear the poisonable filters, keep the plumbing."""
        for iid in ("#condition", "#keyword", "#exclude"):
            try:
                self.query_one(iid, Input).value = ""
            except Exception:
                pass
        for lid in ("#phases", "#ages", "#funders"):
            try:
                self.query_one(lid, SelectionList).deselect_all()
            except Exception:
                pass
        try:
            self.query_one("#net-banner", Static).update(self._net_banner(""))
        except Exception:
            pass
        self.notify("clean slate — set a condition (and any filters) then SEARCH",
                    severity="information")

    def on_resize(self, event) -> None:
        """Narrow terminal → stack the option grids so borders never collide."""
        wide = event.size.width >= 96
        try:
            self.query_one("#filters-cols", Grid).styles.grid_size_columns = 2 if wide else 1
            self.query_one("#filters-selects", Grid).styles.grid_size_columns = 2 if wide else 1
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        with Vertical(id="filters-box"):
            yield Static(Text.from_markup("[#ffb000 b]FILTERS · TARGET[/]  "
                                          "[dim]ctrl+s = search · esc = close[/]"), classes="modal-title")
            with VerticalScroll(id="filters-scroll"):
                yield Static(Text.from_markup("[#33ff88]Condition[/]  [dim](query.cond)[/]"))
                yield Input(value=str(self._f("condition", "")), id="condition",
                            placeholder="e.g. prematurity")
                yield Static(Text.from_markup("[#33ff88]Keyword[/]  [dim](OR expression — combined with Condition as AND)[/]"))
                yield Input(value=str(self._f("keyword", "")), id="keyword")
                yield Static(self._net_banner(str(self._f("keyword", "")) or ""), id="net-banner")
                yield Static(Text.from_markup("[#33ff88]Exclude keywords[/]  [dim](comma-separated)[/]"))
                yield Input(value=", ".join(self._f("exclude_keywords", []) or []), id="exclude")

                with Grid(id="filters-cols"):
                    with Vertical(classes="fcol"):
                        yield Static(Text.from_markup("[#33ff88]Status[/]"))
                        yield SelectionList[str](
                            *[Selection(l, v, v in (self._f("statuses", []) or [])) for l, v in STATUS_OPTS],
                            id="statuses")
                        yield Static(Text.from_markup("[#33ff88]Phase[/]  [dim](none = all)[/]"))
                        yield SelectionList[str](
                            *[Selection(l, v, v in [str(x) for x in self._f("phases", []) or []]) for l, v in PHASE_OPTS],
                            id="phases")
                    with Vertical(classes="fcol"):
                        yield Static(Text.from_markup("[#33ff88]Age[/]"))
                        yield SelectionList[str](
                            *[Selection(l, v, v in (self._f("ages", []) or [])) for l, v in AGE_OPTS],
                            id="ages")
                        yield Static(Text.from_markup("[#33ff88]Funder[/]  [dim](none = all)[/]"))
                        yield SelectionList[str](
                            *[Selection(l, v, v in (self._f("funder_types", []) or [])) for l, v in FUNDER_OPTS],
                            id="funders")

                with Grid(id="filters-selects"):
                    for key, (label, opts, default) in RADIO_GROUPS.items():
                        with Vertical(classes="fcol"):
                            yield Static(Text.from_markup(f"[#33ff88]{label}[/]"))
                            cur = str(self._f(key, default))
                            if cur not in [v for _l, v in opts]:
                                cur = default
                            with RadioSet(id=key):
                                for l, v in opts:
                                    yield RadioButton(l, value=(v == cur))

                yield Static(Text.from_markup("[#33ff88]Max results[/]"))
                yield Input(value=str(self._f("max_results", 300)), id="max_results")
            with Horizontal(id="filters-buttons"):
                yield Button("⟲  SEARCH NOW", id="run")
                yield Button("save (no search)", id="save")
                yield Button("✕ new hunt — clear all", id="newhunt")

    # ---- actions ---- #
    def _collect(self) -> None:
        cfg = self.engine.cfg
        cfg.set("filters.condition", self.query_one("#condition", Input).value.strip())
        cfg.set("filters.keyword", self.query_one("#keyword", Input).value.strip())
        cfg.set("filters.exclude_keywords",
                [x.strip() for x in self.query_one("#exclude", Input).value.split(",") if x.strip()])
        cfg.set("filters.statuses", list(self.query_one("#statuses", SelectionList).selected))
        cfg.set("filters.phases", list(self.query_one("#phases", SelectionList).selected))
        cfg.set("filters.ages", list(self.query_one("#ages", SelectionList).selected))
        cfg.set("filters.funder_types", list(self.query_one("#funders", SelectionList).selected))
        for key, (_label, opts, default) in RADIO_GROUPS.items():
            idx = self.query_one(f"#{key}", RadioSet).pressed_index
            cfg.set(f"filters.{key}", opts[idx][1] if idx >= 0 else default)
        try:
            cfg.set("filters.max_results", max(1, int(self.query_one("#max_results", Input).value or 300)))
        except ValueError:
            cfg.set("filters.max_results", 300)
        cfg.save()

    def action_run(self) -> None:
        self._collect()
        self.dismiss(True)     # signal: run a search

    def action_cancel(self) -> None:
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "newhunt":
            self.action_new_hunt()
            return
        if event.button.id == "run":
            self.action_run()
        else:
            self._collect()
            self.notify("Filters saved.", severity="information")
            self.dismiss(False)

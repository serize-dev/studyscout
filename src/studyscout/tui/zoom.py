"""Fullscreen zoom of the studies deck — every column, header-click sorting,
pick a row to jump the deck's cursor to it.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from .sorting import STUDY_SORTS, SortSpec, apply_sort, sort_arrow
from .widgets import contact_cell, phase_cell, sites_cell, stage_glyph, status_cell

# column index → sort key (zoom adds an NCT spec the `s` modal doesn't need)
ZOOM_SORTS = STUDY_SORTS + [SortSpec("nct", "NCT id", lambda r: r[0].nct)]
COLUMN_KEYS = ["stage", "nct", "phase", "status", "sites", "enrollment",
               "start", "contact", "sponsor", "title"]


class StudiesModal(ModalScreen):
    BINDINGS = [
        ("escape,q,z", "close", "close"),
        ("o,enter", "choose", "select"),
        ("j", "cursor_down", ""),
        ("k", "cursor_up", ""),
    ]

    def __init__(self, rows: list, sort_key: str = "start", flipped: bool = False):
        super().__init__()
        self.rows = rows  # list of (Study, Stage, notes), pre-sorted by the deck
        self.sort_key = sort_key
        self.sort_flipped = flipped

    def compose(self) -> ComposeResult:
        with Vertical(id="zoom-box"):
            yield Static(id="zoom-title", classes="modal-title")
            table = DataTable(id="zoomtable", cursor_type="row", zebra_stripes=False)
            table.add_column("●", width=2)
            table.add_column("NCT", width=12)
            table.add_column("PHASE", width=6)
            table.add_column("STATUS", width=8)
            table.add_column("SITES", width=5)
            table.add_column("ENROLL", width=6)
            table.add_column("START", width=10)
            table.add_column("@", width=2)
            table.add_column("SPONSOR", width=26)
            table.add_column("TITLE")
            yield table

    def on_mount(self) -> None:
        self._populate()
        self.query_one("#zoomtable", DataTable).focus()

    def _populate(self) -> None:
        table = self.query_one("#zoomtable", DataTable)
        table.clear()
        for study, stage, _notes in self.rows:
            table.add_row(
                stage_glyph(stage),
                Text(study.nct, style="#1f9e46"),
                phase_cell(study),
                status_cell(study),
                sites_cell(study),
                Text(str(study.enrollment or "—"), justify="right", style="#33ff66"),
                Text(study.start.isoformat() if study.start else "—", style="#1f9e46"),
                contact_cell(study),
                Text((study.sponsor or "—")[:26],
                     style="#ffb000" if study.sponsor_class == "INDUSTRY" else "#33ff66"),
                Text(study.title, style="#33ff66"),
                key=study.id)
        arrow = sort_arrow(ZOOM_SORTS, self.sort_key, self.sort_flipped)
        self.query_one("#zoom-title", Static).update(Text.from_markup(
            f"[#33ff88 b]STUDIES[/]  [dim]· {len(self.rows)} shown · "
            f"sort [#ffb000]{self.sort_key}{arrow}[/] (click a column header) · "
            f"enter jump · esc close[/]"))

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        key = COLUMN_KEYS[event.column_index]
        self.sort_flipped = (not self.sort_flipped) if key == self.sort_key else False
        self.sort_key = key
        self.rows = apply_sort(self.rows, ZOOM_SORTS, self.sort_key, self.sort_flipped)
        self._populate()

    def action_cursor_down(self) -> None:
        self.query_one("#zoomtable", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#zoomtable", DataTable).action_cursor_up()

    def action_close(self) -> None:
        # v1.8.0 — even on escape, a sort picked in the zoom comes home to the deck
        self.dismiss((None, self.sort_key, self.sort_flipped))

    def action_choose(self) -> None:
        table = self.query_one("#zoomtable", DataTable)
        try:
            from textual.coordinate import Coordinate
            key = table.coordinate_to_cell_key(Coordinate(table.cursor_row, 0)).row_key
            self.dismiss((key.value, self.sort_key, self.sort_flipped))
        except Exception:
            self.dismiss((None, self.sort_key, self.sort_flipped))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.dismiss(event.row_key.value)

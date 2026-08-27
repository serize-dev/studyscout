"""Print/export (v1.6.0 pattern, shared since v1.9.0): a text listing on
screen (c copies) + the same text saved in the data dir for `lp <file>`."""

from __future__ import annotations

from datetime import datetime

from ..config import data_dir


def export_text(app, scope: str, text: str, prefix: str = "pipeline") -> str:
    from .modals import TextModal
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = data_dir() / f"{prefix}-{scope}-{stamp}.txt"
    try:
        path.write_text(text, encoding="utf-8")
        saved = f"saved → {path}"
    except Exception as exc:  # noqa: BLE001
        saved = f"save failed: {exc}"
    title = (f"PRINT · {scope.upper()}  [dim]· c copy · saved to disk — "
             f"print with: lp {path.name}[/]")
    app.push_screen(TextModal(title, text, copyable=True))
    app.notify(saved, severity="information")
    return str(path)

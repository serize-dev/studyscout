"""Render helpers for studies — list cells + the detail view."""

from __future__ import annotations

from rich.text import Text

from ..models import SPONSOR_CLASS_LABEL, Stage, Study

STAGE_COLOR = {
    Stage.NEW: "#1f9e46", Stage.FLAGGED: "#ffb000", Stage.CONTACTED: "#33ccff",
    Stage.WAITING: "#c0a000", Stage.REPLIED: "#33ff88", Stage.MEETING: "#ff66cc",
    Stage.WON: "#00ff88", Stage.CONDUCTING: "#00ffcc", Stage.FUTURE: "#b58cff",
    Stage.DECLINED: "#ff5555", Stage.UNAVAILABLE: "#8899aa", Stage.CLOSED: "#555555",
}

_STATUS_SHORT = {
    "RECRUITING": ("Rec", "#33ff88"),
    "NOT_YET_RECRUITING": ("NYR", "#ffb000"),
    "ACTIVE_NOT_RECRUITING": ("Act", "#33ccff"),
    "ENROLLING_BY_INVITATION": ("Inv", "#33ccff"),
    "COMPLETED": ("Done", "#1f9e46"),
    "SUSPENDED": ("Susp", "#ff5555"),
    "TERMINATED": ("Term", "#ff5555"),
    "WITHDRAWN": ("Wdrn", "#ff5555"),
}


def stage_glyph(stage: Stage) -> Text:
    return Text(stage.glyph, style=f"bold {STAGE_COLOR.get(stage, '#33ff66')}")


def status_cell(study: Study) -> Text:
    short, color = _STATUS_SHORT.get(study.status, (study.status[:4].title(), "#2bbf5a"))
    return Text(short, style=color)


def phase_cell(study: Study) -> Text:
    p = study.phase_str
    color = "#33ff88" if any(x in p for x in ("2", "3", "4")) else "#2bbf5a"
    return Text(p, style=color)


def sites_cell(study: Study) -> Text:
    n = study.n_sites
    color = "#33ff88" if n >= 2 else ("#1f9e46" if n == 1 else "#555")
    return Text(f"{n}", style=f"bold {color}")


def contact_cell(study: Study) -> Text:
    if study.has_contact:
        return Text("@", style="bold #00ff88")
    return Text("·", style="#1f9e46")


def title_cell(study: Study) -> Text:
    t = Text()
    t.append(study.title[:70], style="#aaffcc")
    if study.sponsor:
        t.append(f"  {study.sponsor[:24]}", style="#1f9e46")
    return t


def detail_view(study: Study, stage: Stage, notes: str) -> Text:
    t = Text()
    t.append(study.title + "\n", style="bold #ffb000")
    t.append(study.nct, style="#33ccff underline")
    t.append(f"   {study.phase_str}", style="bold #33ff88")
    t.append(f"   {study.status_short}", style=_STATUS_SHORT.get(study.status, ('', '#2bbf5a'))[1])
    t.append(f"   n={study.enrollment}   {study.n_sites} sites\n", style="#33ff66")

    t.append("\nsponsor  ", style="#1f9e46")
    t.append(study.sponsor or "—", style="bold #00ff88")
    t.append(f"  [{SPONSOR_CLASS_LABEL.get(study.sponsor_class, study.sponsor_class or '?')}]\n", style="#1f9e46")
    if study.collaborators:
        t.append("collab   ", style="#1f9e46")
        t.append(", ".join(study.collaborators[:5]) + "\n", style="#33ff66")
    if study.conditions:
        t.append("cond     ", style="#1f9e46")
        t.append(", ".join(study.conditions[:8]) + "\n", style="#33ff66")
    t.append("stage    ", style="#1f9e46")
    t.append(f"{stage.glyph} {stage.label}\n", style=STAGE_COLOR.get(stage, "#33ff66"))
    if study.start:
        t.append("start    ", style="#1f9e46")
        t.append(f"{study.start.isoformat()}\n", style="#33ff66")

    # Contacts — the outreach targets.
    best = study.best_contact()
    if best.has_direct:
        t.append("\n► CONTACT\n", style="bold #00ff88")
        t.append(f"  {best.render()}\n", style="#aaffcc")
    if study.central_contacts:
        t.append("\ncentral contacts\n", style="#1f9e46")
        for c in study.central_contacts[:3]:
            t.append(f"  {c.render()}\n", style="#33ff66")

    if study.sites:
        t.append("\nsites\n", style="#1f9e46")
        for s in study.sites[:8]:
            t.append(f"  • {s.facility} — {s.where()}", style="#33ff66")
            sc = next((c for c in s.contacts if c.has_direct), None)
            if sc:
                t.append(f"   ✉ {sc.email or sc.phone}", style="#33ff88")
            t.append("\n")
        if study.n_sites > 8:
            t.append(f"  … +{study.n_sites - 8} more\n", style="#1f9e46")

    t.append("\nlink     ", style="#1f9e46")
    t.append(study.url + "\n", style="#33ccff underline")
    if notes:
        t.append("notes    ", style="#1f9e46")
        t.append(notes + "\n", style="#ffb000")
    if study.summary:
        t.append("\n" + "─" * 40 + "\n", style="#103018")
        t.append(study.summary[:3000], style="#33ff66")
    return t

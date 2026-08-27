"""Regulatory startup — the paperwork gauntlet as PHASES (v1.9.0).

The checklist is grouped into phases (FEASIBILITY → REG DOCS → IRB →
CONTRACTS → ACTIVATION). A study's *regulatory column* is derived, never
set: it sits in the first phase that still has an open item, and lands in
ACTIVATED when nothing is open. Check things off and it moves itself.

Rules-only, no AI: startup paperwork is a deterministic gauntlet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

OPEN, DONE, NA = 0, 1, 2
ACTIVATED = "ACTIVATED"

# The v1.0–v1.8 flat template. A profile whose `regulatory.checklist` still
# equals this was never customized → the new phased default applies.
LEGACY_CHECKLIST = [
    "CDA / NDA signed",
    "Feasibility questionnaire returned",
    "Protocol + IB received",
    "FDA 1572 completed",
    "PI CV + medical license current",
    "GCP / human-subjects certs current",
    "IRB / EC submission",
    "Budget negotiated",
    "CTA executed",
    "Delegation-of-authority log started",
    "SIV scheduled",
]

# Keyword hints that sort a customized FLAT checklist into phases so an
# upgraded profile gets a board without hand-migration. First hit wins.
_PHASE_HINTS = [
    ("FEASIBILITY", ("cda", "nda", "confidential", "feasib", "protocol", " ib", "brochure",
                     "psv", "qualification", "sqv")),
    ("REG DOCS", ("1572", "cv", "license", "licence", "gcp", "human-subjects", "human subjects",
                  "citi", "disclosure", "clia", "cap ", "lab cert", "normal range", "signature")),
    ("IRB", ("irb", "ethics", " ec ", "consent", "icf")),
    ("CONTRACTS", ("budget", "cta", "contract", "agreement", "payment", "invoice")),
    ("ACTIVATION", ("delegation", "doa", "siv", "initiation", "activation", "pharmacy",
                    "ip storage", "drug storage", "training", "green light")),
]
_OTHER = "OTHER"


@dataclass
class RegItem:
    item: str
    done: int = OPEN            # OPEN / DONE / NA
    note: str = ""
    updated_at: str = ""
    phase: str = _OTHER
    custom: bool = False        # not in the template (ad-hoc or legacy)

    @property
    def complete(self) -> bool:
        return self.done in (DONE, NA)

    @property
    def box(self) -> str:
        return {DONE: "[x]", NA: "[-]"}.get(self.done, "[ ]")


def _norm(phases) -> list[tuple[str, tuple[str, ...]]]:
    out = []
    for p in phases or []:
        if isinstance(p, dict):
            name = str(p.get("name", "") or "").strip() or _OTHER
            items = tuple(str(x) for x in (p.get("items") or []))
        else:
            name, items = str(p), ()
        out.append((name, items))
    return out


def heuristic_phases(items: list[str]) -> list[tuple[str, list[str]]]:
    """Sort a flat checklist into the default phase names by keyword."""
    buckets: dict[str, list[str]] = {name: [] for name, _k in _PHASE_HINTS}
    buckets[_OTHER] = []
    for it in items:
        low = f" {it.lower()} "
        for name, keys in _PHASE_HINTS:
            if any(k in low for k in keys):
                buckets[name].append(it)
                break
        else:
            buckets[_OTHER].append(it)
    return [(name, lst) for name, lst in buckets.items() if lst]


def resolve_phases(cfg, default_phases) -> list[tuple[str, list[str]]]:
    """The effective phase template for this profile.

    Precedence: a customized `regulatory.phases` wins; else a customized
    legacy flat `regulatory.checklist` (v1.0–v1.8 profiles) is auto-phased;
    else the shipped default. Items keep their text → checked state survives.
    """
    phases = _norm(cfg.get("regulatory.phases") or [])
    legacy = [str(x) for x in (cfg.get("regulatory.checklist") or [])]
    phases_custom = bool(phases) and phases != _norm(default_phases)
    legacy_custom = bool(legacy) and legacy != LEGACY_CHECKLIST
    if legacy_custom and not phases_custom:
        return heuristic_phases(legacy)
    if phases:
        return [(name, list(items)) for name, items in phases]
    # No phases anywhere (and the legacy list, if any, is the untouched
    # v1.0–v1.8 default) → the shipped phased template.
    return [(name, list(items)) for name, items in _norm(default_phases)]


def flatten(phases: list[tuple[str, list[str]]]) -> list[str]:
    return [it for _n, items in phases for it in items]


def build_items(phases: list[tuple[str, list[str]]], rows: dict[str, dict]) -> list[RegItem]:
    """Template order, phase-tagged, with recorded state; custom items last."""
    out: list[RegItem] = []
    seen = set()
    for name, items in phases:
        for it in items:
            r = rows.get(it, {})
            out.append(RegItem(it, int(r.get("done", 0) or 0), r.get("note", "") or "",
                               r.get("updated_at", "") or "", name, False))
            seen.add(it)
    for it, r in rows.items():
        if it not in seen:
            out.append(RegItem(it, int(r.get("done", 0) or 0), r.get("note", "") or "",
                               r.get("updated_at", "") or "", _OTHER, True))
    return out


def progress(items: list[RegItem]) -> tuple[int, int]:
    return sum(1 for i in items if i.complete), len(items)


def column_of(items: list[RegItem], phases: list[tuple[str, list[str]]]) -> str:
    """First phase with an open item; ACTIVATED when nothing is open."""
    order = [n for n, _i in phases] + [_OTHER]
    open_phases = {i.phase for i in items if not i.complete}
    for name in order:
        if name in open_phases:
            return name
    return ACTIVATED


def next_open(items: list[RegItem]) -> str:
    return next((i.item for i in items if not i.complete), "")


def days_since(iso: str) -> int | None:
    if not iso:
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(iso)).days
    except (TypeError, ValueError):
        return None


def board_columns(phases: list[tuple[str, list[str]]], has_other: bool) -> list[str]:
    cols = [n for n, _i in phases]
    if has_other:
        cols.append(_OTHER)
    cols.append(ACTIVATED)
    return cols

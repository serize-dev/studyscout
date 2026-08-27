"""Follow-up — the tickle file (v1.9.0).

`t` on any study or lead sets a date; the FOLLOW-UP ledger (`T`) lists what
is overdue, due today, coming up, plus the un-dated pressure the app already
knew about: quiet sponsors, FUTURE relationships whose call-back clock ran
out, and open startup paperwork. Rules-only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

_REL = re.compile(r"^\+\s*(\d+)\s*([dwm]?)$", re.I)


def parse_due(text: str, today: date | None = None) -> date | None:
    """Forgiving date entry: '9/15', '9/15/26', '2026-09-15', '+7', '+2w',
    '+1m', 'tomorrow', 'mon'…'sun' (next one), '' → None (clear).
    Raises ValueError on garbage so the UI can say so.
    """
    today = today or date.today()
    s = (text or "").strip().lower()
    if not s or s in ("clear", "none", "-", "x"):
        return None
    if s in ("today", "now"):
        return today
    if s in ("tomorrow", "tmrw", "+"):
        return today + timedelta(days=1)
    m = _REL.match(s)
    if m:
        n, unit = int(m.group(1)), (m.group(2) or "d").lower()
        return today + timedelta(days=n * {"d": 1, "w": 7, "m": 30}[unit])
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    for i, d in enumerate(days):
        if s.startswith(d):
            ahead = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m/%d", "%m-%d", "%b %d", "%d %b"):
        try:
            d = datetime.strptime(s, fmt).date()
        except ValueError:
            continue
        if "%Y" not in fmt and "%y" not in fmt:
            d = d.replace(year=today.year)
            if d < today - timedelta(days=60):       # "1/5" in December = next year
                d = d.replace(year=today.year + 1)
        return d
    raise ValueError(f"can't read a date from {text!r} — try 9/15, +7, +2w, mon, 2026-09-15")


def due_label(due: str, today: date | None = None) -> tuple[str, str]:
    """('overdue 3d' | 'today' | 'in 5d' | '9/15', color)."""
    today = today or date.today()
    try:
        d = date.fromisoformat(due)
    except (TypeError, ValueError):
        return ("", "#555")
    delta = (d - today).days
    if delta < 0:
        return (f"overdue {-delta}d", "#ff5555")
    if delta == 0:
        return ("today", "#ffb000")
    if delta <= 14:
        return (f"in {delta}d", "#33ff88")
    return (f"{d.month}/{d.day}", "#1f9e46")


@dataclass
class Ledger:
    """What the FOLLOW-UP screen shows, in order of pressure."""
    overdue: list = field(default_factory=list)     # (Study, Stage, notes, due)
    today: list = field(default_factory=list)
    upcoming: list = field(default_factory=list)
    later: list = field(default_factory=list)       # dated beyond the horizon
    quiet: list = field(default_factory=list)       # (sponsor, days, n)
    future: list = field(default_factory=list)      # (sponsor, days, n)
    reg: list = field(default_factory=list)         # (Study, done, total)
    horizon: int = 14

    @property
    def dated(self) -> list:
        return self.overdue + self.today + self.upcoming + self.later

    @property
    def pressing(self) -> int:
        return len(self.overdue) + len(self.today)


def build_ledger(rows, due_map: dict[str, str], quiet, future, reg,
                 horizon: int = 14, today: date | None = None) -> Ledger:
    today = today or date.today()
    led = Ledger(quiet=list(quiet), future=list(future), reg=list(reg), horizon=horizon)
    dated = []
    for study, stage, notes in rows:
        due = due_map.get(study.id)
        if not due:
            continue
        try:
            d = date.fromisoformat(due)
        except ValueError:
            continue
        dated.append((d, (study, stage, notes, due)))
    dated.sort(key=lambda x: x[0])
    for d, row in dated:
        delta = (d - today).days
        if delta < 0:
            led.overdue.append(row)
        elif delta == 0:
            led.today.append(row)
        elif delta <= horizon:
            led.upcoming.append(row)
        else:
            led.later.append(row)
    return led

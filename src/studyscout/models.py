"""Domain models for StudyScout — clinical-trials BD intel.

A ClinicalTrials.gov record becomes a :class:`Study`. The BD pipeline lives in
:class:`Stage`; the therapeutic angle in the study's conditions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Stage(str, Enum):
    """BD outreach pipeline (mirrors the STUDY//SCOUT reference)."""

    NEW = "new"
    FLAGGED = "flagged"        # a fit worth pursuing
    CONTACTED = "contacted"
    WAITING = "waiting"        # awaiting their reply
    REPLIED = "replied"
    MEETING = "meeting"        # call/meeting booked
    WON = "won"               # study/engagement landed
    FUTURE = "future"          # relationship warm — reach out for FUTURE studies
    DECLINED = "declined"
    CLOSED = "closed"          # dead / not a fit

    @property
    def label(self) -> str:
        return {
            Stage.NEW: "Inbox", Stage.FLAGGED: "Flagged", Stage.CONTACTED: "Contacted",
            Stage.WAITING: "Waiting", Stage.REPLIED: "Replied", Stage.MEETING: "Meeting",
            Stage.WON: "Won", Stage.FUTURE: "Future", Stage.DECLINED: "Declined",
            Stage.CLOSED: "Closed",
        }[self]

    @property
    def glyph(self) -> str:
        return {
            Stage.NEW: "·", Stage.FLAGGED: "⚑", Stage.CONTACTED: "→", Stage.WAITING: "…",
            Stage.REPLIED: "✉", Stage.MEETING: "★", Stage.WON: "✓",
            Stage.FUTURE: "⟳", Stage.DECLINED: "✗", Stage.CLOSED: "▪",
        }[self]


KANBAN_ORDER = [
    Stage.NEW, Stage.FLAGGED, Stage.CONTACTED, Stage.WAITING,
    Stage.REPLIED, Stage.MEETING, Stage.WON, Stage.FUTURE, Stage.DECLINED,
]

# Sponsor classes worth weighting for BD (industry = paying customers).
SPONSOR_CLASS_LABEL = {
    "INDUSTRY": "industry", "NIH": "NIH", "FED": "federal",
    "OTHER_GOV": "gov", "NETWORK": "network", "OTHER": "academic/other",
    "INDIV": "individual", "UNKNOWN": "?",
}


@dataclass
class Contact:
    name: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    @property
    def has_direct(self) -> bool:
        return bool(self.email or self.phone)

    def render(self) -> str:
        bits = [b for b in (self.name, self.role, self.email, self.phone) if b]
        return "  ·  ".join(bits) if bits else "—"


@dataclass
class Site:
    facility: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    status: str = ""
    contacts: list[Contact] = field(default_factory=list)

    def where(self) -> str:
        return ", ".join(x for x in (self.city, self.state) if x) or self.country


@dataclass
class Study:
    nct: str
    title: str
    status: str = ""                       # overall status (RECRUITING, ...)
    phases: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    sponsor: str = ""
    sponsor_class: str = ""                # INDUSTRY / NIH / OTHER ...
    collaborators: list[str] = field(default_factory=list)
    enrollment: Optional[int] = None
    study_type: str = ""
    start: Optional[date] = None
    sites: list[Site] = field(default_factory=list)
    central_contacts: list[Contact] = field(default_factory=list)
    summary: str = ""

    # ---- derived / scored ---- #
    fit: int = 0
    fit_reason: str = ""
    llm_scored: bool = False

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct}"

    @property
    def id(self) -> str:
        return hashlib.sha1(self.nct.encode()).hexdigest()[:16] if self.nct else \
            hashlib.sha1(self.title.encode()).hexdigest()[:16]

    @property
    def phase_str(self) -> str:
        return "/".join(p.replace("PHASE", "P") for p in self.phases) or "N/A"

    @property
    def status_short(self) -> str:
        return (self.status or "").replace("_", " ").title()

    @property
    def n_sites(self) -> int:
        return len(self.sites)

    def best_contact(self) -> Contact:
        """A local site contact with an email/phone, else a central contact."""
        for pool in (
            [c for s in self.sites for c in s.contacts if c.has_direct],
            [c for c in self.central_contacts if c.has_direct],
            [c for s in self.sites for c in s.contacts],
            self.central_contacts,
        ):
            if pool:
                return pool[0]
        return Contact()

    @property
    def has_contact(self) -> bool:
        return self.best_contact().has_direct


@dataclass
class SponsorDossier:
    """One BD relationship: a sponsor and everything you know about them.

    The dossier is a regrouping of studies already in the store — the real
    outreach unit is the sponsor, not the individual NCT.
    """

    name: str
    sponsor_class: str = ""
    rows: list = field(default_factory=list)     # (Study, Stage, notes) tuples
    notes: str = ""                              # per-sponsor BD notes
    last_touch: Optional[datetime] = None        # newest stage change on their trials
    intel: str = ""                              # Wintermute web-hunted intel brief
    intel_at: str = ""                           # iso timestamp of the hunt

    @property
    def id(self) -> str:
        return hashlib.sha1(self.name.encode("utf-8")).hexdigest()[:16]

    @property
    def n_trials(self) -> int:
        return len(self.rows)

    @property
    def recruiting(self) -> int:
        return sum(1 for s, _st, _n in self.rows
                   if s.status in ("RECRUITING", "NOT_YET_RECRUITING", "ENROLLING_BY_INVITATION"))

    @property
    def in_pipeline(self) -> int:
        """Trials you've actually moved on (anything past Inbox, still alive)."""
        dead = (Stage.NEW, Stage.CLOSED, Stage.DECLINED)
        return sum(1 for _s, st, _n in self.rows if st not in dead)

    @property
    def is_industry(self) -> bool:
        return self.sponsor_class == "INDUSTRY"

    @property
    def newest_start(self) -> Optional[date]:
        starts = [s.start for s, _st, _n in self.rows if s.start]
        return max(starts) if starts else None

    @property
    def conditions(self) -> list[str]:
        seen: dict[str, None] = {}
        for s, _st, _n in self.rows:
            for c in s.conditions:
                seen.setdefault(c, None)
        return list(seen)

    @property
    def phases(self) -> str:
        toks: dict[str, None] = {}
        for s, _st, _n in self.rows:
            if s.phase_str != "N/A":
                toks.setdefault(s.phase_str, None)
        return "/".join(sorted(toks)) or "N/A"

    def contacts(self, limit: int = 6) -> list[Contact]:
        """Central + site contacts across all their trials, deduped, direct-first.

        Central contacts repeat across a sponsor's studies — one human often
        guards several NCTs, which is exactly the BD door.
        """
        seen: dict[str, Contact] = {}
        pools = ([c for s, _st, _n in self.rows for c in s.central_contacts]
                 + [c for s, _st, _n in self.rows for site in s.sites for c in site.contacts])
        for c in pools:
            key = (c.email or "").lower() or f"{c.name}|{c.phone}"
            if key.strip("|") and key not in seen:
                seen[key] = c
        ranked = sorted(seen.values(), key=lambda c: not c.has_direct)
        return ranked[:limit]

    @property
    def has_contact(self) -> bool:
        return any(c.has_direct for c in self.contacts(limit=1))

    @property
    def bd_key(self) -> tuple:
        """Default ordering: industry money first, then live demand, then reachability."""
        return (self.is_industry, self.recruiting, self.has_contact,
                self.n_trials, self.newest_start or date.min)


def parse_date(value) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%B %d, %Y", "%B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

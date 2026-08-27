"""Controller: config + store + ClinicalTrials.gov search."""

from __future__ import annotations

from datetime import datetime

from .ai import Brain, Consigliere
from .config import DEFAULTS, Config
from .db import Store
from .followup import Ledger, build_ledger
from .models import LEAD_STATUS, Contact, SponsorDossier, Stage, Study
from .sources import ctgov
from . import regulatory as reg


class Engine:
    def __init__(self):
        self.cfg = Config()
        self.cfg.ensure_file()
        self.cfg.ensure_me()          # seed site.md
        self.store = Store()
        self.brain = Brain(self.cfg)
        self.consigliere = Consigliere(self.brain, self.cfg)

    def reload_brain(self) -> None:
        self.brain = Brain(self.cfg)
        self.consigliere = Consigliere(self.brain, self.cfg)

    @property
    def ai_ready(self) -> bool:
        return self.brain.enabled

    async def refresh(self, progress_cb=None) -> tuple[int, int, list[str]]:
        """Run the configured filters against ClinicalTrials.gov and persist."""
        if progress_cb:
            progress_cb("ctgov", "querying…", None)
        studies, errors = await ctgov.fetch(self.cfg)
        # One stamp for the whole catch: rows carrying it are "fresh", NEW rows
        # without it drop off the deck (hidden, never deleted — `a` reveals).
        from datetime import datetime
        stamp = datetime.now().isoformat(timespec="seconds")
        new = self.store.upsert(studies, stamp=stamp)
        self.store.set_meta("last_search_at", stamp)
        if progress_cb:
            progress_cb("ctgov", "ok", len(studies))
        return len(studies), new, errors

    def load(self) -> list[tuple[Study, Stage, str]]:
        return self.store.studies_with_stage()

    def set_stage(self, study_id: str, stage: Stage) -> None:
        self.store.set_stage(study_id, stage)

    def set_notes(self, study_id: str, notes: str) -> None:
        self.store.set_notes(study_id, notes)

    def counts(self):
        return self.store.counts()

    # ---- sponsor dossiers (the BD lens) ---- #
    def dossiers(self) -> list[SponsorDossier]:
        """Group the deck by sponsor: one dossier per relationship."""
        notes = self.store.sponsor_notes_map()
        touches = self.store.sponsor_touches()
        intel = self.store.sponsor_intel_map()
        by: dict[str, SponsorDossier] = {}
        for study, stage, n in self.load():
            name = study.sponsor or "(unknown sponsor)"
            d = by.setdefault(name, SponsorDossier(name=name, sponsor_class=study.sponsor_class))
            d.rows.append((study, stage, n))
            if not d.sponsor_class and study.sponsor_class:
                d.sponsor_class = study.sponsor_class
        for name, d in by.items():
            d.notes = notes.get(name, "")
            d.intel, d.intel_at = intel.get(name, ("", ""))
            ts = touches.get(name)
            if ts:
                try:
                    d.last_touch = datetime.fromisoformat(ts)
                except ValueError:
                    pass
        return list(by.values())

    def set_sponsor_notes(self, name: str, notes: str) -> None:
        self.store.set_sponsor_notes(name, notes)

    async def enrich_sponsor(self, dossier: SponsorDossier) -> str:
        """Web-hunt fresh intel on a sponsor; persist it on the relationship."""
        intel = await self.consigliere.enrich_dossier(dossier)
        if intel:
            self.store.set_sponsor_intel(dossier.name, intel)
        return intel

    # ---- outreach with outcome memory ---- #
    def _outreach_ctx(self) -> str:
        sent, replied, subjects = self.store.outreach_stats()
        if not sent:
            return ""
        ctx = f"{sent} outreach emails drafted so far; {replied} got replies."
        if subjects:
            ctx += " Subject lines that got replies: " + " | ".join(subjects)
        return ctx

    @staticmethod
    def _subject_of(draft: str) -> str:
        lines = (draft or "").strip().splitlines()
        if lines and lines[0].lower().startswith("subject:"):
            return lines[0].split(":", 1)[1].strip()
        return ""

    async def outreach_email(self, study: Study, notes: str = "") -> str:
        """Study-level draft with the track record folded in; logged at draft time."""
        draft = await self.consigliere.outreach_email(study, notes,
                                                      outreach_ctx=self._outreach_ctx())
        self.store.log_outreach(study.sponsor, study.id,
                                self._subject_of(draft) or f"Site interest — {study.nct}")
        return draft

    async def sponsor_pitch(self, dossier: SponsorDossier) -> str:
        """Sponsor-level consolidated pitch; logged against the relationship."""
        draft = await self.consigliere.sponsor_outreach(dossier,
                                                        outreach_ctx=self._outreach_ctx())
        self.store.log_outreach(dossier.name, "",
                                self._subject_of(draft) or f"Site interest — {dossier.name}")
        return draft

    # ---- regulatory handoff (v1.9.0: phased) ---- #
    REG_STAGES = (Stage.MEETING, Stage.WON, Stage.CONDUCTING)

    def reg_phases(self) -> list[tuple[str, list[str]]]:
        return reg.resolve_phases(self.cfg, DEFAULTS["regulatory"]["phases"])

    def reg_items(self) -> list[str]:
        return reg.flatten(self.reg_phases())

    def reg_state(self, study_id: str) -> list[tuple[str, int]]:
        return self.store.reg_state(study_id, self.reg_items())

    def reg_detail(self, study_id: str) -> list[reg.RegItem]:
        """Phase-tagged items with notes/dates — what the checklist renders."""
        return reg.build_items(self.reg_phases(), self.store.reg_rows(study_id))

    def reg_toggle(self, study_id: str, item: str) -> bool:
        return self.store.reg_toggle(study_id, item)

    def reg_set(self, study_id: str, item: str, done: int) -> int:
        return self.store.reg_set(study_id, item, done)

    def reg_note(self, study_id: str, item: str, note: str) -> None:
        self.store.reg_note(study_id, item, note)

    def reg_add_item(self, study_id: str, item: str) -> None:
        item = (item or "").strip()
        if item:
            self.store.reg_set(study_id, item, reg.OPEN)

    def reg_delete_item(self, study_id: str, item: str) -> None:
        self.store.reg_delete_item(study_id, item)

    def reg_progress(self, study_id: str) -> tuple[int, int]:
        return reg.progress(self.reg_detail(study_id))

    def reg_started_days(self, study_id: str) -> int | None:
        """The startup clock: days since the first checklist touch, else since
        the study entered its current stage."""
        d = reg.days_since(self.store.reg_started(study_id))
        if d is None:
            d = reg.days_since(self.store.stage_stamps().get(study_id, ""))
        return d

    def reg_progress_map(self) -> dict[str, tuple[int, int]]:
        """study_id → (done, total) for every reg-eligible study, one query."""
        phases = self.reg_phases()
        recorded = self.store.reg_all()
        out = {}
        for study, stage, _n in self.load():
            if stage not in self.REG_STAGES:
                continue
            rows = {it: {"done": d} for it, d in recorded.get(study.id, {}).items()}
            out[study.id] = reg.progress(reg.build_items(phases, rows))
        return out

    def reg_board(self) -> tuple[list[str], dict[str, list[dict]]]:
        """The REGULATORY board: phase columns, studies placed by derivation.

        Returns (columns, {column: [card…]}); a card = dict(study, stage,
        notes, done, total, days, next, items).
        """
        phases = self.reg_phases()
        recorded = self.store.reg_all()
        stamps = self.store.stage_stamps()
        cards: dict[str, list[dict]] = {}
        has_other = False
        for study, stage, notes in self.load():
            if stage not in self.REG_STAGES:
                continue
            rows = {it: {"done": d} for it, d in recorded.get(study.id, {}).items()}
            items = reg.build_items(phases, rows)
            col = reg.column_of(items, phases)
            if col == "OTHER":
                has_other = True
            done, total = reg.progress(items)
            days = reg.days_since(self.store.reg_started(study.id))
            if days is None:
                days = reg.days_since(stamps.get(study.id, ""))
            cards.setdefault(col, []).append({
                "study": study, "stage": stage, "notes": notes, "done": done,
                "total": total, "days": days, "next": reg.next_open(items), "items": items,
            })
        cols = reg.board_columns(phases, has_other)
        for col in cols:
            cards.setdefault(col, []).sort(key=lambda c: -(c["days"] or 0))   # longest in startup first
        return cols, cards

    def reg_open(self) -> list[tuple[Study, int, int]]:
        """Won/meeting/conducting studies with startup paperwork still open."""
        out = []
        by_id = {s.id: s for s, _st, _n in self.load()}
        for sid, (done, total) in self.reg_progress_map().items():
            if total and done < total:
                out.append((by_id[sid], done, total))
        out.sort(key=lambda t: t[1] / max(1, t[2]))    # least-started first
        return out

    # ---- v1.9.0: off-registry leads ---- #
    def leads(self) -> list[tuple[Study, Stage, str]]:
        return [(s, st, n) for s, st, n in self.load() if s.is_lead]

    def save_lead(self, form: dict, nct: str = "", stage: Stage | None = None,
                  due: str | None = None) -> Study:
        """Create (nct='') or update a lead from the form dict:
        title, sponsor, sponsor_class, contact{name,role,email,phone}, link,
        topics (list), summary."""
        c = form.get("contact") or {}
        contact = Contact(name=c.get("name") or None, role=c.get("role") or None,
                          email=c.get("email") or None, phone=c.get("phone") or None)
        study = Study(
            nct=nct or self.store.next_lead_nct(),
            title=(form.get("title") or "").strip() or "(untitled lead)",
            status=LEAD_STATUS, phases=[], conditions=list(form.get("topics") or []),
            sponsor=(form.get("sponsor") or "").strip(),
            sponsor_class=form.get("sponsor_class") or "OTHER",
            study_type="LEAD", central_contacts=[contact] if any(
                (contact.name, contact.role, contact.email, contact.phone)) else [],
            summary=(form.get("summary") or "").strip(),
            link=(form.get("link") or "").strip(),
        )
        self.store.upsert([study], quiet=True)
        if stage is not None:
            self.store.set_stage(study.id, stage)
        if due is not None:
            self.store.set_due(study.id, due or None)
        return study

    def delete_lead(self, study_id: str) -> None:
        self.store.delete_study(study_id)

    # ---- v1.9.0: dated follow-ups ---- #
    def set_due(self, study_id: str, due: str | None) -> None:
        self.store.set_due(study_id, due)

    def due_map(self) -> dict[str, str]:
        return self.store.due_map()

    def ledger(self) -> Ledger:
        days = int(self.cfg.get("followup.nudge_days", 7))
        fdays = int(self.cfg.get("followup.future_nudge_days", 45))
        horizon = int(self.cfg.get("followup.due_horizon_days", 14))
        return build_ledger(self.load(), self.due_map(), self.store.quiet_sponsors(days),
                            self.store.future_due(fdays), self.reg_open(), horizon=horizon)

    # ---- follow-up decay + the morning briefing ---- #
    def followups_due(self) -> int:
        days = int(self.cfg.get("followup.nudge_days", 7))
        return len(self.store.quiet_sponsors(days))

    def briefing(self) -> dict:
        """The morning ritual: deltas since last visit, quiet relationships,
        and today's top moves. Rules-only — works with Wintermute dark.
        """
        last_visit = self.store.get_meta("last_visit")
        deltas = self.store.deltas_since(last_visit)
        touched = set(self.store.sponsor_touches())          # sponsors you've worked
        new_rows = [d for d in deltas if d["kind"] == "new"]
        flips = [d for d in deltas if d["kind"] == "status"]
        known_new = [d for d in new_rows if d["sponsor"] in touched]
        days = int(self.cfg.get("followup.nudge_days", 7))
        quiet = self.store.quiet_sponsors(days)
        fdays = int(self.cfg.get("followup.future_nudge_days", 45))
        future_due = self.store.future_due(fdays)
        # Fresh pitch candidates: industry dossiers with live demand + a door,
        # that you haven't touched yet.
        untouched = [d for d in self.dossiers()
                     if d.is_industry and d.recruiting and d.has_contact
                     and d.name not in touched]
        untouched.sort(key=lambda d: d.bd_key, reverse=True)
        meetings = [(s, st, n) for s, st, n in self.load() if st == Stage.MEETING]
        led = self.ledger()
        self.store.set_meta("last_visit", datetime.now().isoformat(timespec="seconds"))
        return {
            "due": (led.overdue + led.today)[:6],
            "due_soon": led.upcoming[:4],
            "new_count": len(new_rows),
            "known_new": known_new[:5],
            "flips": flips[:6],
            "quiet": quiet[:5],
            "future": future_due[:5],
            "future_days": fdays,
            "pitch": untouched[:3],
            "meetings": meetings[:3],
            "reg": self.reg_open()[:3],
            "nudge_days": days,
        }

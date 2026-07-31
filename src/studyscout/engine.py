"""Controller: config + store + ClinicalTrials.gov search."""

from __future__ import annotations

from datetime import datetime

from .ai import Brain, Consigliere
from .config import Config
from .db import Store
from .models import SponsorDossier, Stage, Study
from .sources import ctgov


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

    # ---- regulatory handoff ---- #
    def reg_items(self) -> list[str]:
        return [str(x) for x in (self.cfg.get("regulatory.checklist", []) or [])]

    def reg_state(self, study_id: str) -> list[tuple[str, bool]]:
        return self.store.reg_state(study_id, self.reg_items())

    def reg_toggle(self, study_id: str, item: str) -> bool:
        return self.store.reg_toggle(study_id, item)

    def reg_progress(self, study_id: str) -> tuple[int, int]:
        state = self.reg_state(study_id)
        return sum(1 for _i, d in state if d), len(state)

    def reg_open(self) -> list[tuple[Study, int, int]]:
        """Won (and meeting-stage) studies with startup paperwork still open."""
        out = []
        for study, stage, _n in self.load():
            if stage not in (Stage.WON, Stage.MEETING):
                continue
            done, total = self.reg_progress(study.id)
            if total and done < total:
                out.append((study, done, total))
        out.sort(key=lambda t: t[1] / max(1, t[2]))    # least-started first
        return out

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
        self.store.set_meta("last_visit", datetime.now().isoformat(timespec="seconds"))
        return {
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

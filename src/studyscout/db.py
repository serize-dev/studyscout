"""SQLite store — cached studies + the BD pipeline (stage + notes)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .config import data_dir
from .models import Contact, Site, Stage, Study, parse_date

SCHEMA = """
CREATE TABLE IF NOT EXISTS studies (
    id TEXT PRIMARY KEY, nct TEXT, title TEXT, status TEXT, phases TEXT,
    conditions TEXT, sponsor TEXT, sponsor_class TEXT, collaborators TEXT,
    enrollment INTEGER, study_type TEXT, start TEXT, sites TEXT,
    central_contacts TEXT, summary TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS pipeline (
    study_id TEXT PRIMARY KEY, stage TEXT NOT NULL DEFAULT 'new',
    notes TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS sponsors (
    name TEXT PRIMARY KEY, notes TEXT DEFAULT '', updated_at TEXT,
    intel TEXT, intel_at TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, study_id TEXT, nct TEXT,
    sponsor TEXT, kind TEXT,             -- new | status
    detail TEXT                          -- e.g. 'NOT_YET_RECRUITING → RECRUITING'
);
CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, sponsor TEXT,
    study_id TEXT DEFAULT '',            -- '' for sponsor-level pitches
    subject TEXT, replied INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reg (
    study_id TEXT, item TEXT, done INTEGER DEFAULT 0, updated_at TEXT,
    PRIMARY KEY (study_id, item)
);
"""


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or (data_dir() / "studyscout.db")
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        # v1.2.0 migration: pre-existing dbs lack last_seen (used to hide rows
        # the latest search no longer catches).
        try:
            self.con.execute("ALTER TABLE studies ADD COLUMN last_seen TEXT")
        except sqlite3.OperationalError:
            pass
        # v1.3.0 migration: web-hunted sponsor intel lives on the dossier.
        for col in ("intel TEXT", "intel_at TEXT"):
            try:
                self.con.execute(f"ALTER TABLE sponsors ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        self.con.commit()

    def close(self):
        self.con.close()

    # ---- write ---- #
    def upsert(self, studies: Iterable[Study], stamp: str | None = None) -> int:
        now = stamp or datetime.now().isoformat(timespec="seconds")
        new = 0
        cur = self.con.cursor()
        for s in studies:
            exists = cur.execute("SELECT status FROM studies WHERE id=?", (s.id,)).fetchone()
            # Delta intel: a brand-new trial or a status flip is the BD trigger.
            if not exists:
                cur.execute(
                    "INSERT INTO deltas (ts,study_id,nct,sponsor,kind,detail) VALUES (?,?,?,?,?,?)",
                    (now, s.id, s.nct, s.sponsor, "new", s.status))
            elif (exists["status"] or "") != (s.status or ""):
                cur.execute(
                    "INSERT INTO deltas (ts,study_id,nct,sponsor,kind,detail) VALUES (?,?,?,?,?,?)",
                    (now, s.id, s.nct, s.sponsor, "status",
                     f"{exists['status'] or '?'} → {s.status or '?'}"))
            cur.execute(
                """INSERT INTO studies (id,nct,title,status,phases,conditions,sponsor,
                   sponsor_class,collaborators,enrollment,study_type,start,sites,
                   central_contacts,summary,first_seen,last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                   phases=excluded.phases, conditions=excluded.conditions,
                   sponsor=excluded.sponsor, sponsor_class=excluded.sponsor_class,
                   collaborators=excluded.collaborators, enrollment=excluded.enrollment,
                   study_type=excluded.study_type, start=excluded.start, sites=excluded.sites,
                   central_contacts=excluded.central_contacts, summary=excluded.summary,
                   last_seen=excluded.last_seen""",
                (s.id, s.nct, s.title, s.status, json.dumps(s.phases),
                 json.dumps(s.conditions), s.sponsor, s.sponsor_class,
                 json.dumps(s.collaborators), s.enrollment, s.study_type,
                 s.start.isoformat() if s.start else None,
                 json.dumps([asdict(x) for x in s.sites]),
                 json.dumps([asdict(c) for c in s.central_contacts]),
                 s.summary, now, now),
            )
            if not exists:
                cur.execute("INSERT OR IGNORE INTO pipeline (study_id,stage,updated_at) VALUES (?,?,?)",
                            (s.id, Stage.NEW.value, now))
                new += 1
        # Bound the delta log — it's an intel feed, not an archive.
        cur.execute("DELETE FROM deltas WHERE id NOT IN "
                    "(SELECT id FROM deltas ORDER BY id DESC LIMIT 500)")
        self.con.commit()
        return new

    def set_stage(self, study_id: str, stage: Stage) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT INTO pipeline (study_id,stage,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(study_id) DO UPDATE SET stage=excluded.stage, updated_at=excluded.updated_at",
            (study_id, stage.value, now))
        if stage in (Stage.REPLIED, Stage.MEETING, Stage.WON):
            # Outcome memory: they answered — credit both the study-level draft
            # and any sponsor-level pitch to the same company.
            r = self.con.execute("SELECT sponsor FROM studies WHERE id=?", (study_id,)).fetchone()
            sponsor = (r["sponsor"] if r else "") or ""
            self.con.execute(
                "UPDATE outreach SET replied=1 WHERE study_id=? OR (sponsor=? AND sponsor != '')",
                (study_id, sponsor))
        self.con.commit()

    def set_notes(self, study_id: str, notes: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT INTO pipeline (study_id,notes,stage,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(study_id) DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at",
            (study_id, notes, Stage.NEW.value, now))
        self.con.commit()

    # ---- read ---- #
    def _row(self, r: sqlite3.Row) -> Study:
        sites = []
        for sd in json.loads(r["sites"] or "[]"):
            contacts = [Contact(**c) for c in sd.get("contacts", [])]
            rest = {k: v for k, v in sd.items() if k != "contacts"}
            sites.append(Site(contacts=contacts, **rest))
        return Study(
            nct=r["nct"], title=r["title"] or "", status=r["status"] or "",
            phases=json.loads(r["phases"] or "[]"), conditions=json.loads(r["conditions"] or "[]"),
            sponsor=r["sponsor"] or "", sponsor_class=r["sponsor_class"] or "",
            collaborators=json.loads(r["collaborators"] or "[]"),
            enrollment=r["enrollment"], study_type=r["study_type"] or "",
            start=parse_date(r["start"]), sites=sites,
            central_contacts=[Contact(**c) for c in json.loads(r["central_contacts"] or "[]")],
            summary=r["summary"] or "",
        )

    def studies_with_stage(self) -> list[tuple[Study, Stage, str]]:
        rows = self.con.execute(
            """SELECT s.*, COALESCE(p.stage,'new') st, COALESCE(p.notes,'') nt
               FROM studies s LEFT JOIN pipeline p ON p.study_id=s.id
               ORDER BY s.start DESC""").fetchall()
        out = []
        for r in rows:
            try:
                stage = Stage(r["st"])
            except Exception:
                stage = Stage.NEW
            out.append((self._row(r), stage, r["nt"]))
        return out

    # ---- meta (last visit, last briefing, …) ---- #
    def stale_ids(self) -> set[str]:
        """NEW-stage studies the latest search did NOT catch (stale on deck).

        Worked rows (any stage past new) are never stale — the pipeline is
        sacred. Before the first post-upgrade search, nothing is stale.
        """
        last = self.get_meta("last_search_at")
        if not last:
            return set()
        rows = self.con.execute(
            """SELECT s.id FROM studies s JOIN pipeline p ON p.study_id = s.id
               WHERE p.stage = 'new' AND COALESCE(s.last_seen, '') < ?""",
            (last,)).fetchall()
        return {r["id"] for r in rows}

    def get_meta(self, key: str, default: str = "") -> str:
        r = self.con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return (r["value"] if r else default) or default

    def set_meta(self, key: str, value: str) -> None:
        self.con.execute("INSERT INTO meta (key,value) VALUES (?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.con.commit()

    # ---- deltas (the intel feed) ---- #
    def deltas_since(self, iso_ts: str, limit: int = 40) -> list[sqlite3.Row]:
        if not iso_ts:
            return []
        return self.con.execute(
            "SELECT * FROM deltas WHERE ts > ? ORDER BY id DESC LIMIT ?",
            (iso_ts, limit)).fetchall()

    # ---- follow-up decay (quiet relationships) ---- #
    def future_due(self, days: int) -> list[tuple[str, int, int]]:
        """Sponsors parked in FUTURE ≥ N days — the keep-warm relationships
        whose 'reach out for the next study' date has arrived.

        Returns (sponsor, days_parked, n_trials), longest-parked first.
        """
        rows = self.con.execute(
            """SELECT s.sponsor nm, MIN(p.updated_at) oldest, COUNT(*) n
               FROM studies s JOIN pipeline p ON p.study_id=s.id
               WHERE p.stage = 'future' AND s.sponsor != ''
               GROUP BY s.sponsor""").fetchall()
        out = []
        for r in rows:
            try:
                parked = (datetime.now() - datetime.fromisoformat(r["oldest"])).days
            except (TypeError, ValueError):
                continue
            if parked >= days:
                out.append((r["nm"], parked, int(r["n"])))
        return sorted(out, key=lambda x: -x[1])

    def quiet_sponsors(self, days: int) -> list[tuple[str, int, int]]:
        """Sponsors with trials sitting in Contacted/Waiting ≥ N days.

        Returns (sponsor, days_quiet, n_trials_waiting), quietest first.
        """
        rows = self.con.execute(
            """SELECT s.sponsor nm, MIN(p.updated_at) oldest, COUNT(*) n
               FROM studies s JOIN pipeline p ON p.study_id=s.id
               WHERE p.stage IN ('contacted','waiting') AND s.sponsor != ''
                 AND replace(p.updated_at,'T',' ') <= datetime('now','localtime', ?)
               GROUP BY s.sponsor ORDER BY oldest ASC""",
            (f"-{max(1, int(days))} days",)).fetchall()
        out = []
        for r in rows:
            try:
                quiet = (datetime.now() - datetime.fromisoformat(r["oldest"])).days
            except Exception:
                quiet = days
            out.append((r["nm"], quiet, int(r["n"])))
        return out

    # ---- outreach ledger (outcome memory) ---- #
    def log_outreach(self, sponsor: str, study_id: str, subject: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT INTO outreach (ts,sponsor,study_id,subject) VALUES (?,?,?,?)",
            (now, sponsor or "", study_id or "", (subject or "")[:200]))
        self.con.commit()

    def outreach_stats(self) -> tuple[int, int, list[str]]:
        r = self.con.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(replied),0) r FROM outreach").fetchone()
        subs = self.con.execute(
            "SELECT DISTINCT subject FROM outreach WHERE replied=1 AND subject != '' "
            "ORDER BY ts DESC LIMIT 3").fetchall()
        return int(r["n"] or 0), int(r["r"] or 0), [s["subject"] for s in subs]

    # ---- regulatory handoff checklist ---- #
    def reg_state(self, study_id: str, template: list[str]) -> list[tuple[str, bool]]:
        """Checklist in template order; custom items already checked off for a
        study survive template edits (they're appended at the end)."""
        rows = {r["item"]: bool(r["done"]) for r in self.con.execute(
            "SELECT item, done FROM reg WHERE study_id=?", (study_id,))}
        out = [(item, rows.pop(item, False)) for item in template]
        out += [(item, done) for item, done in rows.items()]   # legacy/custom items
        return out

    def reg_toggle(self, study_id: str, item: str) -> bool:
        now = datetime.now().isoformat(timespec="seconds")
        r = self.con.execute("SELECT done FROM reg WHERE study_id=? AND item=?",
                             (study_id, item)).fetchone()
        new = 0 if (r and r["done"]) else 1
        self.con.execute(
            "INSERT INTO reg (study_id,item,done,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(study_id,item) DO UPDATE SET done=excluded.done, "
            "updated_at=excluded.updated_at",
            (study_id, item, new, now))
        self.con.commit()
        return bool(new)

    # ---- sponsors (the BD relationship layer) ---- #
    def sponsor_notes_map(self) -> dict[str, str]:
        return {r["name"]: r["notes"] or ""
                for r in self.con.execute("SELECT name, notes FROM sponsors")}

    def set_sponsor_notes(self, name: str, notes: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT INTO sponsors (name,notes,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET notes=excluded.notes, updated_at=excluded.updated_at",
            (name, notes, now))
        self.con.commit()

    def set_sponsor_intel(self, name: str, intel: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            "INSERT INTO sponsors (name,intel,intel_at,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET intel=excluded.intel, "
            "intel_at=excluded.intel_at, updated_at=excluded.updated_at",
            (name, intel, now, now))
        self.con.commit()

    def sponsor_intel_map(self) -> dict[str, tuple[str, str]]:
        """name → (intel text, fetched-at iso) for dossiers that have been enriched."""
        return {r["name"]: (r["intel"], r["intel_at"] or "")
                for r in self.con.execute(
                    "SELECT name, intel, intel_at FROM sponsors WHERE intel IS NOT NULL AND intel != ''")}

    def sponsor_touches(self) -> dict[str, str]:
        """Newest stage-change timestamp per sponsor (anything moved past Inbox)."""
        rows = self.con.execute(
            """SELECT s.sponsor nm, MAX(p.updated_at) ts
               FROM studies s JOIN pipeline p ON p.study_id=s.id
               WHERE p.stage != 'new' AND s.sponsor != ''
               GROUP BY s.sponsor""").fetchall()
        return {r["nm"]: r["ts"] for r in rows if r["ts"]}

    def counts(self) -> dict[Stage, int]:
        out = {s: 0 for s in Stage}
        for r in self.con.execute("SELECT COALESCE(stage,'new') s, COUNT(*) n FROM pipeline GROUP BY s"):
            try:
                out[Stage(r["s"])] = r["n"]
            except Exception:
                pass
        return out

"""Functional tests: dossiers, sorting, sponsor notes/touches. No network."""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from studyscout.engine import Engine            # noqa: E402
from studyscout.models import Contact, Site, Stage, Study   # noqa: E402
from studyscout.tui.sorting import (             # noqa: E402
    SPONSOR_SORTS, STUDY_SORTS, apply_sort, sort_arrow)


def _studies() -> list[Study]:
    return [
        Study(nct="NCT00000001", title="Surfactant strategies in preterm infants",
              status="RECRUITING", phases=["PHASE3"], conditions=["Respiratory Distress Syndrome"],
              sponsor="Acme Pharma", sponsor_class="INDUSTRY", enrollment=400,
              start=date(2026, 5, 1),
              sites=[Site(facility="Somewhere NICU", city="Nashville", state="TN",
                          contacts=[Contact(name="Jane CRA", email="jane@acme.test")])],
              central_contacts=[Contact(name="Central BD", email="bd@acme.test")]),
        Study(nct="NCT00000002", title="HIE cooling adjunct",
              status="NOT_YET_RECRUITING", phases=["PHASE2"], conditions=["HIE"],
              sponsor="Acme Pharma", sponsor_class="INDUSTRY", enrollment=120,
              start=date(2026, 6, 15),
              central_contacts=[Contact(name="Central BD", email="bd@acme.test")]),
        Study(nct="NCT00000003", title="Neonatal sepsis registry",
              status="RECRUITING", phases=[], conditions=["Neonatal Sepsis"],
              sponsor="State University", sponsor_class="OTHER", enrollment=2000,
              start=date(2026, 1, 10)),
    ]


def main() -> None:
    e = Engine()
    new = e.store.upsert(_studies())
    assert new == 3, new

    # dossiers group by sponsor
    ds = {d.name: d for d in e.dossiers()}
    assert set(ds) == {"Acme Pharma", "State University"}, set(ds)
    acme = ds["Acme Pharma"]
    assert acme.n_trials == 2 and acme.recruiting == 2 and acme.is_industry
    # contact dedup: bd@acme.test appears on both trials → once
    emails = [c.email for c in acme.contacts()]
    assert emails.count("bd@acme.test") == 1, emails
    assert acme.has_contact and not ds["State University"].has_contact
    print("dossier grouping + contact dedup OK")

    # touch: move a trial past inbox → sponsor gets a last_touch
    sid = _studies()[0].id
    e.set_stage(sid, Stage.CONTACTED)
    acme = {d.name: d for d in e.dossiers()}["Acme Pharma"]
    assert acme.last_touch is not None and acme.in_pipeline == 1
    assert ds["State University"].last_touch is None
    print("sponsor last-touch OK")

    # sponsor notes round-trip
    e.set_sponsor_notes("Acme Pharma", "met their CRA at PAS 2026")
    acme = {d.name: d for d in e.dossiers()}["Acme Pharma"]
    assert acme.notes == "met their CRA at PAS 2026"
    print("sponsor notes OK")

    # ---- sorting ---- #
    rows = e.load()
    by_start = apply_sort(rows, STUDY_SORTS, "start", False)
    assert by_start[0][0].nct == "NCT00000002"          # newest first
    assert apply_sort(rows, STUDY_SORTS, "start", True)[0][0].nct == "NCT00000003"  # flipped
    assert apply_sort(rows, STUDY_SORTS, "enrollment", False)[0][0].enrollment == 2000
    assert apply_sort(rows, STUDY_SORTS, "contact", False)[0][0].has_contact
    assert apply_sort(rows, STUDY_SORTS, "sponsor", False)[0][0].sponsor == "Acme Pharma"  # industry first
    assert apply_sort(rows, STUDY_SORTS, "stage", False)[0][1] == Stage.CONTACTED
    assert sort_arrow(STUDY_SORTS, "start", False) == "↓"
    assert sort_arrow(STUDY_SORTS, "start", True) == "↑"
    print("study sorts OK")

    dlist = e.dossiers()
    assert apply_sort(dlist, SPONSOR_SORTS, "bd", False)[0].name == "Acme Pharma"
    assert apply_sort(dlist, SPONSOR_SORTS, "trials", False)[0].n_trials == 2
    assert apply_sort(dlist, SPONSOR_SORTS, "name", False)[0].name == "Acme Pharma"
    assert apply_sort(dlist, SPONSOR_SORTS, "touch", False)[0].last_touch is not None
    print("sponsor sorts OK")

    # dossier context builder (feeds the consolidated pitch)
    from studyscout.ai.consigliere import _dossier_context
    ctx = _dossier_context(acme)
    assert "NCT00000001" in ctx and "NCT00000002" in ctx and "bd@acme.test" in ctx
    assert "PAS 2026" in ctx
    print("dossier context OK")

    # ---- deltas: new trials + status flips ---- #
    e.store.set_meta("last_visit", "2000-01-01T00:00:00")
    flipped = _studies()
    flipped[1].status = "RECRUITING"           # NYR → RECRUITING
    extra = Study(nct="NCT00000004", title="New PDA device trial", status="RECRUITING",
                  phases=["PHASE3"], conditions=["PDA"], sponsor="Acme Pharma",
                  sponsor_class="INDUSTRY", start=date(2026, 7, 1))
    e.store.upsert(flipped + [extra])
    deltas = e.store.deltas_since("2000-01-01T00:00:00")
    kinds = {(d["nct"], d["kind"]) for d in deltas}
    assert ("NCT00000004", "new") in kinds, kinds
    assert ("NCT00000002", "status") in kinds, kinds
    flip = next(d for d in deltas if d["kind"] == "status")
    assert "NOT_YET_RECRUITING → RECRUITING" in flip["detail"], flip["detail"]
    print("delta tracking OK")

    # ---- quiet sponsors (follow-up decay) ---- #
    e.set_stage(sid, Stage.WAITING)
    old = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    e.store.con.execute("UPDATE pipeline SET updated_at=? WHERE study_id=?", (old, sid))
    e.store.con.commit()
    quiet = e.store.quiet_sponsors(7)
    assert quiet and quiet[0][0] == "Acme Pharma" and quiet[0][1] == 10, quiet
    assert e.followups_due() == 1
    print("quiet sponsors OK")

    # ---- outreach outcome memory (sponsor-level credit) ---- #
    e.store.log_outreach("Acme Pharma", "", "Three neonatal programs, one NICU site")
    e.set_stage(sid, Stage.REPLIED)            # any Acme trial replying credits the pitch
    sent, replied, subjects = e.store.outreach_stats()
    assert (sent, replied) == (1, 1) and "NICU" in subjects[0], (sent, replied, subjects)
    assert "NICU" in e._outreach_ctx()
    print("outreach memory OK")

    # ---- briefing ---- #
    e.store.set_meta("last_visit", "2000-01-01T00:00:00")
    e.set_stage(sid, Stage.WAITING)            # restore the quiet state
    e.store.con.execute("UPDATE pipeline SET updated_at=? WHERE study_id=?", (old, sid))
    e.store.con.commit()
    b = e.briefing()
    assert b["new_count"] >= 1
    assert any(d["nct"] == "NCT00000004" for d in b["known_new"])   # known sponsor posted new
    assert b["flips"] and b["quiet"] and b["quiet"][0][0] == "Acme Pharma"
    b2 = e.briefing()
    assert b2["new_count"] == 0                # delta consumed
    print("briefing OK ·", {k: (len(v) if isinstance(v, list) else v)
                            for k, v in b.items()})

    # ---- regulatory handoff checklist ---- #
    items = e.reg_items()
    assert len(items) >= 8 and items[0].startswith("CDA"), items[:2]
    state = e.reg_state(sid)
    assert len(state) == len(items) and not any(d for _i, d in state)
    assert e.reg_toggle(sid, items[0]) is True          # check off CDA
    assert e.reg_toggle(sid, items[1]) is True
    assert e.reg_toggle(sid, items[1]) is False         # toggle back
    done, total = e.reg_progress(sid)
    assert (done, total) == (1, len(items)), (done, total)
    # open-reg surfacing: won study with items pending shows in briefing
    e.set_stage(sid, Stage.WON)
    open_reg = e.reg_open()
    assert open_reg and open_reg[0][0].id == sid and open_reg[0][1] == 1
    b3 = e.briefing()
    assert b3["reg"] and b3["reg"][0][0].id == sid
    # all checked → drops off the nag list
    for item in items:
        st = dict(e.reg_state(sid))
        if not st[item]:
            e.reg_toggle(sid, item)
    assert not e.reg_open()
    print("reg handoff OK ·", f"{len(items)} items in template")

    # prompt-caching block shapes
    from studyscout.ai.client import _system_text, system_blocks
    blocks = system_blocks("STABLE", "VOLATILE")
    assert blocks[0]["cache_control"] == {"type": "ephemeral"} and len(blocks) == 2
    assert _system_text(blocks) == "STABLE\n\nVOLATILE"
    assert _system_text("plain") == "plain"
    print("system_blocks OK")

    print("\nALL GREEN")


if __name__ == "__main__":
    main()

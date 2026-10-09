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

    # v1.6.0 — mail routing: outlook deeplink + command placeholders
    from studyscout.mail import build_mailto, build_outlook_url
    ol = build_outlook_url("cra@sponsor.test", "Site interest — NCT1", "Hola & adiós")
    assert ol.startswith("https://outlook.office.com/mail/deeplink/compose?")
    assert "to=cra%40sponsor.test" in ol
    assert "subject=Site%20interest" in ol and "Hola%20%26%20adi" in ol
    assert build_mailto("a@b.c", "s", "b").startswith("mailto:a@b.c?")
    # placeholder substitution: {url}/{to} swapped in, URL NOT appended
    from unittest import mock as _mock

    from studyscout import mail as _mail
    calls = []
    with _mock.patch.object(_mail.subprocess, "Popen",
                            lambda argv, **kw: calls.append(argv)), \
         _mock.patch.object(_mail.shutil, "which", lambda x: "/usr/bin/" + x):
        ok, msg = _mail.open_mail("a@b.c", "S", "B", command="mycli --open {url}",
                                  mode="outlook")
        assert ok and calls[-1][0] == "mycli"
        assert calls[-1][-1].startswith("https://outlook.office.com/")
        assert len(calls[-1]) == 3, calls[-1]           # nothing appended
        ok, msg = _mail.open_mail("a@b.c", "S", "B", command="prospect-mail")
        assert ok and calls[-1] == ["prospect-mail",
                                    build_mailto("a@b.c", "S", "B")]  # appended
        ok, msg = _mail.open_mail("a@b.c", "S", "B", mode="outlook")
        assert ok and calls[-1][0] == "xdg-open" and "deeplink" in calls[-1][1]
    print("mail routing OK ·", len(calls), "launches intercepted")
    # v1.9.1 — frozen binary must not leak its _MEI lib dir into the browser
    from studyscout.childenv import child_env
    mei = "/tmp/_MEIabc123"
    leaky = {"LD_LIBRARY_PATH": mei + ":/opt/x/lib", "LD_LIBRARY_PATH_ORIG": "/opt/x/lib",
             "PATH": "/usr/bin", "GI_TYPELIB_PATH": mei + "/gi", "HOME": "/h"}
    env = child_env(leaky, bundle_dir=mei)
    assert env["LD_LIBRARY_PATH"] == "/opt/x/lib", env
    assert "LD_LIBRARY_PATH_ORIG" not in env and "GI_TYPELIB_PATH" not in env, env
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/h"
    env = child_env({"LD_LIBRARY_PATH": mei, "LD_LIBRARY_PATH_ORIG": ""}, bundle_dir=mei)
    assert "LD_LIBRARY_PATH" not in env, env           # user had none → none
    env = child_env({"LD_LIBRARY_PATH": mei + ":/usr/lib"}, bundle_dir=mei)
    assert env["LD_LIBRARY_PATH"] == "/usr/lib", env   # no ORIG → strip bundle entry
    assert child_env({"LD_LIBRARY_PATH": "/a"}, bundle_dir="") == {"LD_LIBRARY_PATH": "/a"}
    kw_seen = []
    with _mock.patch.object(_mail.subprocess, "Popen",
                            lambda argv, **kw: kw_seen.append(kw)), \
         _mock.patch.object(_mail.shutil, "which", lambda x: "/usr/bin/" + x):
        _mail.open_mail("a@b.c", "S", "B")
    assert "env" in kw_seen[-1], kw_seen
    print("child env scrub OK")

    # v1.7.0 — dossier aliveness: CONDUCTING counts, UNAVAILABLE doesn't
    from studyscout.models import SponsorDossier
    ss = _studies()
    d0 = SponsorDossier(name="Acme", rows=[
        (ss[0], Stage.CONDUCTING, ""),
        (ss[1], Stage.UNAVAILABLE, ""),
        (ss[2], Stage.CLOSED, ""),
    ])
    assert d0.in_pipeline == 1, d0.in_pipeline
    print("conducting aliveness OK")


    # ================= v1.9.0 — reg phases · leads · follow-up =================
    from datetime import date as _date
    from studyscout import regulatory as R
    from studyscout.followup import build_ledger, due_label, parse_due
    from studyscout.config import DEFAULTS

    # parse_due: forgiving entry
    t0 = _date(2026, 8, 27)
    assert parse_due("9/15", t0) == _date(2026, 9, 15)
    assert parse_due("+7", t0) == _date(2026, 9, 3) and parse_due("+2w", t0) == _date(2026, 9, 10)
    assert parse_due("mon", t0) == _date(2026, 8, 31) and parse_due("tomorrow", t0) == _date(2026, 8, 28)
    assert parse_due("1/5", t0) == _date(2027, 1, 5)          # rolls into next year
    assert parse_due("2026-09-15", t0) == _date(2026, 9, 15) and parse_due("", t0) is None
    try:
        parse_due("garbage", t0); raise AssertionError("garbage accepted")
    except ValueError:
        pass
    assert due_label((t0 - timedelta(days=3)).isoformat(), t0)[0] == "overdue 3d"
    assert due_label(t0.isoformat(), t0)[0] == "today"
    assert due_label((t0 + timedelta(days=5)).isoformat(), t0)[0] == "in 5d"
    print("parse_due OK")

    # resolve_phases precedence: default → legacy-untouched → customized legacy → custom phases
    defaults = DEFAULTS["regulatory"]["phases"]
    class _Cfg:
        def __init__(self, d): self.d = d
        def get(self, k, default=None): return self.d.get(k, default)
    ph = R.resolve_phases(_Cfg({}), defaults)
    assert [n for n, _i in ph] == ["FEASIBILITY", "REG DOCS", "IRB", "CONTRACTS", "ACTIVATION"]
    assert R.resolve_phases(_Cfg({"regulatory.checklist": list(R.LEGACY_CHECKLIST)}), defaults) == ph
    custom_flat = ["CDA signed", "IRB approval", "SIV booked", "Weird local thing"]
    ph2 = R.resolve_phases(_Cfg({"regulatory.checklist": custom_flat,
                                 "regulatory.phases": defaults}), defaults)
    assert dict(ph2) == {"FEASIBILITY": ["CDA signed"], "IRB": ["IRB approval"],
                         "ACTIVATION": ["SIV booked"], "OTHER": ["Weird local thing"]}, ph2
    ph3 = R.resolve_phases(_Cfg({"regulatory.checklist": custom_flat,
                                 "regulatory.phases": [{"name": "ONE", "items": ["a", "b"]}]}), defaults)
    assert ph3 == [("ONE", ["a", "b"])], ph3
    # derivation: N/A counts complete; column = first phase with an open item
    items = R.build_items(ph3, {"a": {"done": R.NA}, "zzz": {"done": R.OPEN}})
    assert R.column_of(items, ph3) == "ONE" and R.progress(items) == (1, 3)
    assert items[-1].custom and items[-1].phase == "OTHER"
    items = R.build_items(ph3, {"a": {"done": R.NA}, "b": {"done": R.DONE}})
    assert R.column_of(items, ph3) == R.ACTIVATED and R.next_open(items) == ""
    assert R.board_columns(ph3, has_other=True) == ["ONE", "OTHER", R.ACTIVATED]
    print("reg phases OK")

    # engine: reg_progress_map only covers reg stages; N/A + notes round-trip
    won = _studies()[1].id
    e.set_stage(won, Stage.WON)
    pm = e.reg_progress_map()
    assert won in pm and pm[won][1] == len(e.reg_items()) and _studies()[2].id not in pm
    e.reg_set(won, "FDA 1572 completed", R.NA)
    e.reg_note(won, "FDA 1572 completed", "non-IND device — n/a")
    d = {i.item: i for i in e.reg_detail(won)}
    assert d["FDA 1572 completed"].done == R.NA and d["FDA 1572 completed"].note.startswith("non-IND")
    assert e.reg_progress(won)[0] == 1
    e.reg_add_item(won, "Local radiation committee")
    assert any(i.custom and i.item == "Local radiation committee" for i in e.reg_detail(won))
    e.reg_delete_item(won, "Local radiation committee")
    assert not any(i.custom for i in e.reg_detail(won))
    cols, cards = e.reg_board()
    assert cols[-1] == R.ACTIVATED and any(c["study"].id == won for c in cards["FEASIBILITY"])
    assert e.reg_started_days(won) is not None
    print("reg engine OK")

    # leads: quiet upsert (no delta), dossier grouping, edit keeps id, delete
    before = len(e.store.deltas_since("2000-01-01T00:00:00", limit=500))
    acme_n = {d.name: d for d in e.dossiers()}["Acme Pharma"].n_trials
    lead = e.save_lead({"title": "Sunshine Genetics Act — PI", "sponsor": "Acme Pharma",
                        "sponsor_class": "INDUSTRY", "contact": {"name": "Dr. Sol", "email": "sol@x.test"},
                        "topics": ["genetics"], "summary": "met at conf", "link": "https://x.test"},
                       stage=Stage.FLAGGED, due="2026-09-15")
    assert lead.nct == "LEAD-0001" and lead.is_lead and lead.url == "https://x.test"
    assert len(e.store.deltas_since("2000-01-01T00:00:00", limit=500)) == before   # no delta noise
    assert e.due_map()[lead.id] == "2026-09-15"
    acme = {d.name: d for d in e.dossiers()}["Acme Pharma"]
    assert acme.n_trials == acme_n + 1 and any(s.is_lead for s, _st, _n in acme.rows)  # joins the dossier
    lead2 = e.save_lead({"title": "Sunshine Genetics Act — PI (edited)", "sponsor": "Acme Pharma"},
                        nct=lead.nct)
    assert lead2.id == lead.id and e.leads()[0][0].title.endswith("(edited)")
    assert e.leads()[0][1] == Stage.FLAGGED                       # stage untouched on edit
    e.store.set_meta("last_search_at", "2999-01-01T00:00:00")
    assert lead.id not in e.store.stale_ids()
    e.store.set_meta("last_search_at", "")
    from studyscout.ai.consigliere import _study_context
    ctx = _study_context(lead2, "call Tuesday")
    assert "off-registry" in ctx and "do not invent" in ctx and "LEAD-0001" in ctx
    e.delete_lead(lead.id)
    assert not e.leads() and lead.id not in e.due_map()
    assert e.store.next_lead_nct() == "LEAD-0002"                  # sequence never reuses
    print("leads OK")

    # ledger buckets
    ss = _studies()
    rows = [(ss[0], Stage.CONTACTED, ""), (ss[1], Stage.WON, "n"), (ss[2], Stage.FLAGGED, "")]
    due = {ss[0].id: (t0 - timedelta(days=1)).isoformat(), ss[1].id: t0.isoformat(),
           ss[2].id: (t0 + timedelta(days=30)).isoformat()}
    led = build_ledger(rows, due, quiet=[("Q", 9, 1)], future=[], reg=[], horizon=14, today=t0)
    assert [r[0].id for r in led.overdue] == [ss[0].id] and [r[0].id for r in led.today] == [ss[1].id]
    assert not led.upcoming and [r[0].id for r in led.later] == [ss[2].id] and led.pressing == 2
    led2 = e.ledger()
    assert isinstance(led2.horizon, int) and led2.reg and led2.reg[0][0].id == won
    e.set_due(won, (_date.today() - timedelta(days=1)).isoformat())
    b4 = e.briefing()
    assert b4["due"] and b4["due"][0][0].id == won and len(b4["due"][0]) == 4
    e.set_due(won, None)
    assert won not in e.due_map()
    print("ledger OK")

    print("\nALL GREEN")


if __name__ == "__main__":
    main()

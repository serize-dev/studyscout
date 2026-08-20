"""Headless TUI smoke test — boots every screen incl. sponsors + sort modal."""

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from studyscout.engine import Engine                       # noqa: E402
from studyscout.models import Contact, Site, Study         # noqa: E402
from studyscout.tui.app import StudyScoutApp              # noqa: E402
from studyscout.tui.launcher import LauncherScreen         # noqa: E402
from studyscout.tui.main_screen import MainScreen          # noqa: E402
from studyscout.tui.modals import TextModal                # noqa: E402
from studyscout.tui.sorting import SortModal               # noqa: E402
from studyscout.tui.splash import Splash                   # noqa: E402
from studyscout.tui.sponsors import SponsorScreen          # noqa: E402

STUDIES = [
    Study(nct="NCT10000001", title="Surfactant strategies in preterm infants",
          status="RECRUITING", phases=["PHASE3"], conditions=["RDS"],
          sponsor="Acme Pharma", sponsor_class="INDUSTRY", enrollment=400,
          start=date(2026, 5, 1),
          sites=[Site(facility="Riverside NICU", city="Nashville", state="TN",
                      contacts=[Contact(name="Jane CRA", email="jane@acme.test")])],
          central_contacts=[Contact(name="Central BD", email="bd@acme.test")]),
    Study(nct="NCT10000002", title="HIE cooling adjunct study",
          status="NOT_YET_RECRUITING", phases=["PHASE2"], conditions=["HIE"],
          sponsor="Acme Pharma", sponsor_class="INDUSTRY", enrollment=120,
          start=date(2026, 6, 15),
          central_contacts=[Contact(name="Central BD", email="bd@acme.test")]),
    Study(nct="NCT10000003", title="Neonatal sepsis outcomes registry",
          status="RECRUITING", phases=[], conditions=["Neonatal Sepsis"],
          sponsor="State University", sponsor_class="OTHER", enrollment=2000,
          start=date(2026, 1, 10)),
]


async def main() -> None:
    eng = Engine()
    eng.store.upsert(STUDIES)
    app = StudyScoutApp(engine=eng)
    async with app.run_test(size=(150, 42)) as pilot:
        await pilot.pause(0.4)
        assert isinstance(app.screen, Splash), type(app.screen).__name__
        await pilot.press("space")
        await pilot.pause(0.3)
        assert isinstance(app.screen, LauncherScreen), type(app.screen).__name__
        await pilot.press("enter")          # Jack in → deck
        await pilot.pause(0.3)
        # First landing of the day → the morning briefing pops over the deck.
        if isinstance(app.screen, TextModal):
            app.save_screenshot("/tmp/sf_briefing.svg")
            await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen), type(app.screen).__name__
        # 'b' reopens it on demand
        await pilot.press("b"); await pilot.pause(0.2)
        assert isinstance(app.screen, TextModal), type(app.screen).__name__
        await pilot.press("escape"); await pilot.pause(0.1)
        assert isinstance(app.screen, MainScreen), type(app.screen).__name__
        app.save_screenshot("/tmp/sf_main.svg")

        # sort modal on the deck: pick enrollment (4), then flip it
        await pilot.press("s"); await pilot.pause(0.2)
        assert isinstance(app.screen, SortModal), type(app.screen).__name__
        app.save_screenshot("/tmp/sf_sort.svg")
        await pilot.press("4"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)
        scr = app.screen
        assert scr.sort_key == "enrollment" and scr.view[0][0].enrollment == 2000
        await pilot.press("s"); await pilot.pause(0.1)
        await pilot.press("4"); await pilot.pause(0.2)   # same field → flipped
        assert scr.sort_flipped and scr.view[0][0].enrollment == 120, \
            (scr.sort_key, scr.sort_flipped, scr.view[0][0].enrollment)

        # sponsors screen
        await pilot.press("S"); await pilot.pause(0.3)
        assert isinstance(app.screen, SponsorScreen), type(app.screen).__name__
        sp = app.screen
        assert sp.view and sp.view[0].name == "Acme Pharma", [d.name for d in sp.view]  # bd sort
        app.save_screenshot("/tmp/sf_sponsors.svg")

        # dossier zoom
        await pilot.press("enter"); await pilot.pause(0.2)
        assert isinstance(app.screen, TextModal), type(app.screen).__name__
        app.save_screenshot("/tmp/sf_dossier.svg")
        await pilot.press("escape"); await pilot.pause(0.1)

        # sponsor sort modal: name (7)
        await pilot.press("s"); await pilot.pause(0.2)
        assert isinstance(app.screen, SortModal)
        await pilot.press("7"); await pilot.pause(0.2)
        assert sp.sort_key == "name" and sp.view[0].name == "Acme Pharma"

        # v1.3.0 — W = expanded dossier (web intel), Brain.web_hunt mocked at
        # CLASS level (instance attrs don't intercept dispatch)
        from unittest import mock
        from studyscout.ai.client import Brain
        from studyscout.tui.sponsors import dossier_view
        CANNED = ("THE COMPANY — Acme Pharma, neonatal analgesia programs.\n"
                  "FRESH SIGNALS — 2026-07: phase 3 readout positive.\n"
                  "WHO TO REACH — Site Selection Lead, Clinical Ops.\n"
                  "THE ANGLE — pitch our NICU census before Q4 site expansion.")

        async def fake_hunt(self, system, user, max_searches=5):
            assert "Acme Pharma" in user       # dossier context reached the hunt
            return CANNED
        with mock.patch.object(Brain, "web_hunt", fake_hunt), \
             mock.patch.object(Brain, "enabled", property(lambda self: True)):
            await pilot.press("W"); await pilot.pause(0.4)
        d = next(x for x in sp.view if x.name == "Acme Pharma")
        assert d.intel == CANNED and d.intel_at, (d.intel[:40], d.intel_at)
        assert "EXPANDED DOSSIER" in dossier_view(d).plain
        # stored intel flows into the consolidated-pitch context
        from studyscout.ai.consigliere import _dossier_context
        assert "FRESH SIGNALS" in _dossier_context(d)

        # back to the deck
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen), type(app.screen).__name__

        # reg handoff checklist: open, toggle first item, close
        from studyscout.tui.reg import RegModal
        await pilot.press("R"); await pilot.pause(0.2)
        assert isinstance(app.screen, RegModal), type(app.screen).__name__
        app.save_screenshot("/tmp/sf_reg.svg")
        await pilot.press("space"); await pilot.pause(0.1)   # check off item 1
        reg = app.screen
        assert sum(1 for _i, d in reg.items if d) == 1
        study_id = reg.study.id
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)
        assert eng.reg_progress(study_id)[0] == 1            # persisted

        # v1.2.0 — z on the list = full table with header-click sorting
        from studyscout.tui.zoom import StudiesModal
        scr = app.screen
        scr.query_one("#listings").focus(); await pilot.pause(0.1)
        await pilot.press("z"); await pilot.pause(0.3)
        assert isinstance(app.screen, StudiesModal), type(app.screen).__name__
        zm = app.screen
        zt = zm.query_one("#zoomtable")
        assert len(zt.columns) == 10, len(zt.columns)
        app.save_screenshot("/tmp/sf_zoom.svg")
        # header click: column 5 = ENROLL → biggest first; again flips
        # (handlers only read column_index — duck-type the event)
        from types import SimpleNamespace
        zm.on_data_table_header_selected(SimpleNamespace(column_index=5))
        await pilot.pause(0.1)
        assert zm.sort_key == "enrollment" and zm.rows[0][0].enrollment == 2000
        zm.on_data_table_header_selected(SimpleNamespace(column_index=5))
        await pilot.pause(0.1)
        assert zm.sort_flipped and zm.rows[0][0].enrollment == 120
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)

        # v1.2.0 — deck header-click sorting (column 3 = SITE)
        scr.on_data_table_header_selected(SimpleNamespace(column_index=3))
        await pilot.pause(0.1)
        assert scr.sort_key == "sites" and scr.view[0][0].n_sites >= scr.view[-1][0].n_sites

        # v1.2.0 — stale rows: a search that misses old inbox rows hides them
        from datetime import datetime
        stamp = datetime.now().isoformat(timespec="seconds")
        eng.store.upsert([STUDIES[0]], stamp=stamp)      # only study 1 re-caught
        eng.store.set_meta("last_search_at", stamp)
        scr.reload(); await pilot.pause(0.1)
        stale_now = eng.store.stale_ids()
        # study 2 was moved through the pipeline by the reg test? it stays if worked;
        # at minimum the untouched NEW rows not re-caught are stale
        assert stale_now, "expected stale rows"
        assert all(r[0].id not in stale_now for r in scr.view)
        shown_hidden = len(scr.view)
        await pilot.press("a"); await pilot.pause(0.1)   # reveal stale
        assert len(scr.view) > shown_hidden
        await pilot.press("a"); await pilot.pause(0.1)   # hide again
        assert len(scr.view) == shown_hidden

        # v1.4.0 — dedicated kanban: worked stages only, cards, unflag-to-inbox
        from studyscout.models import Stage
        from studyscout.tui.kanban import BOARD_ORDER, KanbanScreen
        assert Stage.NEW not in BOARD_ORDER            # inbox lives on the deck
        eng.set_stage(STUDIES[0].id, Stage.FLAGGED)
        await pilot.press("K"); await pilot.pause(0.4)
        kb = app.screen
        assert isinstance(kb, KanbanScreen), type(kb).__name__
        app.save_screenshot("/tmp/sf_kanban.svg")
        assert len(kb.board.get(Stage.FLAGGED, [])) == 1
        flagged_col = BOARD_ORDER.index(Stage.FLAGGED)
        kb.col, kb.sel = flagged_col, 0
        kb._restyle(); await pilot.pause(0.1)
        await pilot.press("u"); await pilot.pause(0.3)   # unflag → inbox, off board
        assert len(kb.board.get(Stage.FLAGGED, [])) == 0, kb.board.get(Stage.FLAGGED)
        assert dict(eng.counts()).get(Stage.NEW, 0) >= 1
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)

        # v1.5.0 — CLOSED + FUTURE columns exist; 9 = future outreach
        assert Stage.CLOSED in BOARD_ORDER and Stage.FUTURE in BOARD_ORDER
        eng.set_stage(STUDIES[1].id, Stage.CLOSED)
        await pilot.press("K"); await pilot.pause(0.4)
        kb = app.screen
        assert len(kb.board.get(Stage.CLOSED, [])) == 1     # no more void
        fcol = BOARD_ORDER.index(Stage.CLOSED)
        kb.col, kb.sel = fcol, 0
        kb._restyle(); await pilot.pause(0.1)
        await pilot.press("9"); await pilot.pause(0.3)      # closed → future
        assert len(kb.board.get(Stage.FUTURE, [])) == 1
        assert len(kb.board.get(Stage.CLOSED, [])) == 0
        await pilot.press("escape"); await pilot.pause(0.2)
        # future_due: backdate the stage stamp past the nudge window
        eng.store.con.execute(
            "UPDATE pipeline SET updated_at=? WHERE study_id=?",
            ("2026-01-01T08:00:00", STUDIES[1].id))
        eng.store.con.commit()
        due = eng.store.future_due(45)
        assert due and due[0][0] == STUDIES[1].sponsor and due[0][1] > 45, due
        b = eng.briefing()
        assert b["future"] and b["future"][0][0] == STUDIES[1].sponsor
        eng.set_stage(STUDIES[1].id, Stage.NEW)             # restore
        app.screen.reload(); await pilot.pause(0.2)

        # v1.4.1 — the board inherits the deck's / filter; `a` lifts it
        eng.set_stage(STUDIES[0].id, Stage.FLAGGED)      # surfactant study
        eng.set_stage(STUDIES[2].id, Stage.CONTACTED)    # sepsis registry
        app.screen.text_filter = "surfactant"
        await pilot.press("K"); await pilot.pause(0.4)
        kb = app.screen
        assert kb.text_filter == "surfactant" and not kb.show_all
        assert len(kb.board.get(Stage.FLAGGED, [])) == 1
        assert len(kb.board.get(Stage.CONTACTED, [])) == 0   # filtered out
        await pilot.press("a"); await pilot.pause(0.3)       # lift the filter
        assert kb.show_all and len(kb.board.get(Stage.CONTACTED, [])) == 1
        await pilot.press("a"); await pilot.pause(0.3)       # back to filtered
        assert not kb.show_all and len(kb.board.get(Stage.CONTACTED, [])) == 0
        await pilot.press("escape"); await pilot.pause(0.2)
        app.screen.text_filter = ""
        eng.set_stage(STUDIES[0].id, Stage.NEW)          # restore for later tests
        eng.set_stage(STUDIES[2].id, Stage.NEW)
        app.screen.reload(); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)

        # v1.4.0 — filters sort handoff: TARGET "sort deck by" drives deck order
        eng.cfg.set("filters.sort", "sites"); eng.cfg.save()
        chosen = str(eng.cfg.get("filters.sort", "start"))
        if chosen in ("start", "sites", "enrollment"):   # the action_filters logic
            app.screen.sort_key, app.screen.sort_flipped = chosen, False
        app.screen.apply_filter(); await pilot.pause(0.1)
        v = app.screen.view
        assert app.screen.sort_key == "sites"
        assert all(v[i][0].n_sites >= v[i+1][0].n_sites for i in range(len(v)-1)), \
            [(x[0].nct, x[0].n_sites) for x in v]

        # FILTERS: dropdowns are gone — radio sets, nothing overlays (v1.1.0)
        from textual.widgets import RadioButton, RadioSet, Select
        from studyscout.tui.filters_screen import RADIO_GROUPS, FiltersScreen
        fs = FiltersScreen(eng)
        app.push_screen(fs); await pilot.pause(0.3)
        assert not list(fs.query(Select)), "a Select dropdown survived"
        for key in RADIO_GROUPS:
            rs = fs.query_one(f"#{key}", RadioSet)
            assert rs.pressed_index >= 0, f"{key}: nothing pressed"
        app.save_screenshot("/tmp/sf_filters.svg")
        # flip site_mode to multi, collect, verify it landed in config
        buttons = list(fs.query_one("#site_mode", RadioSet).query(RadioButton))
        buttons[1].value = True; await pilot.pause(0.1)
        fs._collect()
        assert eng.cfg.get("filters.site_mode") == "multi", \
            eng.cfg.get("filters.site_mode")
        # v1.4.0 — net banner reflects keyword state; NEW HUNT clears in place
        from textual.widgets import Input, SelectionList, Static
        kw = fs.query_one("#keyword", Input)
        kw.value = "neonatal OR preterm"; await pilot.pause(0.2)
        assert "ACTIVE" in fs.query_one("#net-banner", Static).renderable.plain
        fs.action_new_hunt(); await pilot.pause(0.2)
        assert fs.query_one("#keyword", Input).value == ""
        assert fs.query_one("#condition", Input).value == ""
        assert not list(fs.query_one("#ages", SelectionList).selected)
        assert "ACTIVE" not in fs.query_one("#net-banner", Static).renderable.plain
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)

        # v1.5.3 — ctrl+e in WM chat folds the conversation into an email draft
        CANNED_EMAIL = ("Subject: Site interest — the refined angle\n\n"
                        "Dr. X — exactly the hook we sharpened in chat.")

        async def fake_email(self, system, user, *, model=None, max_tokens=None, history=None):
            stable = system[0]["text"] if isinstance(system, list) else system
            assert "the conversation wins" in stable       # chat outranks the defaults
            assert "sharpen the hook" in user              # history rode the wire
            return CANNED_EMAIL
        wm = app.screen.wm_pane
        assert wm is not None
        wm.history.extend([
            {"role": "user", "content": "let's sharpen the hook for the sponsor"},
            {"role": "assistant", "content": "lead with the census, drop the boilerplate"},
        ])
        with mock.patch.object(Brain, "complete", fake_email), \
             mock.patch.object(Brain, "enabled", property(lambda self: True)):
            wm.on_chat_input_compose(None); await pilot.pause(0.5)
        assert isinstance(app.screen, TextModal), type(app.screen).__name__
        assert "refined angle" in app.screen._body
        app.save_screenshot("/tmp/sf_chatmail.svg")
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)
        wm.history.clear()

        # v1.6.0 — ctrl+e fires with the focus ANYWHERE (log / deck), not just
        # inside the chat input (the v1.5.1 focus lesson, chat edition)
        wm.history.extend([
            {"role": "user", "content": "let's sharpen the hook for the sponsor"},
            {"role": "assistant", "content": "lead with the census, drop the boilerplate"},
        ])
        with mock.patch.object(Brain, "complete", fake_email), \
             mock.patch.object(Brain, "enabled", property(lambda self: True)):
            app.screen.query_one("#wm-log").focus(); await pilot.pause(0.1)
            await pilot.press("ctrl+e"); await pilot.pause(0.5)     # from the LOG
            assert isinstance(app.screen, TextModal), type(app.screen).__name__
            await pilot.press("escape"); await pilot.pause(0.2)
            app.screen.query_one("#listings").focus(); await pilot.pause(0.1)
            await pilot.press("ctrl+e"); await pilot.pause(0.5)     # from the DECK
            assert isinstance(app.screen, TextModal), type(app.screen).__name__
            # the draft modal carries the 4-tuple mail ctx (mode included)
            assert len(app.screen._mail) == 4, app.screen._mail
            await pilot.press("escape"); await pilot.pause(0.2)
        wm.history.clear()
        assert isinstance(app.screen, MainScreen)

        # v1.6.0 — x = NOT ACCEPTING: sinks on the deck, owns a board column
        scr = app.screen
        assert Stage.UNAVAILABLE in BOARD_ORDER
        scr.query_one("#listings").focus(); await pilot.pause(0.1)
        scr.query_one("#listings").move_cursor(row=0); await pilot.pause(0.1)
        parked_id = scr.current_id
        await pilot.press("x"); await pilot.pause(0.2)
        assert scr.by_id[parked_id][1] == Stage.UNAVAILABLE
        assert scr.view[-1][0].id == parked_id          # dead-sink to the bottom
        await pilot.press("K"); await pilot.pause(0.4)
        kb = app.screen
        assert len(kb.board.get(Stage.UNAVAILABLE, [])) == 1

        # v1.6.0 — p/P print: detailed listing on screen + a text file on disk
        import os as _os
        kb.col = BOARD_ORDER.index(Stage.UNAVAILABLE)
        kb._restyle(); await pilot.pause(0.1)
        kb.action_print_column(); await pilot.pause(0.3)
        assert isinstance(app.screen, TextModal), type(app.screen).__name__
        body = app.screen._body
        assert "NOT ACCEPTING" in body and "NCT" in body and "sponsor:" in body
        exports = sorted(Path(_os.environ["STUDYSCOUT_DATA"]).glob("pipeline-*.txt"))
        assert exports, "print/export wrote no file"
        assert "NOT ACCEPTING" in exports[-1].read_text()
        await pilot.press("escape"); await pilot.pause(0.2)
        kb.action_print_board(); await pilot.pause(0.3)
        assert isinstance(app.screen, TextModal)
        body = app.screen._body
        for st in BOARD_ORDER:                              # every column present
            assert st.label.upper() in body, st
        await pilot.press("escape"); await pilot.pause(0.2)
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)
        eng.set_stage(parked_id, Stage.NEW)                 # restore
        app.screen.reload(); await pilot.pause(0.2)

        # v1.7.0 — C = CONDUCTING: the live book between WON and CLOSED
        scr = app.screen
        assert Stage.CONDUCTING in BOARD_ORDER
        assert BOARD_ORDER.index(Stage.CONDUCTING) == BOARD_ORDER.index(Stage.WON) + 1
        scr.query_one("#listings").focus(); await pilot.pause(0.1)
        scr.query_one("#listings").move_cursor(row=0); await pilot.pause(0.1)
        live_id = scr.current_id
        await pilot.press("C"); await pilot.pause(0.2)      # shift+c ≠ c (chat)
        assert scr.by_id[live_id][1] == Stage.CONDUCTING
        assert scr.view[0][0].id == live_id                 # ALIVE — does not sink
        await pilot.press("K"); await pilot.pause(0.4)
        kb = app.screen
        assert len(kb.board.get(Stage.CONDUCTING, [])) == 1
        kb.action_print_board(); await pilot.pause(0.3)
        assert isinstance(app.screen, TextModal)
        assert "CONDUCTING" in app.screen._body
        await pilot.press("escape"); await pilot.pause(0.2)
        await pilot.press("escape"); await pilot.pause(0.2)
        assert isinstance(app.screen, MainScreen)
        eng.set_stage(live_id, Stage.NEW)                   # restore
        app.screen.reload(); await pilot.pause(0.2)

        # MODELS: provider radio rebuilds the model radio list live
        from studyscout.tui.models_screen import CATALOG, ModelsScreen
        msn = ModelsScreen(eng)
        app.push_screen(msn); await pilot.pause(0.3)
        assert not list(msn.query(Select))
        prov_btns = list(msn.query_one("#prov", RadioSet).query(RadioButton))
        prov_btns[1].value = True; await pilot.pause(0.3)    # → openrouter
        assert eng.cfg.provider() == "openrouter"
        model_btns = list(msn.query_one("#model", RadioSet).query(RadioButton))
        assert len(model_btns) == len(CATALOG["openrouter"]), len(model_btns)
        prov_btns = list(msn.query_one("#prov", RadioSet).query(RadioButton))
        prov_btns[0].value = True; await pilot.pause(0.3)    # back to anthropic
        assert eng.cfg.provider() == "anthropic"
        await pilot.press("escape"); await pilot.pause(0.2)
    print("ALL SCREENS OK")

    # ---- doctor + backup/restore (headless, offline) ------------------------
    import io
    import os
    import tarfile

    from studyscout import backup as bx
    from studyscout.doctor import FAIL, render, run_doctor

    rep = await run_doctor(offline=True)
    sections = {c.section for c in rep.checks}
    assert {"PROFILE", "WINTERMUTE", "FILTERS", "DATABASE"} <= sections, sections
    assert rep.worst != FAIL, render(rep, color=False)
    cfg_root = Path(os.environ["STUDYSCOUT_PROFILE"]).parent
    scratch_root = Path(os.environ["STUDYSCOUT_DATA"]).parent
    canary = cfg_root / "canary.txt"
    canary.write_text("original")
    box = bx.backup(scratch_root / "box.tar.gz")
    assert (box.stat().st_mode & 0o777) == 0o600
    canary.write_text("mutated")
    bx.restore(box, snapshot=False)
    assert canary.read_text() == "original"
    evil = scratch_root / "evil.tar.gz"
    with tarfile.open(evil, "w:gz") as t:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    try:
        bx.peek(evil)
        raise AssertionError("hostile tarball accepted")
    except ValueError:
        pass
    print("DOCTOR + BLACK BOX OK")


if __name__ == "__main__":
    asyncio.run(main())
    print("=== screenshots ===")
    for f in ("sf_main", "sf_sort", "sf_sponsors", "sf_dossier", "sf_reg"):
        p = Path(f"/tmp/{f}.svg")
        print(f"  {f}.svg", p.stat().st_size if p.exists() else "MISSING")

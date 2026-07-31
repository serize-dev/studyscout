# STUDY//SCOUT — THE HANDBOOK
### v1.5.0 · the definitive manual

A phosphor-green terminal for clinical-trials business development. It hunts
ClinicalTrials.gov for studies that fit your site, groups them into **sponsor
dossiers**, tracks the BD pipeline on a kanban, drafts consolidated outreach
with Wintermute (Claude), and nags you about relationships going quiet.

House law: **the LLM proposes, clockwork verifies, you confirm.** By design
there is **no fit scoring** — you rank fits in your head; the tool's job is
to put everything about a sponsor in front of you at once.

---

## 1 · Getting in

```
sudo dnf install ./studyscout-1.5.0-1.x86_64.rpm     # note the ./
studyscout
studyscout doctor        # pre-flight: profile, key, API, database
```

(Only the `.rpm` goes to dnf. The bare `studyscout` binary in a portable
tarball is the already-built program — `./install.sh` there installs it to
`~/.local/bin` with no sudo at all.)

First run seeds `~/.config/studyscout/profile.toml` plus **site.md** — your
site's capabilities, populations, and equipment. Wintermute reads it for
every pitch; keep it honest and specific. Anthropic key goes in
`⌁ CONNECTIONS` (or `ANTHROPIC_API_KEY`); no key = search and dossiers work,
outreach drafting is dark.

## 2 · The hunt

`⟲ SEARCH` (or `studyscout search` headless) pulls ClinicalTrials.gov v2 —
no API key needed, it's a public federal API.

**FILTERS** (the TARGET panel): condition, keyword net (your OR-expression),
excludes, then pure checkbox/radio glory — status, phase, age, funder as
check-lists; type / where / #sites / sort as radio groups. Nothing overlays
anything. `ctrl+s` searches, `esc` closes.

Doctor tip: if targeting is empty (no condition, no keyword), you're trawling
the whole ocean — `studyscout doctor` will call it out.

## 3 · The board & dossiers

- **Pipeline stages:** New → Flagged → Contacted → Waiting → Replied →
  Meeting → Won · **Future** (`9`) · Declined · Closed. Single keys move the
  selected study (see F1); stage changes stamp the sponsor's last-touch.
- **`9` — FUTURE OUTREACH** (v1.5.0): "current study closed, but the CMO said
  call us for the next one" — warm relationships, not dead ones. The board has
  a FUTURE column, and the **morning briefing nags you** when a FUTURE sponsor
  has been parked ≥ `followup.future_nudge_days` (default 45) — the keep-warm
  clock. CLOSED also has its own board column now (the `8` key no longer sends
  cards into the void).
- **`K` / menu → PIPELINE — the kanban board** (v1.4.0): worked stages only —
  the inbox stays on the deck. Wide scrollable columns, gridlined cards
  (NCT · phase · title · sponsor · notes). `0` or `u` on a card un-flags it
  back to the inbox — **off the board entirely**. The board **inherits the
  deck's `/` text filter** (v1.4.1) — `/covid` on the deck, then K = only the
  covid pipeline; `a` on the board lifts/re-applies the filter.
- **The keyword-net trap**: whatever you put in the Keyword box silently ANDs
  into EVERY search — a leftover net from last month's hunt will poison a new
  condition search. The FILTERS panel shows an amber **keyword net ACTIVE**
  banner whenever the box is non-empty, and the **✕ new hunt** button clears
  condition/net/ages/phases/funders in one tap for a clean-slate search.
- **`S` — Sponsor dossier:** every trial from that sponsor in one view,
  contacts deduped across NCTs, per-sponsor notes, last touch.
  `m` drafts ONE consolidated pitch covering all their relevant trials.
- **`W` — the expanded dossier:** Wintermute searches the live web for that
  sponsor — pipeline news, readouts/starts, deals, and names tied to clinical
  ops or site selection — and writes a dated intel brief onto the dossier
  (THE COMPANY / FRESH SIGNALS / WHO TO REACH / THE ANGLE). It's stored, shown
  in the dossier view, and automatically fed into the `m` pitch. Uses tokens +
  live search; runs only when you press it. Anthropic provider only.
- **`b` — morning briefing:** what changed since yesterday (deltas), sponsors
  gone quiet (`followup.nudge_days`), and today's top three.
- **`R` — reg handoff:** after a WIN, the CDA→SIV paperwork checklist
  (edit the template in `regulatory.checklist`). The briefing nags open items.
- **`s`** sorts (same key flips direction) — or **click any column header**
  on the deck or in the zoom table; clicking the same header flips.
- **`z`** on the studies list opens the **full table** — every column (NCT,
  phase, status, sites, enrollment, start, contact, sponsor, title), header
  sorting, `enter` jumps the deck to the selected row. `z` on the detail pane
  zooms the study text.
- **Stale rows:** after each search, inbox studies the latest catch did NOT
  include are hidden (never deleted — your worked pipeline is untouchable).
  The status bar counts them; **`a`** shows/hides. This is why tightening
  filters visibly tightens the deck.
- The TARGET panel's **"Sort deck by"** choice (newest / most sites / biggest
  enroll) sets the deck order after each search.

## 4 · Field maintenance

```
studyscout doctor            # what's broken, in one screen
studyscout doctor --ping     # + one tiny paid call proving the AI key works
studyscout backup            # black box → ~/studyscout-backup-<stamp>.tar.gz
studyscout restore <tar.gz>  # put it back (auto-snapshots current state first)
```

The backup holds your **BD memory** — pipeline, sponsor notes, outreach
history. That's business value; back it up before anything happens to the
laptop. It also contains your API key (profile.toml), hence chmod 600.

**Symptom table:**

| Symptom | Likely cause | Fix |
|---|---|---|
| Search returns nothing | filters too tight, or API down | `doctor`; loosen phases/statuses |
| Outreach drafting dark | AI key missing/rejected | `doctor --ping` |
| Briefing feels stale | nudge window | tune `followup.nudge_days` |
| dnf refuses the package | you fed it the binary, not the .rpm | `sudo dnf install ./studyscout-*.rpm` |

## 5 · Building from source

```
python3 -m venv .venv && .venv/bin/pip install textual anthropic httpx platformdirs tomli-w
PYTHONPATH=src .venv/bin/python -m studyscout
bash packaging/build_rpm.sh      # Fedora RPM; needs rpmbuild + binutils
```

Version lives in three places: `pyproject.toml`, `src/studyscout/__init__.py`,
`packaging/build_rpm.sh`.

---

*Scan the sky. Work the dossier. Win the study.* 📡

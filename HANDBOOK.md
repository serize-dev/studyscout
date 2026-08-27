# STUDY//SCOUT — THE HANDBOOK
### v1.9.0 · the definitive manual

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
  Meeting → Won → **Conducting** (`C`) · **Future** (`9`) · Declined ·
  **Not a Good Fit** (`n`) · **Not Accepting** (`x`) · Closed. Single keys move the selected study
  (see F1); stage changes stamp the sponsor's last-touch.
- **`C` — CONDUCTING** (v1.7.0): the studies your site is **running right
  now** — the live book, and the seed of the pseudo-CTMS. The site lifecycle
  reads left to right on the board: `6` WON (landed, startup paperwork — the
  `R` checklist keeps nagging here) → `C` CONDUCTING (enrolling/active) →
  `8` CLOSED (completed archive). Conducting counts as an alive relationship
  in the sponsor dossiers.
- **`x` vs `8` — the two graveyards** (v1.6.0): `x` NOT ACCEPTING = the study
  isn't taking new sites — you never got in. `8` CLOSED = the archive of
  studies **your site ran** that have since completed. Both sink to the bottom
  of the deck and live in their own board columns.
- **`n` — NOT A GOOD FIT** (v1.8.0): the third graveyard, and the only one
  that's *your* verdict — you screened it (pop too small, wrong phase, no
  pharmacy support, whatever) and passed. `7` DECLINED = *they* said no;
  `x` NOT ACCEPTING = never got in; `n` = you said no. Sinks on the deck,
  own board column, dead in the dossier counts.
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
- **`p` / `P` — print the board** (v1.6.0): `p` exports the current column,
  `P` the whole board — a detailed listing (NCT · phase · status · title ·
  sponsor · contact · notes · link) shown on screen (`c` copies) **and saved
  as a text file in the data dir** — send it to paper with `lp <file>`.
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
- **`ctrl+e` in chat — fold the conversation into an email** (v1.5.3): the `m`
  draft starts cold from the study; this one starts from the chat. Refine the
  angle with Wintermute — hooks, wording, tone — then `ctrl+e` produces the
  final email *as agreed in the conversation*, in the same draft modal
  (`c` copy · `o` open in mail). Where the chat and the default email rules
  disagree, the chat wins. Works in the side pane and the full screen (`c`) —
  and since v1.6.0 the key fires with the focus ANYWHERE (log, deck, detail),
  not just inside the chat input.
- **`o` on a draft — where the email opens** (v1.6.0): `ui.mail_mode` in
  `profile.toml` picks the route. `"mailto"` (default) hands the draft to the
  system mail client (`ui.mail_command` overrides the launcher and may use
  `{url} {to} {subject} {body}` placeholders). `"outlook"` opens **Outlook
  Web's compose deeplink in the browser** — draft prefilled in your O365
  account. That's the route for Outlook shops: desktop wrappers like Prospect
  Mail take no compose arguments, but the browser deeplink reaches the same
  account/mailbox.
- **`b` — morning briefing:** what changed since yesterday (deltas), sponsors
  gone quiet (`followup.nudge_days`), and today's top three.
- **`R` — reg handoff:** the startup paperwork checklist, **grouped by
  phase** since v1.9.0 (FEASIBILITY → REG DOCS → IRB → CONTRACTS →
  ACTIVATION). `space` checks an item off (it stamps its own date), **`-`
  marks it N/A** (doesn't apply to this study — no 1572 on a non-IND device
  trial — and counts as complete), `a` adds an ad-hoc item for this study
  only, `e` notes an item ("IRB reviewer asked for X"), `d` drops an ad-hoc
  item, `p` prints. The title shows the startup-day clock. Works on the
  deck, the pipeline board, the regulatory board, the leads screen and the
  follow-up ledger. Edit the template in `profile.toml → regulatory.phases`
  (item text is the key the checked state hangs on — rename = start over;
  a customized v1.x flat `regulatory.checklist` is auto-sorted into phases
  by keyword, so upgrades don't lose anything).
- **`G` — REGULATORY board** (also in the menu): the startup gauntlet as a
  second board. Columns are the phases plus ACTIVATED; **nothing is dragged
  — a study sits in the first phase that still has an open item and moves
  itself as you check things off.** Cards show `▤ done/total`, the startup
  day count (amber past 60) and the next open item. `enter`/`R` opens the
  checklist right there, **`C` promotes to CONDUCTING** (the handoff from
  paperwork to the live book — it stays on the board while items are open),
  `t` sets a follow-up, `p`/`P` print. Studies land here once they hit
  MEETING / WON / CONDUCTING on the pipeline; pipeline cards show the same
  `▤` progress. The briefing nags open items.
- **`L` — LEADS** (also in the menu): off-registry prospects. Not everything
  worth chasing has an NCT — a PI you met, a state genetics program, an act
  with grant money behind it, a network that said "call us". `a` adds one
  (title, organization, contact, link, topics, kind, starting stage, a
  follow-up date, and free text Wintermute reads); `enter` edits; `d` drops
  (with a confirm — leads are the only thing Scout ever deletes). A lead
  gets a `LEAD-####` id and lives in the **same store as the studies**, so
  it rides everything with zero special cases: the stage digits, the `K`
  board, the `S` dossier (grouped by organization — a lead for Acme joins
  Acme's dossier next to their NCTs), `e` notes, `m` outreach (Wintermute
  is told it's off-registry and must not invent trial details), `c` chat,
  `R` reg, `t`/`T` follow-up. Leads show on the deck as `Lead` status and
  are never "stale" — searches don't touch them.
- **`t` / `T` — FOLLOW-UP, the tickle file** (also in the menu): `t` on any
  study or lead (deck · board · reg board · leads) sets a date — forgiving
  entry: `9/15`, `+7`, `+2w`, `+1m`, `mon`, `tomorrow`, `2026-09-15`, blank
  clears. `T` opens the ledger: **OVERDUE → DUE TODAY → UPCOMING (next
  `followup.due_horizon_days`, default 14) → LATER**, then the un-dated
  pressure Scout already tracked — open reg paperwork, quiet sponsors,
  FUTURE call-backs due. `enter` jumps to that row on the deck, `space`
  marks a follow-up done (clears the date — `t` sets the next one), `t`
  reschedules, `R` works the checklist, `p` prints. Due dates ride the
  detail pane and the board cards (`⏰ overdue 3d` in red); the status bar
  counts what's due; the briefing leads with them and puts them at the top
  of TODAY'S TOP 3.
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

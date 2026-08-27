"""Wintermute — the BD consigliere for StudyScout."""

from __future__ import annotations

from typing import Optional

from ..config import Config
from ..models import SponsorDossier, Stage, Study
from .client import Brain, BrainError, load_site, system_blocks

PERSONA = """You are Wintermute, the business-development consigliere inside StudyScout — \
a phosphor-green clinical-trials BD deck, Neuromancer-noir but genuinely useful and concise. \
Your operator runs a clinical research SITE (its population, setting, and capabilities are in \
the site profile below — ground every fit judgment in THAT, not in assumptions) and hunts \
ClinicalTrials.gov for trials that would want to add his site. He reaches out to the study's \
PI / sponsor / central contact to pitch his site as an investigator site. Help him: judge \
whether a study is a realistic add for his site, draft outreach, prep talking points, and \
sharpen his site profile. Be honest about weak fits."""

EMAIL_SYSTEM = PERSONA + """

TASK: Draft a short, credible outreach email to this study's contact (PI or central/sponsor contact) \
expressing the site's interest in participating. Lead with a specific hook tied to THIS study \
(condition, phase, population), state the site's fit in 2-3 lines using the site profile (setting, \
population/volume, PI, relevant capabilities), and close with a low-friction ask (a brief call to \
explore adding the site). Warm, professional, no fluff, no fabricated credentials or numbers. \
Output ONLY the email — a subject line then the body."""


SPONSOR_EMAIL_SYSTEM = PERSONA + """

TASK: Draft ONE consolidated BD outreach email to this SPONSOR (not a single study) — \
they run several trials our site could serve, and one strong email beats three cold ones. \
Lead with the sharpest hook across their portfolio (the conditions/phases our site can \
actually enroll), state the site's fit in 2-4 lines from the site profile, name the \
specific NCT numbers we're interested in, and close with a single low-friction ask (a \
brief intro call). Warm, professional, no fluff, no fabricated credentials or numbers. \
Output ONLY the email — a subject line then the body."""


ENRICH_SYSTEM = PERSONA + """

TASK: Research this sponsor on the live web and write the EXPANDED DOSSIER — the intel \
brief a business developer reads before picking up the phone. Search for: recent pipeline \
news in pain/analgesia and adjacent programs, trial readouts, starts or expansions, \
approvals/setbacks, partnerships or acquisitions, and any names/roles tied to clinical \
operations, site selection, or study startup. Only report what you actually FOUND — no \
guessing, no padding; if a section comes up empty, say 'nothing found'. Keep it under \
~350 words, in exactly these sections:

THE COMPANY — two lines: who they are, where their pain/relevant programs stand.
FRESH SIGNALS — dated bullets: readouts, starts, expansions, deals (newest first).
WHO TO REACH — names/titles/functions found for clinical ops or site selection, else \
the best entry route you found (careers page, clinical partnerships email, CRO partner).
THE ANGLE — 2-3 lines: given OUR SITE and their book, the sharpest hook for outreach \
and the right timing.
"""


def _dossier_context(d: SponsorDossier) -> str:
    lines = [
        f"SPONSOR DOSSIER: {d.name} [{d.sponsor_class or '?'}]",
        f"  {d.n_trials} trials in our net · {d.recruiting} recruiting · phases {d.phases}",
    ]
    for s, st, n in d.rows[:10]:
        line = (f"  - {s.nct} · {s.phase_str} · {s.status_short} · "
                f"{', '.join(s.conditions[:3])} · {s.title[:80]}")
        if st != Stage.NEW:
            line += f" · our stage: {st.label}"
        if n:
            line += f" · notes: {n}"
        lines.append(line)
    if d.n_trials > 10:
        lines.append(f"  … +{d.n_trials - 10} more")
    contacts = d.contacts(4)
    if contacts:
        lines.append("  Contacts: " + "  |  ".join(c.render() for c in contacts))
    if d.notes:
        lines.append(f"  Our notes on this sponsor: {d.notes}")
    if d.intel:
        lines.append(f"  WEB INTEL (fetched {d.intel_at[:10] or '?'}):\n{d.intel}")
    return "\n".join(lines)


def _study_context(study: Optional[Study], notes: str = "") -> str:
    if not study:
        return "No study selected."
    c = study.best_contact()
    sites = "; ".join(f"{s.facility} ({s.where()})" for s in study.sites[:6]) or "—"
    if study.is_lead:
        # v1.9.0 — an off-registry prospect: no NCT, no registry record. Never
        # invent trial details; work from what the operator typed.
        return (
            f"SELECTED LEAD (off-registry prospect — NOT a ClinicalTrials.gov record; "
            f"there is no NCT number, do not invent one):\n"
            f"  {study.nct} — {study.title}\n"
            f"  Organization: {study.sponsor or '?'} [{study.sponsor_class or '?'}]\n"
            f"  Topics: {', '.join(study.conditions[:8]) or '—'}\n"
            f"  Contact: {c.render()}\n"
            + (f"  Link: {study.link}\n" if study.link else "")
            + f"  Your notes: {notes or '(none)'}\n"
            f"  What you know: {(study.summary or '')[:1600]}"
        )
    return (
        f"SELECTED STUDY:\n"
        f"  {study.nct} — {study.title}\n"
        f"  Sponsor: {study.sponsor} [{study.sponsor_class or '?'}]"
        + (f"; collaborators: {', '.join(study.collaborators[:4])}" if study.collaborators else "") + "\n"
        f"  Phase: {study.phase_str}  ·  Status: {study.status_short}  ·  Type: {study.study_type}  "
        f"·  Enrollment: {study.enrollment}  ·  Sites: {study.n_sites}\n"
        f"  Conditions: {', '.join(study.conditions[:8])}\n"
        f"  Contact: {c.render()}\n"
        f"  Sites: {sites}\n"
        f"  URL: {study.url}\n"
        f"  Your notes: {notes or '(none)'}\n"
        f"  Summary: {(study.summary or '')[:1600]}"
    )


class Consigliere:
    def __init__(self, brain: Brain, cfg: Config):
        self.brain = brain
        self.cfg = cfg
        self._chat_study_id = None   # v1.5.2: last study discussed in chat

    @property
    def enabled(self) -> bool:
        return self.brain.enabled

    async def chat(self, history: list[dict], study: Optional[Study] = None, notes: str = "",
                   user_msg: str = "") -> str:
        site = load_site(self.cfg)
        # Stable prefix first (cacheable across turns); per-study context after.
        stable = PERSONA + ("\n\nOUR SITE PROFILE:\n" + site if site else "")
        # v1.5.2 — models follow the CONVERSATION over the system block: with a
        # long shared history about earlier studies, Winter kept asking for the
        # NCT even though it rode the system every call. So a study switch is
        # written INTO the shared history where momentum actually lives.
        sid = study.id if study else None
        if study and sid != self._chat_study_id:
            history.append({"role": "user",
                            "content": f"[Context switch — now discussing {study.nct}: "
                                       f"{study.title[:90]} ({study.sponsor})]"})
            history.append({"role": "assistant",
                            "content": f"Locked on {study.nct}. Go."})
        self._chat_study_id = sid
        # Cap what rides the wire: old-study chatter must not drown the present.
        sent = history[-40:] if len(history) > 40 else history
        return await self.brain.complete(
            system_blocks(stable, _study_context(study, notes)), user_msg,
            model=self.brain.model, max_tokens=self.brain.max_tokens, history=sent)

    async def outreach_email(self, study: Study, notes: str = "",
                             outreach_ctx: str = "") -> str:
        site = load_site(self.cfg)
        stable = EMAIL_SYSTEM + ("\n\nOUR SITE PROFILE:\n" + site if site else "")
        volatile = _study_context(study, notes) + (
            "\n\nOUR OUTREACH TRACK RECORD (lean toward what has worked):\n" + outreach_ctx
            if outreach_ctx else "")
        return await self.brain.complete(
            system_blocks(stable, volatile), "Write the outreach email now.",
            model=self.brain.model, max_tokens=1200)

    async def email_from_chat(self, history: list[dict], study: Optional[Study] = None,
                              notes: str = "") -> str:
        """Ctrl+E — fold the chat's refinements into the final outreach email.

        The 'm' draft starts from the study alone; this one starts from the
        conversation — angle, wording, and corrections agreed with Wintermute
        carry over and OUTRANK the default email instructions.
        """
        site = load_site(self.cfg)
        stable = (EMAIL_SYSTEM + ("\n\nOUR SITE PROFILE:\n" + site if site else "")
                  + "\n\nThe operator has been refining the outreach in the conversation "
                    "below — strategy, hooks, phrasing, tone. The email must reflect what "
                    "was agreed there; where the conversation and the instructions above "
                    "disagree, the conversation wins.")
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-40:])
        return await self.brain.complete(
            system_blocks(stable, _study_context(study, notes)),
            "Conversation:\n" + convo + "\n\nWrite the final outreach email now.",
            model=self.brain.model, max_tokens=1200)

    async def sponsor_outreach(self, dossier: SponsorDossier,
                               outreach_ctx: str = "") -> str:
        """The consolidated multi-trial pitch — one email per relationship."""
        site = load_site(self.cfg)
        stable = SPONSOR_EMAIL_SYSTEM + ("\n\nOUR SITE PROFILE:\n" + site if site else "")
        volatile = _dossier_context(dossier) + (
            "\n\nOUR OUTREACH TRACK RECORD (lean toward what has worked):\n" + outreach_ctx
            if outreach_ctx else "")
        return await self.brain.complete(
            system_blocks(stable, volatile), "Write the consolidated outreach email now.",
            model=self.brain.model, max_tokens=1400)

    async def enrich_dossier(self, dossier: SponsorDossier) -> str:
        """Web-hunt the sponsor: the expanded dossier (uses tokens + live search)."""
        site = load_site(self.cfg)
        system = ENRICH_SYSTEM + ("\n\nOUR SITE PROFILE:\n" + site if site else "")
        user = ("Research this sponsor now and write the expanded dossier.\n\n"
                + _dossier_context(dossier))
        max_searches = int(self.cfg.get("ai.web_hunt_max_searches", 5) or 5)
        return await self.brain.web_hunt(system, user, max_searches=max_searches)

    async def revise_site(self, history: list[dict]) -> str:
        """Draft an updated site.md from the conversation."""
        site = load_site(self.cfg)
        system = (PERSONA + "\n\nTASK: Update the operator's site profile (site.md) from this "
                  "conversation. Output the COMPLETE updated file — keep his voice and structure, "
                  "integrate new facts he stated, don't invent. Output ONLY the file content, no fences."
                  + "\n\nCURRENT site.md:\n" + (site or "(empty)"))
        convo = "\n".join(f"{m['role']}: {m['content']}" for m in history[-24:])
        text = await self.brain.complete(system, "Conversation:\n" + convo + "\n\nOutput the full site.md.",
                                         model=self.brain.model, max_tokens=2000)
        lines = text.strip().splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip() + "\n"

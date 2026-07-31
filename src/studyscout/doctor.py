"""Doctor — the pre-flight diagnostic. `studyscout doctor` on the command line.

Checks the rig without touching it: profile syntax, site.md, AI key, a live
ClinicalTrials.gov probe, filter sanity, and database health. Free HTTP checks
run by default; `--offline` skips them; `--ping` adds one tiny paid AI call to
verify the key end-to-end. No TUI imports — must run even when the TUI can't.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

from .config import Config, data_dir

OK, WARN, FAIL, OFF = "ok", "warn", "fail", "off"

MARK = {OK: "✓", WARN: "!", FAIL: "✗", OFF: "·"}


@dataclass
class Check:
    section: str
    name: str
    status: str
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    def add(self, section: str, name: str, status: str, detail: str = "") -> None:
        self.checks.append(Check(section, name, status, detail))

    @property
    def worst(self) -> str:
        order = {FAIL: 3, WARN: 2, OK: 1, OFF: 0}
        return max((c.status for c in self.checks), key=lambda s: order[s], default=OK)


def _check_profile(rep: Report, cfg: Config) -> None:
    sec = "PROFILE"
    p = cfg.path
    if not p.exists():
        rep.add(sec, "profile.toml", WARN, f"{p} — not written yet (defaults active)")
    else:
        try:
            with open(p, "rb") as fh:
                tomllib.load(fh)
            rep.add(sec, "profile.toml", OK, str(p))
        except Exception as exc:  # noqa: BLE001
            rep.add(sec, "profile.toml", FAIL, f"TOML syntax error: {exc}")
            return
        try:
            if p.stat().st_mode & 0o077:
                rep.add(sec, "permissions", WARN,
                        f"profile readable by group/others — it holds API keys; fix: chmod 600 {p}")
            else:
                rep.add(sec, "permissions", OK, "owner-only (0600)")
        except OSError:
            pass

    site = cfg.me_path()
    if site.exists():
        n = len(cfg.me_text(limit=100_000))
        rep.add(sec, "site.md", OK if n > 200 else WARN,
                f"{site.name} · {n} chars"
                + ("" if n > 200 else " — thin; Wintermute pitches blind"))
    else:
        rep.add(sec, "site.md", WARN, f"{site} missing — seeded on next launch")


def _check_ai(rep: Report, cfg: Config) -> None:
    sec = "WINTERMUTE"
    key = cfg.api_key()
    if key:
        rep.add(sec, "api key", OK, f"{cfg.provider()} · from {cfg.api_key_source()}")
    else:
        rep.add(sec, "api key", WARN,
                f"no {cfg.provider()} key — dossiers and search work, outreach "
                "drafting is dark. Paste one in CONNECTIONS.")
    rep.add(sec, "model", OK, cfg.model_for("consigliere"))


async def _ping_ai(rep: Report, cfg: Config) -> None:
    from .ai.client import Brain
    ok, msg = await Brain(cfg).ping()
    rep.add("WINTERMUTE", "live ping", OK if ok else FAIL, msg)


async def _check_ctgov(rep: Report, cfg: Config, offline: bool) -> None:
    sec = "CLINICALTRIALS.GOV"
    if offline:
        rep.add(sec, "api", OK, "probe skipped (--offline)")
        return
    import httpx
    from .sources.ctgov import API
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(API, params={"pageSize": 1, "query.cond":
                                         str(cfg.get("filters.condition", "") or "prematurity")})
        if r.status_code == 200 and "studies" in r.text:
            rep.add(sec, "api", OK, "v2 API reachable, query answered")
        else:
            rep.add(sec, "api", FAIL, f"HTTP {r.status_code} — API changed or blocked?")
    except Exception as exc:  # noqa: BLE001
        rep.add(sec, "api", WARN, f"unreachable: {type(exc).__name__} (network down?)")


def _check_filters(rep: Report, cfg: Config) -> None:
    sec = "FILTERS"
    cond = str(cfg.get("filters.condition", "") or "").strip()
    kw = str(cfg.get("filters.keyword", "") or "").strip()
    if cond or kw:
        rep.add(sec, "targeting", OK,
                f"condition: {cond or '—'} · keyword net: {'set' if kw else '—'}")
    else:
        rep.add(sec, "targeting", WARN,
                "no condition and no keyword — a search would trawl the whole ocean")
    statuses = cfg.get("filters.statuses", []) or []
    rep.add(sec, "statuses", OK if statuses else WARN,
            ", ".join(statuses) if statuses
            else "none selected — includes completed/withdrawn noise")
    try:
        mx = int(cfg.get("filters.max_results", 300))
        rep.add(sec, "max results", OK if 1 <= mx <= 1000 else WARN, str(mx))
    except (TypeError, ValueError):
        rep.add(sec, "max results", WARN, "not a number — will fall back to 300")


def _check_db(rep: Report, cfg: Config) -> None:
    from .db import Store
    sec = "DATABASE"
    try:
        store = Store()
    except Exception as exc:  # noqa: BLE001
        rep.add(sec, "open", FAIL, f"cannot open: {exc}")
        return
    try:
        counts = store.counts()
        total = sum(counts.values())
        stages = {k.value if hasattr(k, "value") else str(k): v
                  for k, v in counts.items() if v}
        rep.add(sec, "studies", OK if total else WARN,
                f"{total} rows · " + (", ".join(f"{k} {v}" for k, v in stages.items())
                                      if stages else "empty — run a search (`⟲` or `studyscout search`)"))
        sent, replied, _ = store.outreach_stats()
        rep.add(sec, "outreach", OK, f"{sent} sent · {replied} replied")
        quiet_days = int(cfg.get("followup.nudge_days", 7) or 7)
        quiet = store.quiet_sponsors(quiet_days)
        if quiet:
            rep.add(sec, "quiet sponsors", WARN,
                    f"{len(quiet)} sponsor(s) silent ≥{quiet_days}d — the briefing (`b`) has names")
        db_file = data_dir() / "studyscout.db"
        if db_file.exists():
            rep.add(sec, "file", OK, f"{db_file} · {db_file.stat().st_size // 1024} KB")
    except Exception as exc:  # noqa: BLE001
        rep.add(sec, "integrity", FAIL, str(exc))
    finally:
        store.close()


async def run_doctor(offline: bool = False, ping: bool = False) -> Report:
    rep = Report()
    cfg = Config()
    _check_profile(rep, cfg)
    _check_ai(rep, cfg)
    if ping and cfg.api_key():
        await _ping_ai(rep, cfg)
    await _check_ctgov(rep, cfg, offline)
    _check_filters(rep, cfg)
    _check_db(rep, cfg)
    return rep


def render(rep: Report, color: bool = True) -> str:
    C = {OK: "\033[32m", WARN: "\033[33m", FAIL: "\033[31m", OFF: "\033[2m"}
    R = "\033[0m"
    lines: list[str] = []
    section = None
    for c in rep.checks:
        if c.section != section:
            section = c.section
            lines.append("")
            lines.append(f"  {section}")
        mark = MARK[c.status]
        if color:
            mark = f"{C[c.status]}{mark}{R}"
        lines.append(f"    {mark} {c.name:<16s} {c.detail}".rstrip())
    verdict = {OK: "all clear — go hunt.", OFF: "all clear — go hunt.",
               WARN: "flying, but check the ! lines.",
               FAIL: "grounded items above — fix the ✗ lines first."}[rep.worst]
    lines.append("")
    lines.append(f"  DIAGNOSIS: {verdict}")
    return "\n".join(lines)

"""The living brain: one TOML file drives every filter + the site profile.

Edit by hand, in-app, or tell Wintermute — schema-validated, hot-reloadable.
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w
from platformdirs import user_config_dir, user_data_dir

APP = "studyscout"

# The site profile Wintermute reads to draft outreach ("run this at our site").
ME_TEMPLATE = """\
# OUR SITE — what Wintermute pitches (edit freely)

## Site
- Name: (your research site)
- Location: (city, state)
- Setting: (hospital? private practice? academic? site network?)

## Investigators
- PI(s): (names, credentials)
- Coordinators / research staff: (capacity)

## Strengths & population
- Therapeutic focus: (your specialty and the conditions you can enroll)
- Patient volume: (annual visits/admits, target population size)
- Capabilities: (labs, imaging, pharmacy, monitoring, prior device/drug trials)

## Track record
- Studies run / enrollment hit / sponsors worked with

## Outreach notes for Wintermute
- Tone: warm, credible, concise. Lead with why we're a strong site for THIS study.
- Ask: a brief call to explore adding our site.
"""

DEFAULTS: dict[str, Any] = {
    "identity": {
        "name": "Site BD — neonatal / pediatric",
        "me_file": "site.md",
    },
    # ClinicalTrials.gov filters — the heart of the hunt.
    "filters": {
        "condition": "",                 # query.cond, e.g. "heart failure"
        # query.term (Essie OR expression) — YOUR therapeutic net. Example for a
        # neonatal site: "neonatal OR preterm OR respiratory distress syndrome
        # OR hypoxic-ischemic encephalopathy". Ships empty: set your own.
        "keyword": "",
        "statuses": ["RECRUITING", "NOT_YET_RECRUITING"],
        "phases": [],                    # [] = all; e.g. ["2", "3"]
        "ages": [],                      # [] = all; any of: child | adult | older
        "study_type": "int",             # int | obs | "" (all)
        "country": "United States",      # "" = international / anywhere
        "states": [],                    # optional; [] = whole country
        "funder_types": [],              # e.g. ["industry", "nih"]
        "sponsor": "",                   # query.lead, optional
        "site_mode": "any",              # any | multi (>=2 sites) | single
        "exclude_keywords": [],          # drop hits whose text matches any of these
        "max_results": 300,
        "sort": "start",                 # start | enrollment | sites | status
    },
    "followup": {
        # Contacted/Waiting this many days with no reply → nudged in the briefing.
        "nudge_days": 7,
        # FUTURE-stage relationships parked this many days → "reach back out"
        # nudge in the briefing. The keep-warm clock.
        "future_nudge_days": 45,
    },
    # Site-startup handoff: the paperwork gauntlet after a study is won.
    # Press R on a study to work the list; edit these items to match your SOP.
    "regulatory": {
        "checklist": [
            "CDA / NDA signed",
            "Feasibility questionnaire returned",
            "Protocol + IB received",
            "FDA 1572 completed",
            "PI CV + medical license current",
            "GCP / human-subjects certs current",
            "IRB / EC submission",
            "Budget negotiated",
            "CTA executed",
            "Delegation-of-authority log started",
            "SIV scheduled",
        ],
    },
    "ai": {
        "enabled": True,
        "provider": "anthropic",         # anthropic | openrouter | openai
        "api_key": "",
        "openrouter_key": "",
        "openai_key": "",
        "consigliere_model": "claude-opus-4-8",
        "consigliere_model_openrouter": "anthropic/claude-opus-4.8",
        "consigliere_model_openai": "gpt-4o",
        "max_tokens": 2048,
    },
    "sources": {
        "ctgov": {"enabled": True},
    },
    "ui": {
        "splash": True,
        "show_menu": True,
        "wintermute_pane": True,
        "mail_command": "",              # blank = xdg-open; or "evolution"; placeholders {url} {to} {subject} {body}
        "mail_mode": "mailto",           # mailto | outlook (Outlook Web deeplink compose — for O365/Prospect Mail shops)
        "accent": "amber",
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def config_path() -> Path:
    env = os.environ.get("STUDYSCOUT_PROFILE")
    if env:
        return Path(env).expanduser()
    local = Path.cwd() / "profile.toml"
    return local if local.exists() else Path(user_config_dir(APP)) / "profile.toml"


def data_dir() -> Path:
    d = Path(os.environ.get("STUDYSCOUT_DATA", user_data_dir(APP)))
    d.mkdir(parents=True, exist_ok=True)
    return d


_KEY_MAP = {
    "anthropic": ("ai.api_key", "ANTHROPIC_API_KEY"),
    "openrouter": ("ai.openrouter_key", "OPENROUTER_API_KEY"),
    "openai": ("ai.openai_key", "OPENAI_API_KEY"),
}
_SUFFIX = {"openrouter": "_openrouter", "openai": "_openai"}


class Config:
    def __init__(self, path: Path | None = None):
        self.path = path or config_path()
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> "Config":
        if self.path.exists():
            with open(self.path, "rb") as fh:
                self.data = _deep_merge(DEFAULTS, tomllib.load(fh))
        else:
            self.data = copy.deepcopy(DEFAULTS)
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "wb") as fh:
            tomli_w.dump(self.data, fh)

    def ensure_file(self) -> Path:
        if not self.path.exists():
            self.save()
        return self.path

    def get(self, dotted: str, default=None):
        cur: Any = self.data
        for part in dotted.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return default
        return cur

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        cur = self.data
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value

    # ---- AI ---- #
    def provider(self) -> str:
        return (self.get("ai.provider", "anthropic") or "anthropic").lower()

    def api_key(self) -> str:
        cfg_key, env_var = _KEY_MAP.get(self.provider(), _KEY_MAP["anthropic"])
        return (self.get(cfg_key, "") or os.environ.get(env_var, "") or "").strip()

    def api_key_source(self) -> str:
        cfg_key, env_var = _KEY_MAP.get(self.provider(), _KEY_MAP["anthropic"])
        return "config" if self.get(cfg_key) else ("env" if os.environ.get(env_var) else "none")

    def model_for(self, role: str = "consigliere") -> str:
        suffix = _SUFFIX.get(self.provider(), "")
        return self.get(f"ai.{role}_model{suffix}") or self.get(f"ai.{role}_model") or ""

    # ---- me / site ---- #
    def me_path(self) -> Path:
        rel = self.get("identity.me_file", "site.md")
        p = Path(rel)
        return p if p.is_absolute() else self.path.parent / p

    def me_text(self, limit: int = 6000) -> str:
        p = self.me_path()
        return p.read_text(errors="ignore")[:limit] if p.exists() else ""

    def ensure_me(self) -> Path:
        p = self.me_path()
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(ME_TEMPLATE)
        return p

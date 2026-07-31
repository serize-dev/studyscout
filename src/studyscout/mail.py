"""Open a drafted outreach message in the desktop mail client (Evolution on
Pop!_OS) via a prefilled mailto: URL.
"""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import quote


def split_draft(draft: str, fallback_subject: str = "") -> tuple[str, str]:
    """Split a Wintermute draft into (subject, body).

    Honors a leading 'Subject: ...' line; otherwise uses the fallback.
    """
    lines = (draft or "").strip().splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).lstrip("\n")
        return subject, body
    return fallback_subject, draft.strip()


def build_mailto(to: str | None, subject: str, body: str) -> str:
    addr = (to or "").strip()
    params = []
    if subject:
        params.append("subject=" + quote(subject))
    if body:
        params.append("body=" + quote(body))
    url = "mailto:" + addr
    if params:
        url += "?" + "&".join(params)
    return url


def open_mail(to: str | None, subject: str, body: str, command: str = "") -> tuple[bool, str]:
    """Launch the mail client with a composed message.

    Returns (ok, message). `command` overrides the launcher (e.g. "evolution");
    blank tries evolution, then xdg-open.
    """
    url = build_mailto(to, subject, body)
    candidates = []
    if command:
        candidates.append(command.split())
    candidates += [["evolution"], ["xdg-open"], ["xdg-email"]]
    for argv in candidates:
        if not shutil.which(argv[0]):
            continue
        try:
            subprocess.Popen(argv + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, f"opened in {argv[0]}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{argv[0]} failed: {exc}"
    return False, "no mail client found (install evolution or set ui.mail_command)"

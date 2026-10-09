"""Open a drafted outreach message in the desktop mail client (Evolution on
Pop!_OS) via a prefilled mailto: URL.
"""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import quote

from .childenv import child_env


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


def build_outlook_url(to: str | None, subject: str, body: str) -> str:
    """Outlook Web 'deeplink compose' — lands a prefilled draft in the user's
    O365 account. The route for Outlook-only shops (incl. Prospect Mail users:
    the Electron wrapper takes no mailto/compose args, but the browser deeplink
    opens the same account).
    """
    params = ["to=" + quote((to or "").strip())]
    if subject:
        params.append("subject=" + quote(subject))
    if body:
        params.append("body=" + quote(body))
    return "https://outlook.office.com/mail/deeplink/compose?" + "&".join(params)


def open_mail(to: str | None, subject: str, body: str, command: str = "",
              mode: str = "mailto") -> tuple[bool, str]:
    """Launch the mail client with a composed message.

    Returns (ok, message). `mode` picks the URL: "mailto" (default) or
    "outlook" (Outlook Web deeplink compose — opens in the browser).
    `command` overrides the launcher (e.g. "evolution"); it may use the
    placeholders {url} {to} {subject} {body}, otherwise the URL is appended.
    Blank command tries evolution (mailto only), then xdg-open.
    """
    if mode == "outlook":
        url = build_outlook_url(to, subject, body)
    else:
        url = build_mailto(to, subject, body)
    candidates = []
    if command:
        argv = command.split()
        if any("{" in a for a in argv):
            sub = {"{url}": url, "{to}": (to or ""), "{subject}": subject, "{body}": body}
            for pat, val in sub.items():
                argv = [a.replace(pat, val) for a in argv]
            candidates.append((argv, False))
        else:
            candidates.append((argv, True))
    if mode == "outlook":
        candidates += [(["xdg-open"], True)]
    else:
        candidates += [(["evolution"], True), (["xdg-open"], True), (["xdg-email"], True)]
    for argv, append_url in candidates:
        if not shutil.which(argv[0]):
            continue
        try:
            final = argv + [url] if append_url else argv
            subprocess.Popen(final, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             env=child_env())
            where = argv[0] + (" (Outlook Web compose)" if mode == "outlook" else "")
            return True, f"opened in {where}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{argv[0]} failed: {exc}"
    return False, "no mail client found (install evolution or set ui.mail_command)"

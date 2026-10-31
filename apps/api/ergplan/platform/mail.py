"""Sending the sign-in link. SMTP when ERGPLAN_SMTP_URL is set (smtp[s]://user:password@host:port);
otherwise the link is written to the log (development)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from ..core.settings import get_settings

log = logging.getLogger("ergplan.mail")


def send(to: str, subject: str, body: str) -> bool:
    st = get_settings()
    if not st.ergplan_smtp_url:
        log.warning("no SMTP configured; message to %s: %s", to, subject)
        return False
    u = urlparse(st.ergplan_smtp_url)
    msg = EmailMessage()
    msg["From"] = st.ergplan_mail_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    port = u.port or (465 if u.scheme == "smtps" else 587)
    smtp: smtplib.SMTP = (
        smtplib.SMTP_SSL(u.hostname or "", port, timeout=20)
        if u.scheme == "smtps"
        else smtplib.SMTP(u.hostname or "", port, timeout=20)
    )
    with smtp:
        if u.scheme != "smtps":
            smtp.starttls()
        if u.username:
            smtp.login(unquote(u.username), unquote(u.password or ""))
        smtp.send_message(msg)
    return True

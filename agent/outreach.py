"""Outreach: email via SMTP. SEND_MODE controls where it actually goes:

  dry      -> print only (default)
  sandbox  -> real SMTP to a sandbox inbox (e.g. Mailtrap) that captures everything
  live     -> real delivery, but ONLY to emails Hunter scored >= MIN_LIVE_CONFIDENCE
"""
import smtplib
import time
from email.message import EmailMessage

from .config import get, get_int


class SendBlocked(Exception):
    pass


def subject(company: str, city: str) -> str:
    return f"Idea for events at {company} in {city}"


def _sign_off() -> str:
    return f"{get('FROM_NAME', 'GoPratle Partnerships')}, GoPratle"


def initial_email(first: str, pitch: str):
    body = f"Hi {first or 'there'},\n\n{pitch}\n\n{_sign_off()}\n\n(Not relevant? Reply \"stop\" and I won't follow up.)"
    return body


def followup_email(first: str, city: str):
    return (f"Hi {first or 'there'},\n\nBumping my note below in case it got buried. Happy to send a shortlist of "
            f"vetted planners, DJs and crew for your next {city} event, no call needed.\n\n"
            f"{_sign_off()}\n\n(Reply \"stop\" and I won't write again.)")


def deliver(to: str, subj: str, body: str, verified: bool) -> str:
    mode = get("SEND_MODE", "dry").lower()
    if mode == "dry":
        print(f"\n--- [dry-run] to={to}\nSubject: {subj}\n\n{body}\n---")
        return "dry"
    if mode == "live" and not verified:
        raise SendBlocked(f"live mode: {to} is not a verified address, held for manual review")
    msg = EmailMessage()
    msg["From"] = f"{get('FROM_NAME', 'GoPratle Partnerships')} <{get('FROM_EMAIL', 'partnerships@gopratle.test')}>"
    msg["To"] = to
    msg["Subject"] = subj
    msg.set_content(body)
    with smtplib.SMTP(get("SMTP_HOST", "sandbox.smtp.mailtrap.io"), get_int("SMTP_PORT", 2525), timeout=30) as s:
        s.starttls()
        s.login(get("SMTP_USER"), get("SMTP_PASS"))
        s.send_message(msg)
    time.sleep(get_int("SEND_DELAY_SECONDS", 20))  # stay under sandbox rate limits
    return mode

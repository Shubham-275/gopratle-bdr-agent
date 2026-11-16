"""Orchestration. Status flow (all state lives in the Sheet):

  (blank) -> Processing -> Outreach Sent -> Follow-up Sent
                        \\-> No Lead Found | Needs Review | Error
  Reply Status set by a human (replied / stop / ...) -> Closed (no follow-up)
"""
import threading
import traceback
from datetime import datetime, timedelta, timezone

from . import discover, enrich, outreach, pitch
from .config import get, get_int

LOCK = threading.Lock()  # sheet poller and Telegram listener share one sheet


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse(ts: str):
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _notify(text: str, chat_id: str = ""):
    print(text)
    if get("TELEGRAM_BOT_TOKEN") and chat_id:
        try:
            from . import telegram_bot

            telegram_bot.send_message(chat_id, text)
        except Exception:
            traceback.print_exc()


def process_row(sheet, row_id: int, row: dict):
    company, city = row["Company"].strip(), row["City"].strip()
    chat = row.get("Requested By") or get("TEST_TELEGRAM_CHAT_ID")
    sheet.update(row_id, {"Status": "Processing", "Source": row.get("Source") or "sheet"})
    try:
        cands = discover.find_leads(company, city)
        if not cands:
            sheet.update(row_id, {"Status": "No Lead Found",
                                  "Notes": "No Founder/HR/Events profile found in public search results"})
            _notify(f"No lead found for {company} ({city}).", chat)
            return
        lead, others = cands[0], cands[1:3]
        contact = enrich.find_email(lead["name"], company)
        pitch_text = pitch.write_pitch(company, city, lead)
        sheet.update(row_id, {
            "Lead Name": lead["name"], "Role": lead["title"], "Lead Type": lead["lead_type"],
            "Profile URL": lead["profile_url"], "Email": contact["email"],
            "Email Confidence": contact["label"], "Pitch": pitch_text,
            "Other Leads": "\n".join(f"{c['name']} | {c['title']} | {c['profile_url']}" for c in others),
        })

        first = enrich.split_name(lead["name"])[0]
        try:
            mode = outreach.deliver(contact["email"], outreach.subject(company, city),
                                    outreach.initial_email(first, pitch_text), contact["verified"])
        except outreach.SendBlocked as e:
            sheet.update(row_id, {"Status": "Needs Review", "Notes": str(e)})
            _notify(f"Held for review: {company} ({city}). {e}", chat)
            return

        sent = _now()
        due = sent + timedelta(minutes=get_int("FOLLOWUP_DELAY_MINUTES", 4320))
        sheet.update(row_id, {"Status": "Outreach Sent", "Outreach Sent At": sent.isoformat(),
                              "Follow-up Due": due.isoformat(), "Notes": f"send_mode={mode}"})
        _notify(
            f"{company} · {city}\nLead: {lead['name']}, {lead['title']} ({lead['lead_type']})\n"
            f"Profile: {lead['profile_url']}\nEmail: {contact['email']} [{contact['label']}]\n\n"
            f"Pitch:\n{pitch_text}\n\nOutreach: {mode}. Follow-up due {due.isoformat()}", chat)
    except Exception as e:
        traceback.print_exc()
        sheet.update(row_id, {"Status": "Error", "Notes": f"{type(e).__name__}: {e}"[:300]})
        _notify(f"Error on {company} ({city}): {e}", chat)


def run_followups(sheet):
    for row_id, row in sheet.rows():
        if row["Status"] != "Outreach Sent":
            continue
        reply = row["Reply Status"].strip()
        if reply:
            sheet.update(row_id, {"Status": f"Closed ({reply})"})
            continue
        if not row["Follow-up Due"] or _now() < _parse(row["Follow-up Due"]):
            continue
        try:
            first = enrich.split_name(row["Lead Name"])[0]
            mode = outreach.deliver(row["Email"], "Re: " + outreach.subject(row["Company"], row["City"]),
                                    outreach.followup_email(first, row["City"]),
                                    row["Email Confidence"].startswith("hunter"))
            sheet.update(row_id, {"Status": "Follow-up Sent", "Follow-up Sent At": _now().isoformat(),
                                  "Notes": f"{row['Notes']}; followup_mode={mode}"})
            _notify(f"Follow-up sent to {row['Lead Name']} at {row['Company']} ({mode}).",
                    row.get("Requested By") or get("TEST_TELEGRAM_CHAT_ID"))
        except Exception as e:
            traceback.print_exc()
            sheet.update(row_id, {"Notes": f"followup failed: {e}"[:300]})


def tick(sheet):
    """One pass: pick up new rows, then send any due follow-ups."""
    with LOCK:
        for row_id, row in sheet.rows():
            if row["Company"].strip() and row["City"].strip() and not row["Status"].strip():
                process_row(sheet, row_id, row)
        run_followups(sheet)


def handle_request(sheet, company: str, city: str, chat_id: str):
    """Telegram entry point: log the request as a row and process it immediately."""
    with LOCK:
        row = {"Company": company, "City": city, "Source": "telegram", "Requested By": str(chat_id)}
        row_id = sheet.append(row)
        process_row(sheet, row_id, row)

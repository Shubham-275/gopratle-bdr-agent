"""Telegram trigger via plain long-polling (no extra dependency).

Say:  "Find event leads for Zomato in Gurgaon"   (or  /find Zomato in Gurgaon)
Only chat IDs in TELEGRAM_ALLOWED_CHAT_IDS may trigger runs; anyone else is told their chat ID
so you can add it. (WhatsApp: same handler, swap the transport for Twilio's WhatsApp sandbox webhook.)
"""
import re
import time

import requests

from . import pipeline
from .config import get

PATTERNS = [
    re.compile(r"^find\s+(?:event\s+)?leads?\s+for\s+(?P<company>.+?)\s+in\s+(?P<city>.+?)\s*$", re.I),
    re.compile(r"^/find\s+(?P<company>.+?)\s+in\s+(?P<city>.+?)\s*$", re.I),
]
HELP = 'Send: "Find event leads for <Company> in <City>"'


def _call(method: str, **params):
    r = requests.post(f"https://api.telegram.org/bot{get('TELEGRAM_BOT_TOKEN')}/{method}", json=params, timeout=45)
    return r.json()


def send_message(chat_id, text: str):
    _call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True)


def parse_command(text: str):
    for p in PATTERNS:
        m = p.match(text.strip())
        if m:
            return m.group("company").strip(), m.group("city").strip()
    return None


def handle(sheet, chat_id: str, text: str):
    parsed = parse_command(text)
    if not parsed:
        send_message(chat_id, HELP)
        return
    company, city = parsed
    send_message(chat_id, f"On it: finding leads for {company} in {city}...")
    pipeline.handle_request(sheet, company, city, chat_id)


def listen(sheet):
    offset = None
    allowed = {x.strip() for x in get("TELEGRAM_ALLOWED_CHAT_IDS").split(",") if x.strip()}
    print("Telegram listener started.")
    while True:
        try:
            data = _call("getUpdates", timeout=30, offset=offset)
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text, chat_id = (msg.get("text") or "").strip(), str((msg.get("chat") or {}).get("id", ""))
                if not text or not chat_id:
                    continue
                if chat_id not in allowed:
                    send_message(chat_id, f"Not authorised. Your chat id is {chat_id}; add it to TELEGRAM_ALLOWED_CHAT_IDS.")
                    continue
                handle(sheet, chat_id, text)
        except Exception as e:
            print(f"telegram loop error: {e}")
            time.sleep(5)

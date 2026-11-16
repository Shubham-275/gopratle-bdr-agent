"""Contact enrichment. Hunter.io email-finder when a key is set; otherwise a pattern guess
that is clearly flagged as unverified (and which live mode refuses to send to)."""
import re

import requests

from .config import get, get_int

TITLES = {"dr", "mr", "ms", "mrs", "prof", "phd", "mba", "ca", "cfa"}


def split_name(full: str):
    parts = [p for p in re.sub(r"[^A-Za-z\s.'-]", " ", full).split() if p.lower().strip(".") not in TITLES]
    if not parts:
        return "", ""
    return parts[0], (parts[-1] if len(parts) > 1 else "")


def guess_domain(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower()) + ".com"


def find_email(full_name: str, company: str) -> dict:
    first, last = split_name(full_name)
    key = get("HUNTER_API_KEY")
    if key and first and last:
        try:
            r = requests.get(
                "https://api.hunter.io/v2/email-finder",
                params={"company": company, "first_name": first, "last_name": last, "api_key": key},
                timeout=30,
            )
            if r.status_code == 200:
                d = r.json().get("data") or {}
                if d.get("email"):
                    score = int(d.get("score") or 0)
                    return {"email": d["email"], "label": f"hunter score {score}",
                            "verified": score >= get_int("MIN_LIVE_CONFIDENCE", 80)}
        except requests.RequestException:
            pass
    local = f"{first}.{last}".strip(".").lower() or "info"
    return {"email": f"{local}@{guess_domain(company)}", "label": "guessed pattern (unverified)", "verified": False}

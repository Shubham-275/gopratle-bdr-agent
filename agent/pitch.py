"""Tailored 3-line pitch for GoPratle. LLM first; validated; template fallback by lead type."""
from . import llm

SYSTEM = """You write cold-outreach pitches for GoPratle, a marketplace that connects event hosts
with vetted event planners, DJs, and crew.
Write EXACTLY 3 lines separated by newlines. No greeting, no sign-off, no bullets, no emojis, <=25 words per line.
Line 1: a specific, credible hook about the recipient's role/company/city. Use ONLY the facts provided.
        Never invent news, numbers, events, or relationships.
Line 2: what GoPratle does for someone in THEIR role.
Line 3: a low-friction ask (e.g. a 15-minute call, or a shortlist of vetted vendors)."""

FALLBACK = {
    "Events": [
        "Running events at {company} in {city} means chasing planners, DJs and crew on tight timelines.",
        "GoPratle connects event hosts with vetted planners, DJs and crew, so you shortlist in hours, not weeks.",
        "Open to a 15-minute call, or should I send a vetted {city} shortlist first?",
    ],
    "HR": [
        "Team offsites and culture events at {company} in {city} usually mean juggling many unvetted vendors.",
        "GoPratle gives HR teams vetted planners, DJs and crew in one place, with clear quotes and reliable delivery.",
        "Worth a 15-minute chat, or would a sample shortlist for {city} be more useful?",
    ],
    "Founder": [
        "As {company} grows in {city}, launches and team events can quietly eat founder time.",
        "GoPratle connects hosts with vetted planners, DJs and crew, so events run without you managing vendors.",
        "Open to a 15-minute call to see if it fits {company}?",
    ],
}


def write_pitch(company: str, city: str, lead: dict) -> str:
    facts = (f"Recipient: {lead['name']}, {lead['title']} ({lead['lead_type']}) at {company}, {city}.\n"
             f"Evidence: {lead.get('evidence', '')}")
    text = llm.complete(SYSTEM, facts, max_tokens=300)
    if text:
        lines = [ln.strip(" -•*\t") for ln in text.splitlines() if ln.strip()]
        if len(lines) == 3:
            return "\n".join(lines)
    return "\n".join(s.format(company=company, city=city) for s in FALLBACK[lead["lead_type"]])

"""Find the right person at a company: Events lead > HR lead > Founder (configurable).

Only public search results are used (title/snippet of LinkedIn profile hits). We never
scrape LinkedIn pages directly. Candidates must come from a returned URL, so the LLM
cannot invent people.
"""
import json
import re
import traceback

from ddgs import DDGS
import requests

from . import llm
from .config import get

EVENTS_RE = re.compile(r"event|experiential|activation|engagement|culture|workplace|offsite", re.I)
HR_RE = re.compile(r"\bhr\b|human resources|people (&|and)? ?(culture|ops|operations)|chro|employee experience", re.I)
FOUNDER_RE = re.compile(r"founder|\bceo\b|chief executive|owner|managing director", re.I)

LI_TITLE = re.compile(r"^(?P<name>[^|\-–—]{3,60}?)\s[-–—]\s(?P<rest>.+?)\s*\|\s*LinkedIn", re.I)


def classify(title: str):
    if EVENTS_RE.search(title):
        return "Events"
    if HR_RE.search(title):
        return "HR"
    if FOUNDER_RE.search(title):
        return "Founder"
    return None


def queries(company: str, city: str):
    return [
        f"site:linkedin.com/in {company} {city} head of events",
        f"site:linkedin.com/in {company} {city} HR business partner people culture",
        f"site:linkedin.com/in {company} founder CEO",
    ]


def web_search(query: str, n: int = 8):
    provider = get("SEARCH_PROVIDER", "ddgs").lower()
    if provider == "tavily":
        r = requests.post(
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {get('TAVILY_API_KEY')}"},
            json={"query": query, "max_results": n},
            timeout=30,
        )
        r.raise_for_status()
        return [{"title": x["title"], "url": x["url"], "content": x.get("content", "")} for x in r.json().get("results", [])]
    from ddgs import DDGS  # lazy import; keyless fallback

    try:
        hits = DDGS().text(query, max_results=n)
    except Exception:
        return []
    return [{"title": x["title"], "url": x["href"], "content": x.get("body", "")} for x in hits]

def _mock_results(company: str, city: str):
    """Fictional people so the demo runs offline. Clearly fake; never emailed anywhere real."""
    return [
        {"title": f"Riya Malhotra - Head of Events & Experiences - {company} | LinkedIn",
         "url": "https://www.linkedin.com/in/riya-malhotra-demo",
         "content": f"{city}. Leads corporate events and employee engagement at {company}."},
        {"title": f"Karan Mehta - Senior HR Business Partner - {company} | LinkedIn",
         "url": "https://www.linkedin.com/in/karan-mehta-demo",
         "content": f"{city}. HR partner for the {company} regional teams."},
        {"title": f"Anita Rao - Co-Founder & CEO - {company} | LinkedIn",
         "url": "https://www.linkedin.com/in/anita-rao-demo",
         "content": f"Co-founder of {company}."},
    ]


def _first_profile(title: str) -> str:
    """ddgs often glues several profiles into one title. Keep only the first one
    (cut at the first '...' or '| LinkedIn')."""
    return re.split(r"\s*(?:\.\.\.|…|\|\s*LinkedIn)", title.strip(), maxsplit=1)[0]


def _heuristic(results, company):
    out = []
    for r in results:
        if "linkedin.com/in/" not in r["url"]:
            continue
        m = re.match(r"^(?P<name>[^-–—|]{3,60}?)\s[-–—]\s(?P<rest>.+)$", _first_profile(r["title"]))
        if not m:
            continue
        rest = m.group("rest")
        if company.lower() not in f"{rest} {r.get('content', '')}".lower():
            continue
        # skip former employees: "Ex Zomato", "Ex-CEO, Zomato", "Former ... Zomato"
        if re.search(rf"\b(ex|former)\b[-\s]*(?:\w+[-\s,]+)?{re.escape(company)}", rest, re.I):
            continue
        lead_type = classify(rest)
        if lead_type:
            out.append({"name": m.group("name").strip(), "title": rest, "profile_url": r["url"],
                        "lead_type": lead_type, "evidence": r.get("content", "")[:200]})
    return out


EXTRACT_SYSTEM = """You extract B2B lead candidates from web search results.
Return ONLY a JSON array (no prose, no code fences). Each item:
{"name": str, "title": str, "profile_url": str, "lead_type": "Founder"|"HR"|"Events", "evidence": str}
Rules: include only people who appear to CURRENTLY work at the target company (prefer the target city).
Use only names/URLs present in the results; never invent anything. evidence = <=150 chars from the
result that supports the role. Events = events/experiential/employee engagement/culture owners.
If nobody qualifies, return []."""


def _llm_extract(company, city, results):
    blob = "\n\n".join(f"[{i}] {r['title']}\n{r['url']}\n{r['content'][:300]}" for i, r in enumerate(results))
    text = llm.complete(EXTRACT_SYSTEM, f"Target company: {company}\nTarget city: {city}\n\nResults:\n{blob}")
    if not text:
        return None
    try:
        arr = json.loads(re.search(r"\[.*\]", text, re.S).group(0))
        return [c for c in arr if isinstance(c, dict) and c.get("name") and c.get("profile_url")
                and c.get("lead_type") in ("Founder", "HR", "Events")]
    except Exception:
        traceback.print_exc()
        return None


def _rank(c, city):
    prio = [p.strip().lower() for p in get("LEAD_PRIORITY", "events,hr,founder").split(",")]
    t = c["lead_type"].lower()
    p = prio.index(t) if t in prio else len(prio)
    city_hit = 0 if city.lower() in f"{c.get('evidence', '')} {c.get('title', '')}".lower() else 1
    return (p, city_hit)


def find_leads(company: str, city: str):
    """Return candidates best-first. The caller uses [0] as the primary lead."""
    if get("SEARCH_PROVIDER", "ddgs").lower() == "mock":
        results = _mock_results(company, city)
    else:
        results, seen = [], set()
        for q in queries(company, city):
            try:
                for r in web_search(q):
                    if r["url"] not in seen:
                        seen.add(r["url"])
                        results.append(r)
            except Exception:
                traceback.print_exc()
    if not results:
        return []

    urls = {r["url"] for r in results}
    cands = _llm_extract(company, city, results) or _heuristic(results, company)
    cands = [c for c in cands if c["profile_url"] in urls]  # anti-hallucination guard

    dedup, seen_urls = [], set()
    for c in sorted(cands, key=lambda c: _rank(c, city)):
        if c["profile_url"] not in seen_urls:
            seen_urls.add(c["profile_url"])
            dedup.append(c)
    return dedup

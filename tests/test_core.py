import os

import pytest

from agent import discover, enrich, pitch, pipeline
from agent.sheet import CsvSheet
from agent.telegram_bot import parse_command


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    for k, v in {"SEARCH_PROVIDER": "mock", "SEND_MODE": "dry", "ANTHROPIC_API_KEY": "",
                 "HUNTER_API_KEY": "", "TELEGRAM_BOT_TOKEN": "", "FOLLOWUP_DELAY_MINUTES": "0"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(tmp_path)


def test_classify():
    assert discover.classify("Head of Events & Experiences") == "Events"
    assert discover.classify("Senior HR Business Partner") == "HR"
    assert discover.classify("Co-Founder & CEO") == "Founder"
    assert discover.classify("Software Engineer") is None


def test_priority_events_first():
    leads = discover.find_leads("Zomato", "Gurgaon")
    assert [l["lead_type"] for l in leads] == ["Events", "HR", "Founder"]


def test_heuristic_requires_company_match():
    res = [{"title": "A B - Head of Events - Other Co | LinkedIn", "url": "https://linkedin.com/in/ab", "content": ""}]
    assert discover._heuristic(res, "Zomato") == []


def test_pitch_is_three_lines_for_every_type():
    for t in ("Events", "HR", "Founder"):
        p = pitch.write_pitch("Zomato", "Gurgaon", {"name": "X Y", "title": "t", "lead_type": t})
        assert len(p.splitlines()) == 3


def test_email_guess_flagged_unverified():
    e = enrich.find_email("Dr. Riya Malhotra", "Zomato")
    assert e["email"] == "riya.malhotra@zomato.com" and not e["verified"]


def test_telegram_parse():
    assert parse_command("Find event leads for Zomato in Gurgaon") == ("Zomato", "Gurgaon")
    assert parse_command("/find Acme Foods in New Delhi") == ("Acme Foods", "New Delhi")
    assert parse_command("hello") is None


def test_end_to_end_and_followup_and_reply_stops_it():
    s = CsvSheet("t.csv")
    s.append({"Company": "Zomato", "City": "Gurgaon"})
    s.append({"Company": "Acme", "City": "Mumbai"})
    pipeline.tick(s)  # delay=0: outreach goes out, then the follow-up is due within the same tick
    rows = {r["Company"]: r for _, r in s.rows()}
    assert rows["Zomato"]["Lead Type"] == "Events"
    assert len(rows["Zomato"]["Pitch"].splitlines()) == 3
    assert rows["Zomato"]["Status"] == "Follow-up Sent"
    # a human marks Acme as replied BEFORE its follow-up goes out
    s2 = CsvSheet("t2.csv")
    rid = s2.append({"Company": "Acme", "City": "Mumbai"})
    row = dict(s2.rows())[rid]
    pipeline.process_row(s2, rid, row)
    s2.update(rid, {"Reply Status": "replied"})
    pipeline.run_followups(s2)
    assert dict(s2.rows())[rid]["Status"] == "Closed (replied)"


def test_live_mode_blocks_unverified(monkeypatch):
    monkeypatch.setenv("SEND_MODE", "live")
    s = CsvSheet("t3.csv")
    rid = s.append({"Company": "Zomato", "City": "Gurgaon"})
    pipeline.process_row(s, rid, dict(s.rows())[rid])
    assert dict(s.rows())[rid]["Status"] == "Needs Review"

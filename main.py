"""GoPratle BDR agent CLI.

  python main.py demo            offline end-to-end demo (mock search, dry-run send, CSV sheet)
  python main.py add "Zomato" "Gurgaon"   add a row to the sheet
  python main.py run             one pass: process new rows + due follow-ups (good for cron)
  python main.py watch           long-running: poll sheet + listen for Telegram commands
"""
import os
import sys
import threading
import time
import traceback


def _sheet():
    from agent.sheet import get_sheet
    return get_sheet()


def cmd_demo():
    os.environ.update({"SEARCH_PROVIDER": "mock", "SEND_MODE": "dry", "SHEET_BACKEND": "csv",
                       "SHEET_CSV": "demo_leads.csv", "FOLLOWUP_DELAY_MINUTES": "4320",
                       "ANTHROPIC_API_KEY": "", "HUNTER_API_KEY": ""})
    if os.path.exists("demo_leads.csv"):
        os.remove("demo_leads.csv")
    from agent import pipeline
    sheet = _sheet()
    sheet.append({"Company": "Zomato", "City": "Gurgaon"})
    sheet.append({"Company": "Acme Foods", "City": "Mumbai"})
    print(">>> tick 1: pick up new rows, find leads, write pitch, send outreach")
    pipeline.tick(sheet)
    print("\n>>> (simulating 3 days passing: backdating 'Follow-up Due' on the sheet)")
    for row_id, r in sheet.rows():
        sheet.update(row_id, {"Follow-up Due": "2000-01-01T00:00:00+00:00"})
    print(">>> tick 2: follow-ups are due and get sent")
    pipeline.tick(sheet)
    print("\n>>> Final sheet state")
    for _, r in sheet.rows():
        print(f"- {r['Company']} / {r['City']}: {r['Status']} | {r['Lead Name']} ({r['Lead Type']}) | {r['Email']} [{r['Email Confidence']}]")


def cmd_add(company, city):
    row_id = _sheet().append({"Company": company, "City": city, "Source": "cli"})
    print(f"Added row {row_id}: {company} / {city}")


def cmd_run():
    from agent import pipeline
    pipeline.tick(_sheet())


def cmd_watch():
    from agent import pipeline, telegram_bot
    from agent.config import get, get_int
    sheet = _sheet()
    if get("TELEGRAM_BOT_TOKEN"):
        threading.Thread(target=telegram_bot.listen, args=(sheet,), daemon=True).start()
    print(f"Watching sheet every {get_int('POLL_SECONDS', 30)}s. Ctrl+C to stop.")
    while True:
        try:
            pipeline.tick(sheet)
        except Exception:
            traceback.print_exc()
        time.sleep(get_int("POLL_SECONDS", 30))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["demo"]:
        cmd_demo()
    elif a[:1] == ["add"] and len(a) == 3:
        cmd_add(a[1], a[2])
    elif a[:1] == ["run"]:
        cmd_run()
    elif a[:1] == ["watch"]:
        cmd_watch()
    else:
        print(__doc__)

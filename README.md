# GoPratle BDR Lead Enrichment & Outreach Agent

A small Python agent (about 600 lines, no framework). Add **Company + City** to a Google Sheet, or message a Telegram bot
**"Find event leads for Zomato in Gurgaon"**, and it will:

1. Find the best Events / HR / Founder lead at that company (public search, LinkedIn profile titles and snippets)
2. Pull their profile URL and contact email (Hunter.io, or a flagged guess)
3. Write a tailored 3-line GoPratle pitch (Claude, with a template fallback)
4. Log everything back to the Sheet
5. Send the outreach email, schedule a follow-up, and send it when due (unless someone marks the row as replied)

```
 Google Sheet row ──┐                      ┌─ search (Tavily / DDG) ─► Events > HR > Founder ranking
                    ├─► pipeline.process ──┼─ enrich (Hunter email-finder, else flagged guess)
 Telegram command ──┘                      ├─ pitch (Claude, validated to exactly 3 lines)
                                           └─ outreach (SMTP: dry | sandbox | live) ─► Sheet
 every POLL_SECONDS: tick() ─► new rows + due follow-ups (state lives in the Sheet)
```

## Try it in 10 seconds (no keys, no network)

```bash
pip install requests python-dotenv
python main.py demo      # mock search, dry-run sending, local CSV acting as the sheet
python -m pytest -q
```

The demo uses fictional people and prints each email instead of sending it.

## Real setup (all have free or sandbox tiers)

| Piece | What to do | Env vars |
|---|---|---|
| Google Sheet | Create a Sheet, create a Google Cloud service account, enable the Sheets API, download its JSON key, **share the Sheet with the service account's email**. Headers are created automatically; humans only fill `Company` and `City`. | `SHEET_BACKEND=google`, `GOOGLE_SHEET_ID`, `GOOGLE_CREDS_FILE`, `WORKSHEET` |
| Search | [Tavily](https://tavily.com) API key (or `SEARCH_PROVIDER=ddgs` for keyless, less reliable) | `SEARCH_PROVIDER`, `TAVILY_API_KEY` |
| Emails | [Hunter.io](https://hunter.io) key. Without it, emails are guessed as `first.last@company.com` and flagged unverified. | `HUNTER_API_KEY` |
| LLM | Anthropic key. Without it, extraction uses a regex heuristic and pitches use templates. | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| Outreach | [Mailtrap](https://mailtrap.io) Email Sandbox SMTP credentials. Every email lands in your Mailtrap inbox and none reach a real person. | `SEND_MODE=sandbox`, `SMTP_*` |
| Telegram | Create a bot with @BotFather, message it once, then add your chat id to the allowlist (the bot replies with your chat id if you are not listed). | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`, `TEST_TELEGRAM_CHAT_ID` |

```bash
cp .env.example .env     # fill in the keys
pip install -r requirements.txt
python main.py add "Zomato" "Gurgaon"   # or type it into the Sheet
python main.py watch                    # polls the Sheet and listens to Telegram
```

To see a follow-up quickly, set `FOLLOWUP_DELAY_MINUTES=2`.
Deployment options: run `python main.py watch` as a worker (Railway, Render, a VM), or run `python main.py run` from cron every 15 minutes. Both work because all state is in the Sheet.

## Sheet columns

`Company`, `City` (input) → `Status`, `Lead Name`, `Role`, `Lead Type`, `Profile URL`, `Email`, `Email Confidence`, `Pitch`,
`Other Leads` (next 2 candidates), `Outreach Sent At`, `Follow-up Due`, `Follow-up Sent At`, `Reply Status`, `Source`, `Requested By`, `Notes`.

Statuses: `Processing`, `Outreach Sent`, `Follow-up Sent`, `No Lead Found`, `Needs Review`, `Error`, `Closed (...)`.
To stop a follow-up, type anything (e.g. `replied` or `stop`) in **Reply Status**. To retry a row, clear its Status.

## Guardrails (deliberate)

- **`SEND_MODE`** defaults to `dry`. `live` only sends to Hunter-verified addresses (score ≥ `MIN_LIVE_CONFIDENCE`); everything else becomes `Needs Review`.
- **No LinkedIn scraping.** Only public search-result titles and snippets are used. Candidates must come from a returned URL, so the LLM can't invent people.
- Sheet writes use `RAW` mode, so scraped text can never run as a formula.
- Telegram runs only for allowlisted chat ids. Every email carries an opt-out line, and follow-ups stop on any Reply Status.
- For real cold outreach in India, check DPDP Act and your email provider's policies before switching to `live`.

## Extending

- **WhatsApp trigger:** reuse `pipeline.handle_request`; swap the transport for a Twilio WhatsApp sandbox webhook.
- **More channels or CRM:** add a sender next to `outreach.deliver`, or push rows to HubSpot or Pipedrive from `process_row`.
- **Reply detection:** poll the inbox (IMAP) and set `Reply Status` automatically.

## Layout

```
main.py                 CLI: demo | add | run | watch
agent/sheet.py          CSV + Google Sheets backends
agent/discover.py       search, extraction, ranking
agent/enrich.py         Hunter / guess
agent/pitch.py          3-line pitch
agent/outreach.py       SMTP delivery + safety guard
agent/pipeline.py       process_row, follow-ups, tick
agent/telegram_bot.py   Telegram trigger
tests/test_core.py
```

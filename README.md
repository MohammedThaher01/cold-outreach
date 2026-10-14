# cold-outreach

A small CLI pipeline that researches a company, drafts a personalised cold email grounded in that research, and sends it after you approve the draft. Built to run on a laptop with a Groq API key and a Gmail app password.

No scraper farm, no database, no dashboard. One CSV file is the whole state.

## How it works

`python main.py run` walks each lead through four phases:

1. **Research** - `research.py` runs a web search (`ddgs`), scrapes the most relevant page with `trafilatura`, and asks a Groq-hosted model for a structured *insight card*: one verifiable observation, a hypothesis about the problem behind it, and the best-matching project to reference. If the evidence is too thin to personalise, the card comes back with `skip=true` and the lead is parked for manual review instead of getting a generic email.
2. **Generate** - `generate.py` turns an insight card into a subject line and a body, then validates the result (word count, no leftover placeholders) before accepting it.
3. **Review** - accepted drafts land in `leads.csv` with status `draft_review`. `python main.py list` prints them; `approve` and `reject` move them forward.
4. **Send** - `send.py` delivers approved drafts over Gmail SMTP, BCC'ing you on every one, with a randomised 45-60s gap between sends and a hard daily cap.

## Layout

| File | Role |
| --- | --- |
| `main.py` | CLI and orchestration - the four phases above |
| `store.py` | CSV-backed lead store (`load` / `save` / `update`) |
| `prompts.py` | The two system prompts: research analyst and email writer |
| `research.py` | Search, scrape, and insight-card generation |
| `generate.py` | Email drafting plus the output validator |
| `send.py` | Gmail SMTP delivery |

`leads.csv` is the database. Each row carries its own pipeline state, so you can stop and resume at any point.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp leads.example.csv leads.csv
```

Then fill in `.env`:

| Variable | What it is |
| --- | --- |
| `GROQ_API_KEY` | From [console.groq.com](https://console.groq.com) |
| `GMAIL_USER` | The Gmail address you send from |
| `GMAIL_APP_PASSWORD` | A 16-character [Gmail app password](https://myaccount.google.com/apppasswords) - not your account password |
| `AUTO_SEND` | `1` to approve drafts automatically, `0` to review every one by hand |
| `DAILY_CAP` | Maximum emails per day |
| `SELF_EMAIL` | Where `digest` sends the daily summary |

## Usage

```bash
python main.py add jane@example.com --company "Example Labs"   # add a lead
python main.py run                                            # research -> draft -> send
python main.py list                                           # review drafts
python main.py approve jane@example.com
python main.py reject jane@example.com
python main.py digest                                         # daily summary to SELF_EMAIL
```

## Lead statuses

Happy path:

```
NEW -> ready_for_email -> draft_review -> approved -> sent
```

Off-ramps:

| Status | Meaning |
| --- | --- |
| `need_company` | Free-mail domain and no company name to search for |
| `needs_manual_research` | Research came back too thin to personalise honestly |
| `skipped` | The writer judged the card too vague to attach a real project |
| `rejected` | You turned the draft down |

## Notes

- `AUTO_SEND=1` skips human review. Leave it at `0` until you trust the drafts.
- The research prompt is written around one specific person's project portfolio and targets AI startups in India. Swap the materials blocks in `prompts.py` for your own before using it.
- `.env` and `leads.csv` are gitignored. Keep them that way.

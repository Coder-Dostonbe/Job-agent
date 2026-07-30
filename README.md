# Job Search Agent 🤖

A personal job-hunting agent. Once a day it collects vacancies from **hh.uz**,
**OLX.uz** and **Telegram channels**, throws away everything that is not a real
job opening, scores what is left against your profile (keywords + Claude), and
sends you a single digest in Telegram.

Built for the Uzbek market (Tashkent, Python/Django), but every source, query
and profile lives in `config.py` — point it at your own.

## How it works

```
collect  →  dedupe  →  is-it-a-real-vacancy?  →  score  →  report
hh.uz       by URL     keyword rules            keyword    Telegram
OLX.uz      + SQLite   + Claude Haiku           + Claude   message
Telegram    history      (batched)              (top N)
```

**Why the vacancy filter?** Telegram job channels and OLX are full of posts that
look like vacancies but are not: résumés from job seekers, "I'll build you a
website" service ads, course advertising. The filter runs in two stages:

1. **Keyword rules** (`scoring/vacancy_filter.py`) — free, catches the obvious
   cases in Uzbek, Russian and English, and labels the rest `uncertain`.
2. **Claude Haiku** (`scoring/ai_filter.py`) — only the `uncertain` posts, sent
   in batches of 15. Costs well under a cent per day.

If the API key is missing or a request fails, the filter **fails open**: the post
is kept and the scoring stage decides. The agent never stops because of AI.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env    # then fill it in
```

### Getting the credentials

| Variable | Where to get it |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Create a bot with [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Message your bot, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id` |
| `TG_API_ID`, `TG_API_HASH` | [my.telegram.org](https://my.telegram.org) → API development tools |
| `TG_SESSION_STRING` | See below |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) — optional |

### Telegram session string

Reading public channels requires a **user** session, not a bot token — the Bot
API cannot read channels you do not own. Generate one once:

```bash
python create_session_qr.py
```

A QR code appears in your terminal. In the Telegram mobile app go to
**Settings → Devices → Link Desktop Device** and scan it. The script prints a
session string.

> ⚠️ That string is full access to your Telegram account — stronger than your
> password. Put it straight into `.env` or GitHub Secrets. Never paste it into a
> chat, an issue, or a commit. If it leaks, revoke it under Settings → Devices.

QR login is used instead of the usual phone-number flow because SMS and in-app
codes are unreliable on some networks. Without a session string the agent still
runs — it just skips the Telegram sources.

## Running it

```bash
python main.py
```

Vacancies already reported are remembered in `vacancies.db`, so you only ever
see each one once.

## Configuration (`config.py`)

| Setting | Meaning |
| --- | --- |
| `PROFILE` | Your skills, experience and role — drives all scoring |
| `SEARCH_QUERIES` | Search terms for hh.uz and OLX |
| `HH_AREA_ID` | hh.uz region id (`97` = Uzbekistan) |
| `TG_CHANNELS` | Channel usernames to watch, without `@` |
| `TG_LOOKBACK_HOURS` | How far back to read each channel |
| `OLX_URLS` | OLX search pages to scrape |
| `REPORT_MIN_SCORE` | Minimum keyword score to appear in the report |
| `AI_SCORE_THRESHOLD` / `AI_MAX_VACANCIES` | Cost control for deep AI analysis |
| `AI_FILTER_ENABLED` / `AI_FILTER_BATCH_SIZE` / `AI_FILTER_MAX_POSTS` | Cost control for the vacancy filter |

## Daily automation (GitHub Actions)

`.github/workflows/daily-jobs.yml` runs the agent at 04:00 UTC (09:00 Tashkent)
and can also be triggered by hand from the Actions tab.

1. Push the repo to GitHub.
2. **Settings → Secrets and variables → Actions** → add `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING` and
   `ANTHROPIC_API_KEY`.
3. Adjust the `cron:` line if you want a different time.

## Example report

```
📊 Kunlik ish hisoboti
Yangi vakansiyalar: 14 ta, mos kelganlari: 4 ta

🟢 1. Junior Python Developer
   hh.uz | FinTech LLC | 5000000–8000000 UZS
   AI: 82/100 — Django va DRF talab qilinadi, tajriba talabi past.
   💡 CV: Fezot Shop production loyihangizni birinchi qatorga chiqaring
   https://hh.uz/vacancy/...

📈 Bugun eng ko'p so'ralgan skillar: python (11), django (7), docker (5)...
```

The report itself is written in Uzbek — see the prompts in `scoring/ai_scorer.py`
and the labels in `reporter.py` if you want it in another language.

## Layout

```
main.py                     pipeline
config.py                   profile, sources, limits
storage.py                  SQLite history + URL dedupe
reporter.py                 Telegram delivery
create_session_qr.py        one-time Telethon session generator
collectors/  hh.py          hh.ru API
             olx.py         OLX HTML scraping
             tg_channels.py Telethon channel reader
scoring/     vacancy_filter.py  stage 1 — keyword rules
             ai_filter.py       stage 2 — Claude Haiku
             keyword_scorer.py  profile match score
             ai_scorer.py       deep analysis of the top matches
```

## Notes

- `*.session` files and `.env` are gitignored. Keep them that way.
- hh.uz may return `403` from datacenter IPs; the other sources keep working.
- The SQLite file is not persisted between GitHub Actions runs yet, so a
  scheduled run can re-report a vacancy it already sent.

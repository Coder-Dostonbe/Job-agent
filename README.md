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

**Nothing the model returns is trusted.** A language model is an untrusted input
source, not an API: it wraps JSON in prose, drops keys, writes `"85"` where a
number belongs, invents ids, and gets cut off mid-object at the token limit. So
the responses go through `scoring/ai_json.py` (find the JSON, whatever it is
wrapped in) and then through per-module validation:

- **Deep analysis** returns either `None` or a dict where `score` (int, 0–100),
  `verdict`, `reason` and `cv_tip` are all present and correctly typed. A
  missing `verdict` is rebuilt from the score rather than thrown away; a
  missing score drops the analysis and the vacancy falls back to its keyword
  score. One malformed response costs one vacancy's analysis — never the report.
- **The vacancy filter** validates each item on its own, so one bad entry no
  longer discards the whole batch of 15. Out-of-range ids are dropped: an
  invented id would otherwise apply one post's verdict to a different post.

How well the AI actually worked shows up in the health line
(`ai-tahlil 4/6 ⚠️`), because a report built entirely from keyword scores looks
exactly like a normal one.

**Source diagnostics.** Every report ends with a health line, so a broken
scraper never looks like a quiet job market:

```
🩺 Manbalar: hh.uz 63 ✅ | olx.uz 41 ✅ | telegram 6 ✅
```

If a source returns nothing without raising, fails outright, or is skipped for
missing credentials, the report also carries an explicit warning block. See
`health.py` — the collectors report into it, `reporter.build_health_block()`
renders it.

And if the agent crashes outright, it sends the reason before dying, then
re-raises so the Actions run is marked failed too. Silence is never the way
you find out something broke.

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
| `TG_SESSION_STRING` | See [Telegram session string](#telegram-session-string) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) — optional |
| `DATABASE_URL` | Any hosted Postgres ([Neon](https://neon.tech), [Supabase](https://supabase.com), …) — see [History](#history) |

hh.uz and OLX need no credentials.

> **Note on the hh.uz API.** `api.hh.uz` is not used. HeadHunter discontinued
> job-seeker API support on 15 December 2025 — `GET /vacancies` now returns
> `403 forbidden` without an application token, and applications can only be
> registered by employers. The collector reads the public search page instead
> (see `collectors/hh.py`).

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

### History

Every vacancy the agent has seen is remembered, so you are never shown the same
one twice. Two backends:

- **PostgreSQL** — used when `DATABASE_URL` is set. Required for scheduled runs:
  a GitHub Actions runner is wiped after every job, so a file on disk cannot
  survive to the next day.
- **SQLite** (`vacancies.db`) — the fallback when `DATABASE_URL` is empty. Fine
  for running locally; nothing to set up.

The table is created on first use. If Postgres is unreachable the agent retries
a few times (serverless databases are slow to wake), then falls back to SQLite
rather than failing — you still get the report, but it may repeat vacancies
until the connection is fixed.

That fallback is **reported, not silent**. The health line names the backend
actually in use, and a warning spells out the consequence:

```
🩺 Manbalar: hh.uz 64 ✅ | olx.uz 41 ✅ | storage sqlite (zaxira) ⚠️

⚠️ Manbalarda muammo:
⚠️ storage: Postgres ishlamadi, SQLite'ga o'tildi (Actions'da SQLite fayli
   run tugashi bilan o'chadi) — tarix o'qilmadi, ko'rilgan e'lonlar takror
   kelishi mumkin. Sabab: ConnectionTimeout: connection timeout expired
```

Running on Actions with no `DATABASE_URL` at all is flagged the same way: the
runner's disk is wiped after every job, so history is never kept and the same
vacancies arrive every morning. A failed *write* never costs you the report —
the digest is sent anyway, with the warning attached.

## Configuration (`config.py`)

| Setting | Meaning |
| --- | --- |
| `PROFILE` | Your skills, experience and role — drives all scoring |
| `SEARCH_QUERIES` | Search terms for hh.uz and OLX |
| `HH_AREA_ID` | hh.uz region id (`97` = Uzbekistan) |
| `HH_DESC_LIMIT` | How many hh.uz vacancies get their full text fetched (one request each) |
| `HH_DESC_MIN_RATIO` | Warn if fewer than this share of descriptions loaded — an unscored vacancy is a silently useless one |
| `DB_CONNECT_RETRIES` / `DB_CONNECT_TIMEOUT` / `DB_RETRY_DELAY` | Postgres connection attempts before falling back to SQLite |
| `TG_CHANNELS` | Channel usernames to watch, without `@` |
| `TG_LOOKBACK_HOURS` | How far back to read each channel |
| `OLX_URLS` | OLX search pages to scrape |
| `REPORT_MIN_SCORE` | Minimum keyword score to appear in the report |
| `REPORT_LIMIT` | Maximum vacancies in one report |
| `REPORT_SOURCE_QUOTA` | Slots guaranteed to each source, so a high-volume source cannot crowd the others out. Unused slots go to whoever else scored best |
| `AI_SCORE_THRESHOLD` / `AI_MAX_VACANCIES` | Cost control for deep AI analysis |
| `AI_MIN_SUCCESS_RATIO` | Warn if fewer than this share of AI analyses returned a usable answer |
| `AI_FILTER_ENABLED` / `AI_FILTER_BATCH_SIZE` / `AI_FILTER_MAX_POSTS` | Cost control for the vacancy filter |

## Daily automation (GitHub Actions)

`.github/workflows/daily-jobs.yml` runs the agent at 04:00 UTC (09:00 Tashkent)
and can also be triggered by hand from the Actions tab.

1. Push the repo to GitHub.
2. **Settings → Secrets and variables → Actions** → add `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_CHAT_ID`, `TG_API_ID`, `TG_API_HASH`, `TG_SESSION_STRING`,
   `DATABASE_URL`, and `ANTHROPIC_API_KEY`.
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
health.py                   per-source status + failure alerts
storage.py                  Postgres/SQLite history + URL dedupe
reporter.py                 Telegram delivery
create_session_qr.py        one-time Telethon session generator
collectors/  hh.py          hh.uz search page
             olx.py         OLX HTML scraping
             tg_channels.py Telethon channel reader
scoring/     vacancy_filter.py  stage 1 — keyword rules
             ai_filter.py       stage 2 — Claude Haiku
             ai_json.py         safe JSON extraction from model replies
             keyword_scorer.py  profile match score
             ai_scorer.py       deep analysis of the top matches
```

## Notes

- `*.session` files and `.env` are gitignored. Keep them that way.
- If a source fails (network, rate limit, a channel that no longer exists) the
  agent logs it and carries on with the rest.

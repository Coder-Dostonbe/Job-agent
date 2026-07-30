"""Fetch an hh.uz application access token (one-time setup).

Since 2025 the vacancy search endpoint rejects unauthenticated requests
with 403. An application token fixes that. It does not expire — generate
it once and store it.

Before running:
  1. Register an application at https://dev.hh.uz/admin
     (hh.uz has its own developer portal, separate from dev.hh.ru)
  2. Copy its Client ID and Client Secret into .env as
     HH_CLIENT_ID and HH_CLIENT_SECRET

Then:
  python get_hh_token.py

The token is printed. Put it in .env as HH_TOKEN, and in GitHub Secrets
under the same name. Requesting a new token revokes the previous one.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

import config

CLIENT_ID = os.getenv("HH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("HH_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: set HH_CLIENT_ID and HH_CLIENT_SECRET in .env first.")
    print("Register an app at https://dev.hh.uz/admin to get them.")
    raise SystemExit(1)

resp = requests.post(
    f"{config.HH_API_BASE}/token",
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    headers={"User-Agent": "job-agent/1.0 (job search assistant)"},
    timeout=15,
)

if not resp.ok:
    print(f"Request failed ({resp.status_code}): {resp.text[:300]}")
    raise SystemExit(1)

token = resp.json().get("access_token", "")
if not token:
    print(f"No access_token in response: {resp.text[:300]}")
    raise SystemExit(1)

print("\n" + "=" * 60)
print("HH_TOKEN:")
print("=" * 60)
print(token)
print("=" * 60)
print("\nAdd it to .env as HH_TOKEN=... and to GitHub Secrets as HH_TOKEN.")
print("Keep it private. Generating a new token revokes this one.")

"""Create a Telethon StringSession via QR code (no SMS / login code needed).

Usage:
    python create_session_qr.py

A QR code appears in the terminal. In the Telegram app on your phone:
    Settings -> Devices -> Link Desktop Device
and scan it. You will be asked for your 2FA password if you have one.

At the end a StringSession is printed. Store it in GitHub Secrets as
TG_SESSION_STRING. Never share it — it grants full access to your account.
"""
import asyncio
import os
from getpass import getpass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")

if not API_ID or not API_HASH:
    print("ERROR: TG_API_ID and TG_API_HASH must be set in .env")
    raise SystemExit(1)


def show_qr(url: str) -> None:
    """Draw the QR in the terminal; fall back to the raw link."""
    try:
        import qrcode
    except ImportError:
        print("\n(run 'pip install qrcode' to render the QR in the terminal)")
        print("Link (for QR generation only, not clickable):\n" + url)
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)


async def main():
    print("Telethon StringSession — QR login")
    print(f"API_ID: {API_ID}\n")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    qr_login = await client.qr_login()
    print("On your phone: Settings -> Devices -> Link Desktop Device")
    print("then scan the QR code below:\n")
    show_qr(qr_login.url)

    while True:
        try:
            await qr_login.wait(60)
            break
        except asyncio.TimeoutError:
            # The QR expires after 60 seconds — draw a fresh one
            print("\nQR expired, here is a new one:\n")
            await qr_login.recreate()
            show_qr(qr_login.url)
        except SessionPasswordNeededError:
            print("\n2FA is enabled. Enter your password (input is hidden):")
            await client.sign_in(password=getpass("Password: "))
            break

    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name}")
    print("\n" + "=" * 60)
    print("STRING SESSION (paste into GitHub Secrets only!):")
    print("=" * 60)
    print(client.session.save())
    print("=" * 60)
    print("\nGitHub -> Settings -> Secrets and variables -> Actions ->")
    print("New repository secret -> Name: TG_SESSION_STRING")
    await client.disconnect()


asyncio.run(main())

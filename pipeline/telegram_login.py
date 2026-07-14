"""Two-step, non-interactive Telegram login (creates the Telethon session file).

Telethon's own login prompts for stdin, which is not available when the script is
driven from a tool. So we split it:

    python3 pipeline/telegram_login.py +39XXXXXXXXXX          # asks Telegram for a code
    python3 pipeline/telegram_login.py +39XXXXXXXXXX 12345    # signs in with the code
    python3 pipeline/telegram_login.py +39XXXXXXXXXX 12345 pw # ...if 2FA is on

The code arrives inside the Telegram app, not by SMS. Run once; telegram.py then
runs unattended against the saved session.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError

ROOT = Path(__file__).resolve().parents[1]
PENDING = ROOT / ".tg_pending.json"  # carries phone_code_hash between the two steps


def env(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{key} mancante in .env")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("uso: telegram_login.py <telefono> [codice] [password2fa]")
    phone = sys.argv[1]
    code = sys.argv[2] if len(sys.argv) > 2 else None
    password = sys.argv[3] if len(sys.argv) > 3 else None

    client = TelegramClient(str(ROOT / "tg.session"),
                            int(env("TG_API_ID")), env("TG_API_HASH"))
    client.connect()

    if client.is_user_authorized():
        me = client.get_me()
        print(f"gia' autenticato come {me.first_name}")
        return

    if not code:
        sent = client.send_code_request(phone)
        PENDING.write_text(json.dumps({"phone": phone,
                                       "hash": sent.phone_code_hash}))
        print("Codice inviato dentro l'app Telegram.")
        print(f"Ora lancia: python3 pipeline/telegram_login.py {phone} <codice>")
        return

    pending = json.loads(PENDING.read_text())
    try:
        client.sign_in(phone=phone, code=code, phone_code_hash=pending["hash"])
    except SessionPasswordNeededError:
        if not password:
            raise SystemExit("hai la verifica in due passaggi: rilancia aggiungendo "
                             "la password come terzo argomento")
        client.sign_in(password=password)

    me = client.get_me()
    PENDING.unlink(missing_ok=True)
    print(f"Login riuscito: {me.first_name}. Sessione salvata, la raccolta puo' partire.")


if __name__ == "__main__":
    main()

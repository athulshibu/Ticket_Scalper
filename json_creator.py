import json
import getpass
from pathlib import Path
import os

def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    my_id = input("My Telgram ID (optional): ").strip()
    notification_bot_http_api = input("Notification Bot HTTP API (optional): ").strip()


    data = {"username": username, "password": password, "my_id": my_id, "notification_bot_http_api": notification_bot_http_api}

    out = Path("credentials.json")
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"Created {out.resolve()}")

if __name__ == "__main__":
    main()

"""Manual test script to verify beep_beep() sound and Telegram notification work.

Run with: python test_beep_beep.py
"""
import json
import psutil
import requests

from scalper_selenium import beep_beep

if __name__ == "__main__":
    print("Testing local beep sound (count=3)...")
    beep_beep(count=3)

    print("Testing Telegram notification (no count, uses credentials.json)...")

    battery = psutil.sensors_battery()
    percent = battery.percent if battery is not None else -1

    # Call the raw Telegram API directly so we can see *why* it fails, since
    # beep_beep() itself doesn't check/print the response.
    with open("credentials.json", encoding="utf-8") as f:
        data = json.load(f)
    my_id = data.get("my_id")
    token = data.get("notification_bot_http_api")

    # Diagnostic: list chats that have messaged this bot, to confirm my_id is correct.
    updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates").json()
    print(f"getUpdates: {updates}")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.get(url, params={"chat_id": my_id, "text": "Test message from test_beep_beep.py"})
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")

    beep_beep(message="Test message from test_beep_beep.py")
    beep_beep(message=f"Battery level: {percent}%", count=1)

    print("Done. Check your speakers and Telegram chat.")

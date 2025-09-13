import json
import getpass
from pathlib import Path
import os

def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")

    data = {"username": username, "password": password}

    out = Path("credentials.json")
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    print(f"Created {out.resolve()}")

if __name__ == "__main__":
    main()

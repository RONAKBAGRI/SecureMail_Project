"""
Node 4 – Admin Dashboard (Sunny)
Live CLI view of mailbox stats, refreshes every 5 seconds.
Run independently: python node4_pop3/admin_dashboard.py
"""
from __future__ import annotations
import os
import sys
import time
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _count_and_size(folder_path: str) -> tuple[int, int]:
    """Returns (count, total_bytes) for .enc files in a folder."""
    if not os.path.exists(folder_path):
        return 0, 0
    files = [f for f in os.listdir(folder_path) if f.endswith(".enc")]
    total = sum(os.path.getsize(os.path.join(folder_path, f)) for f in files)
    return len(files), total


def _read_meta(filepath: str) -> dict:
    meta = filepath.replace(".enc", ".meta")
    if os.path.exists(meta):
        try:
            with open(meta) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def print_dashboard():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("╔══════════════════════════════════════════════════╗")
        print("║         SECUREMAIL – ADMIN DASHBOARD (Node 4)   ║")
        print(f"║  Refreshed: {now}              ║")
        print("╠══════════════════════════════════════════════════╣")

        storage = config.SHARED_STORAGE_DIR
        if not os.path.exists(storage):
            print("║  No storage directory found yet.                ║")
            print("╚══════════════════════════════════════════════════╝")
            time.sleep(5)
            continue

        total_inbox = total_spam = 0
        for user in sorted(os.listdir(storage)):
            user_path = os.path.join(storage, user)
            if not os.path.isdir(user_path):
                continue

            inbox_cnt, inbox_sz = _count_and_size(os.path.join(user_path, "inbox"))
            spam_cnt,  spam_sz  = _count_and_size(os.path.join(user_path, "spam"))
            total_inbox += inbox_cnt
            total_spam  += spam_cnt

            print(f"║  User: {user:<38} ║")
            print(f"║    Inbox : {inbox_cnt:3} messages  ({inbox_sz:>8} bytes)          ║")
            print(f"║    Spam  : {spam_cnt:3} messages  ({spam_sz:>8} bytes)          ║")
            print("║  ────────────────────────────────────────────  ║")

        print(f"║  TOTAL  Inbox: {total_inbox:<5}  |  Spam: {total_spam:<5}              ║")
        print("╚══════════════════════════════════════════════════╝")
        print("  (Press Ctrl+C to exit)")
        time.sleep(5)


if __name__ == "__main__":
    try:
        print_dashboard()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")

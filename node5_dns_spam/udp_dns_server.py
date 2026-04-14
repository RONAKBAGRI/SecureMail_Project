"""
Node 5 – UDP DNS Verifier + Spam Filter (Amit)

Listens on UDP port 5053. Accepts JSON queries:
  {"action": "VERIFY",     "email": "user@domain"}
  {"action": "SPAM_CHECK", "content": "email body"}
  {"action": "REGISTER",   "email": "newuser@domain"}   ← NEW

Responses:
  VERIFY     → {"status": "OK"}  |  {"status": "FAIL"}
  SPAM_CHECK → {"is_spam": true} |  {"is_spam": false}
  REGISTER   → {"status": "OK"}  |  {"status": "ERR", "reason": "..."}
"""
import socket
import json
import sys
import os
import threading
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from spam_filter import SpamFilterModule

logging.basicConfig(
    level=logging.INFO,
    format="[NODE5-DNS][%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

USERS_FILE = os.path.join(os.path.dirname(__file__), "valid_users.json")
LISTEN_IP  = "0.0.0.0"
_file_lock = threading.Lock()

# ── Initialize Machine Learning Spam Scanner ──────────────────────────────────
# Load the model into RAM exactly once when the server starts
try:
    scanner = SpamFilterModule()
except Exception as e:
    log.error(f"Could not load AI Spam Scanner: {e}")
    scanner = None


# ── User file helpers ─────────────────────────────────────────────────────────

def _load_users() -> set:
    try:
        with open(USERS_FILE, "r") as f:
            return set(json.load(f).get("users", []))
    except Exception as e:
        log.error(f"Could not load users: {e}")
        return set()


def _save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump({"users": sorted(users)}, f, indent=4)


# ── Request processor ─────────────────────────────────────────────────────────

def _process(req: dict) -> dict:
    action = req.get("action", "").upper()

    if action == "VERIFY":
        email = req.get("email", "").strip().lower()
        users = {u.lower() for u in _load_users()}
        valid = email in users
        log.info(f"VERIFY {email!r} → {'OK' if valid else 'FAIL'}")
        return {"status": "OK" if valid else "FAIL"}

    elif action == "SPAM_CHECK":
        content = req.get("content", "")
        
        # Use the loaded ML model for prediction
        if scanner:
            spam_result = scanner.is_spam(content)
        else:
            log.warning("Spam scanner unavailable, defaulting to false.")
            spam_result = False
            
        log.info(f"SPAM_CHECK → is_spam={spam_result}")
        return {"is_spam": spam_result}

    elif action == "REGISTER":
        email = req.get("email", "").strip().lower()
        if not email or "@" not in email:
            return {"status": "ERR", "reason": "Invalid email"}
        with _file_lock:
            users = _load_users()
            if email not in {u.lower() for u in users}:
                users.add(email)
                _save_users(users)
                log.info(f"REGISTER {email!r} → added")
            else:
                log.info(f"REGISTER {email!r} → already exists, OK")
        return {"status": "OK"}

    else:
        log.warning(f"Unknown action: {action!r}")
        return {"error": "Unknown action"}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, config.DNS_SPAM_PORT))
    log.info(f"UDP DNS/Spam server on {LISTEN_IP}:{config.DNS_SPAM_PORT}")

    while True:
        try:
            raw, addr = sock.recvfrom(65535)
            req       = json.loads(raw.decode("utf-8"))
            response  = _process(req)
            sock.sendto(json.dumps(response).encode(), addr)
        except json.JSONDecodeError:
            log.warning("Malformed JSON — ignored.")
        except Exception as e:
            log.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
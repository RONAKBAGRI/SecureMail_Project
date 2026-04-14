"""
Node 4 – User Manager (Sunny)
Single source of truth for credentials on Node 4.
Thread-safe reads/writes to users.txt.
Also notifies Node 5 via UDP to add the new user to valid_users.json.
"""
import os
import json
import socket
import threading
import logging
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log        = logging.getLogger(__name__)
_lock      = threading.Lock()
USERS_FILE = os.path.join(os.path.dirname(__file__), "users.txt")


def load_users() -> dict:
    """Return {email: password} from users.txt. Thread-safe read."""
    users = {}
    if not os.path.exists(USERS_FILE):
        return users
    with open(USERS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and ":" in line:
                u, p = line.split(":", 1)
                users[u.strip().lower()] = p.strip()
    return users


def add_user(email: str, password: str) -> tuple:
    """
    Register a new user.
    Steps:
      1. Validate inputs
      2. Check for duplicate (thread-safe)
      3. Append to users.txt
      4. Create storage/inbox and storage/spam directories
      5. Notify Node 5 via UDP

    Returns (success: bool, message: str).
    """
    email = email.strip().lower()

    if not email or "@" not in email:
        return False, "Invalid email address."
    if not password or len(password) < 4:
        return False, "Password must be at least 4 characters."

    with _lock:
        existing = load_users()
        if email in existing:
            return False, "User already exists."

        try:
            with open(USERS_FILE, "a") as f:
                f.write(f"{email}:{password}\n")
        except OSError as e:
            return False, f"Could not write users file: {e}"

        for folder in ("inbox", "spam"):
            path = os.path.join(config.SHARED_STORAGE_DIR, email, folder)
            try:
                os.makedirs(path, exist_ok=True)
            except OSError as e:
                log.warning(f"Could not create dir {path}: {e}")

    _notify_node5(email)
    log.info(f"[USER_MGR] Registered: {email}")
    return True, "Registration successful."


def _notify_node5(email: str):
    """Tell Node 5 to add this email to valid_users.json."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0)
        req = json.dumps({"action": "REGISTER", "email": email}).encode()
        sock.sendto(req, (config.DNS_SPAM_IP, config.DNS_SPAM_PORT))
        resp, _ = sock.recvfrom(256)
        result   = json.loads(resp.decode())
        if result.get("status") == "OK":
            log.info(f"[USER_MGR] Node 5 confirmed registration for {email}")
        else:
            log.warning(f"[USER_MGR] Node 5 unexpected response: {result}")
    except socket.timeout:
        log.warning("[USER_MGR] Node 5 timed out on REGISTER — user added locally only.")
    except Exception as e:
        log.error(f"[USER_MGR] Failed to notify Node 5: {e}")
    finally:
        if sock:
            sock.close()

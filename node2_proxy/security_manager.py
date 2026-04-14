import os
import logging

log = logging.getLogger(__name__)
BLACKLIST_FILE = os.path.join(os.path.dirname(__file__), "blacklist.txt")


def is_ip_allowed(ip_address: str) -> bool:
    """Return True if the IP is NOT on the blacklist."""
    if not os.path.exists(BLACKLIST_FILE):
        return True
    try:
        with open(BLACKLIST_FILE, "r") as f:
            blocked = {line.strip() for line in f if line.strip() and not line.startswith("#")}
        if ip_address in blocked:
            log.warning(f"[SECURITY] Blocked connection from blacklisted IP: {ip_address}")
            return False
        return True
    except OSError as e:
        log.error(f"[SECURITY] Could not read blacklist: {e}")
        return True  # Fail open
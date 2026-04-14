"""UDP client helpers for querying Node 5 (DNS + Spam Filter)."""

import socket
import json
import sys
import os
import logging
from typing import Optional  # ✅ FIX: for Python < 3.10

# Add parent directory to path (to import config)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log = logging.getLogger(__name__)

UDP_TIMEOUT = 3.0


def _udp_query(payload: dict) -> Optional[dict]:
    """
    Send a JSON query to Node 5 and return the parsed response.
    Returns None if timeout or error occurs.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(UDP_TIMEOUT)

    try:
        data = json.dumps(payload).encode()
        sock.sendto(data, (config.DNS_SPAM_IP, config.DNS_SPAM_PORT))

        resp, _ = sock.recvfrom(4096)
        return json.loads(resp.decode())

    except socket.timeout:
        log.warning(f"[UDP] Node 5 timed out for query: {payload.get('action')}")
        return None

    except Exception as e:
        log.error(f"[UDP] Query error: {e}")
        return None

    finally:
        sock.close()


def verify_user(email: str) -> bool:
    """
    Return True if the email address is registered in Node 5.
    """
    resp = _udp_query({"action": "VERIFY", "email": email})

    if resp is None:
        log.warning("[UDP] VERIFY timed out; defaulting to REJECT.")
        return False

    return resp.get("status") == "OK"


def check_spam_score(content: str) -> bool:
    """
    Return True if the content is classified as spam by Node 5.
    """
    resp = _udp_query({"action": "SPAM_CHECK", "content": content})

    if resp is None:
        log.warning("[UDP] SPAM_CHECK timed out; defaulting to NOT spam.")
        return False

    return bool(resp.get("is_spam", False))
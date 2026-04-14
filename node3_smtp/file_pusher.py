"""
Immediately pushes a saved email and its metadata to Node 4 (Sunny)
over a direct TCP connection on FILE_TRANSFER_PORT.
Uses length-prefixed framing: 4-byte big-endian length + JSON payload.
"""
import socket
import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log     = logging.getLogger(__name__)
TIMEOUT = 10


def push_email(
    recipient: str,
    folder:    str,
    filename:  str,
    content:   str,
    meta:      dict,
) -> bool:
    """
    Push one email to Node 4 immediately after it is stored on Node 3.
    Returns True on success, False on any failure.
    Failure is non-fatal — the email is already saved locally on Node 3.
    """
    payload = json.dumps({
        "recipient": recipient,
        "folder":    folder,
        "filename":  filename,
        "content":   content,
        "meta":      meta,
    }).encode("utf-8")

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((config.POP3_IP, config.FILE_TRANSFER_PORT))

        # 4-byte big-endian length prefix + payload
        sock.sendall(len(payload).to_bytes(4, "big") + payload)

        ack = sock.recv(8).strip()
        if ack == b"ACK":
            log.info(f"[PUSHER] Delivered → {recipient}/{folder}/{filename}")
            return True
        else:
            log.error(f"[PUSHER] Unexpected ack from Node 4: {ack!r}")
            return False

    except ConnectionRefusedError:
        log.error("[PUSHER] Node 4 unreachable. Email stored locally on Node 3 only.")
        return False
    except socket.timeout:
        log.error("[PUSHER] Timed out pushing to Node 4.")
        return False
    except Exception as e:
        log.error(f"[PUSHER] Unexpected error: {e}", exc_info=True)
        return False
    finally:
        if sock:
            sock.close()
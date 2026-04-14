"""
Node 3 – SMTP Server / MTA (Gaurav)

Handles: HELO/EHLO, MAIL FROM, RCPT TO, DATA, RSET, NOOP, QUIT
  • Verifies recipient via UDP → Node 5
  • Uses spam flag from Node 2 proxy (if available)
  • Fallback: checks spam locally if no flag
  • Stores encrypted body to local disk
  • Writes metadata receipt
  • Immediately pushes email to Node 4 via TCP (file_pusher)
  • Multi-threaded
"""

import socket
import threading
import os
import time
import datetime
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from udp_client_helper import verify_user, check_spam_score
from receipt_manager import generate_receipt
from file_pusher import push_email

logging.basicConfig(
    level=logging.INFO,
    format="[NODE3-SMTP][%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

LISTEN_IP = "0.0.0.0"
MAX_BODY  = 10 * 1024 * 1024


# ── Socket helpers ────────────────────────────────────────────────────────────

def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Client disconnected")
        buf += ch
    return buf.decode("utf-8", errors="replace").rstrip("\r\n")


def _recv_until(sock: socket.socket, terminator: bytes, max_size: int = MAX_BODY) -> bytes:
    buf = b""
    while not buf.endswith(terminator):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Client disconnected mid-body")
        buf += chunk
        if len(buf) > max_size:
            raise OverflowError("Body too large")
    return buf


# ── Per-connection handler ────────────────────────────────────────────────────

def _handle_client(conn: socket.socket, addr):
    sender, rcpt = None, None
    try:
        conn.sendall(b"220 SecureMail SMTP Ready\r\n")
        log.info(f"Connection from {addr[0]}")

        while True:
            line = _recv_line(conn)
            if not line:
                continue

            cmd = line.upper().split()[0] if line.split() else ""
            log.debug(f"  C: {line}")

            if cmd in ("HELO", "EHLO"):
                conn.sendall(b"250 Hello. SecureMail SMTP at your service.\r\n")

            elif cmd == "MAIL":
                try:
                    sender = line.split(":<", 1)[1].rstrip(">").strip()
                except IndexError:
                    conn.sendall(b"501 Syntax: MAIL FROM:<address>\r\n")
                    continue
                conn.sendall(b"250 OK\r\n")
                log.info(f"MAIL FROM: {sender}")

            elif cmd == "RCPT":
                try:
                    rcpt = line.split(":<", 1)[1].rstrip(">").strip()
                except IndexError:
                    conn.sendall(b"501 Syntax: RCPT TO:<address>\r\n")
                    continue

                if verify_user(rcpt):
                    conn.sendall(b"250 OK\r\n")
                    log.info(f"RCPT TO accepted: {rcpt}")
                else:
                    conn.sendall(b"550 No such user here\r\n")
                    log.warning(f"RCPT TO rejected: {rcpt}")
                    rcpt = None

            # ───────────────────────────────────────────────────────────────
            # ✅ FIXED DATA HANDLING WITH PROXY SPAM FLAG
            # ───────────────────────────────────────────────────────────────

            elif cmd == "DATA":
                if not sender or not rcpt:
                    conn.sendall(b"503 Bad sequence of commands\r\n")
                    continue

                conn.sendall(b"354 End data with <CRLF>.<CRLF>\r\n")

                raw = _recv_until(conn, b"\r\n.\r\n")

                # Remove SMTP terminator
                raw_stripped = raw[:-5]

                # Try to extract spam flag from Node 2 proxy
                first_newline = raw_stripped.find(b"\r\n")

                if first_newline != -1:
                    flag_line = raw_stripped[:first_newline].decode(
                        "utf-8", errors="replace"
                    ).strip()

                    if flag_line in ("SPAM:YES", "SPAM:NO"):
                        is_spam = (flag_line == "SPAM:YES")
                        body = raw_stripped[first_newline + 2:].decode(
                            "utf-8", errors="replace"
                        )
                        log.info(f"Spam flag from proxy: {flag_line}")

                    else:
                        # Fallback: no valid flag
                        body = raw_stripped.decode("utf-8", errors="replace")
                        is_spam = check_spam_score(body)
                        log.warning("No spam flag from proxy; fallback to local check.")

                else:
                    # Edge case: no newline found
                    body = raw_stripped.decode("utf-8", errors="replace")
                    is_spam = check_spam_score(body)
                    log.warning("Malformed DATA: fallback to local spam check.")

                folder = "spam" if is_spam else "inbox"

                # ── Store email ────────────────────────────────────────────
                save_dir = os.path.join(config.SHARED_STORAGE_DIR, rcpt, folder)
                os.makedirs(save_dir, exist_ok=True)

                filename = f"{int(time.time() * 1000)}.enc"
                filepath = os.path.join(save_dir, filename)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(body)

                meta = {
                    "sender": sender,
                    "recipient": rcpt,
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "status": "Quarantined" if is_spam else "Delivered",
                    "spam": is_spam,
                }

                generate_receipt(filepath, sender, rcpt, is_spam)

                # ── Push to Node 4 ────────────────────────────────────────
                push_email(rcpt, folder, filename, body, meta)

                log.info(f"Stored + pushed: {filepath} | spam={is_spam}")
                conn.sendall(b"250 Message accepted for delivery\r\n")

                sender, rcpt = None, None

            # ───────────────────────────────────────────────────────────────

            elif cmd == "RSET":
                sender, rcpt = None, None
                conn.sendall(b"250 OK\r\n")

            elif cmd == "NOOP":
                conn.sendall(b"250 OK\r\n")

            elif cmd == "QUIT":
                conn.sendall(b"221 Bye\r\n")
                break

            else:
                conn.sendall(b"500 Command not recognized\r\n")

    except ConnectionError as e:
        log.warning(f"Client {addr[0]} disconnected: {e}")
    except OverflowError:
        log.warning(f"Client {addr[0]} sent oversized body.")
        try:
            conn.sendall(b"552 Message too large\r\n")
        except Exception:
            pass
    except Exception as e:
        log.error(f"Error handling {addr}: {e}", exc_info=True)
    finally:
        conn.close()
        log.info(f"Connection from {addr[0]} closed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_IP, config.SMTP_PORT))
    srv.listen(10)

    log.info(f"SMTP Server listening on {LISTEN_IP}:{config.SMTP_PORT}")

    try:
        while True:
            conn, addr = srv.accept()
            conn.settimeout(30)

            threading.Thread(
                target=_handle_client,
                args=(conn, addr),
                daemon=True
            ).start()

    except KeyboardInterrupt:
        log.info("SMTP Server shutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
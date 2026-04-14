"""
Node 1 – SMTP Sender (Prashant)
================================
Connects through the Node 2 proxy to the Node 3 SMTP server.

Changes in this version:
  • Multi-recipient 'to' (comma-separated list)
  • CC  – additional recipients included in headers
  • BCC – additional recipients delivered silently (stripped from headers)
  • In-Reply-To / Message-ID headers for threaded replies
  • Returns sent-mail dict for local Sent-cache storage
"""

import socket
import sys
import os
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _recv_line(sock):
    """Read one CRLF-terminated line from socket."""
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Connection closed unexpectedly")
        buf += ch
    return buf.decode("utf-8", errors="replace").strip()


def _parse_addresses(field: str) -> list:
    """Split a comma-separated address string into a clean list."""
    if not field:
        return []
    return [a.strip() for a in field.split(",") if a.strip()]


def _send_to_one(sock, recipient: str) -> tuple:
    """Issue a single RCPT TO command. Returns (ok, error_str)."""
    sock.sendall(f"RCPT TO:<{recipient}>\r\n".encode())
    resp = _recv_line(sock)
    if resp.startswith("550"):
        return False, f"Recipient rejected: {recipient} (no such user)"
    if not resp.startswith("250"):
        return False, f"RCPT TO rejected for {recipient}: {resp}"
    return True, ""


def send_email(
    sender: str,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    in_reply_to: str = "",
    message_id: str = "",
):
    """
    Send an email through the proxy to Node 3 SMTP.

    Parameters
    ----------
    sender      : str   From address
    to          : str   Comma-separated To addresses
    subject     : str
    body        : str
    cc          : str   Comma-separated CC addresses (optional)
    bcc         : str   Comma-separated BCC addresses — delivered but NOT in headers
    in_reply_to : str   Message-ID of email being replied to (optional)
    message_id  : str   Override auto-generated Message-ID (optional)

    Returns
    -------
    (True,  sent_dict)   on success — dict contains all metadata for Sent cache
    (False, error_str)   on failure
    """
    to_list  = _parse_addresses(to)
    cc_list  = _parse_addresses(cc)
    bcc_list = _parse_addresses(bcc)

    if not to_list:
        return False, "At least one 'To' recipient is required."

    all_recipients = to_list + cc_list + bcc_list

    # Generate Message-ID for threading
    msg_id = message_id or f"<{int(time.time()*1000)}.{uuid.uuid4().hex[:8]}@securemail>"

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((config.PROXY_IP, config.PROXY_PORT))

        # ── Route announcement ──────────────────────────────────
        sock.sendall(b"ROUTE:SMTP\r\n")
        ready = _recv_line(sock)
        if ready != "READY":
            return False, f"Proxy not ready: {ready}"

        # ── SMTP handshake ──────────────────────────────────────
        banner = _recv_line(sock)  # 220 …
        if not banner.startswith("220"):
            return False, f"Unexpected banner: {banner}"

        sock.sendall(b"HELO client\r\n")
        resp = _recv_line(sock)
        if not resp.startswith("250"):
            return False, f"HELO rejected: {resp}"

        sock.sendall(f"MAIL FROM:<{sender}>\r\n".encode())
        resp = _recv_line(sock)
        if not resp.startswith("250"):
            return False, f"MAIL FROM rejected: {resp}"

        # ── RCPT TO for every recipient (To + CC + BCC) ────────
        rejected = []
        accepted = []
        for rcpt in all_recipients:
            ok, err = _send_to_one(sock, rcpt)
            if ok:
                accepted.append(rcpt)
            else:
                rejected.append((rcpt, err))

        if not accepted:
            return False, "All recipients were rejected:\n" + "\n".join(
                f"  {r}: {e}" for r, e in rejected
            )

        # ── DATA ────────────────────────────────────────────────
        sock.sendall(b"DATA\r\n")
        resp = _recv_line(sock)
        if not resp.startswith("354"):
            return False, f"DATA rejected: {resp}"

        # Build RFC 822-style headers.  BCC is intentionally omitted.
        headers = (
            f"Message-ID: {msg_id}\r\n"
            f"From: {sender}\r\n"
            f"To: {', '.join(to_list)}\r\n"
        )
        if cc_list:
            headers += f"CC: {', '.join(cc_list)}\r\n"
        if in_reply_to:
            headers += f"In-Reply-To: {in_reply_to}\r\n"
        headers += f"Subject: {subject}\r\n"

        email_payload = headers + "\r\n" + body + "\r\n.\r\n"
        sock.sendall(email_payload.encode())

        resp = _recv_line(sock)
        if not resp.startswith("250"):
            return False, f"Message rejected: {resp}"

        sock.sendall(b"QUIT\r\n")
        _recv_line(sock)  # 221 Bye

        # Build sent-mail record for the Sent cache
        sent_dict = {
            "message_id": msg_id,
            "from":       sender,
            "to":         ", ".join(to_list),
            "cc":         ", ".join(cc_list),
            "subject":    subject,
            "body":       body,
            "timestamp":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            # 'raw' mirrors what the inbox viewer expects
            "raw": (
                f"Message-ID: {msg_id}\r\n"
                f"From: {sender}\r\n"
                f"To: {', '.join(to_list)}\r\n"
                + (f"CC: {', '.join(cc_list)}\r\n" if cc_list else "")
                + (f"In-Reply-To: {in_reply_to}\r\n" if in_reply_to else "")
                + f"Subject: {subject}\r\n\r\n{body}"
            ),
        }

        warn = ""
        if rejected:
            warn = (
                "\n\nWarning – some recipients were rejected:\n"
                + "\n".join(f"  {r}: {e}" for r, e in rejected)
            )

        return True, sent_dict

    except ConnectionRefusedError:
        return False, "Could not connect to proxy. Is Node 2 running?"
    except socket.timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)
    finally:
        if sock:
            sock.close()

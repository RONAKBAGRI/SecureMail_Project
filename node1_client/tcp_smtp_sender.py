import socket
import sys
import os

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


def send_email(sender: str, recipient: str, subject: str, body: str):
    """
    Send an email through the proxy.
    Returns (success: bool, message: str)
    """
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

        sock.sendall(f"RCPT TO:<{recipient}>\r\n".encode())
        resp = _recv_line(sock)
        if resp.startswith("550"):
            return False, f"Recipient rejected: {recipient} (no such user)"
        if not resp.startswith("250"):
            return False, f"RCPT TO rejected: {resp}"

        sock.sendall(b"DATA\r\n")
        resp = _recv_line(sock)
        if not resp.startswith("354"):
            return False, f"DATA rejected: {resp}"

        # ── Email payload (RFC 822-style) ───────────────────────
        email_payload = (
            f"From: {sender}\r\n"
            f"To: {recipient}\r\n"
            f"Subject: {subject}\r\n"
            f"\r\n"
            f"{body}\r\n"
            f".\r\n"
        )
        sock.sendall(email_payload.encode())

        resp = _recv_line(sock)
        if not resp.startswith("250"):
            return False, f"Message rejected: {resp}"

        sock.sendall(b"QUIT\r\n")
        _recv_line(sock)  # 221 Bye
        return True, "Email sent successfully."

    except ConnectionRefusedError:
        return False, "Could not connect to proxy. Is Node 2 running?"
    except socket.timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)
    finally:
        if sock:
            sock.close()
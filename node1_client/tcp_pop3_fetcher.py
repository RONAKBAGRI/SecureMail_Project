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


def _recv_multiline(sock):
    """Read a POP3 multi-line response ending with CRLF.CRLF."""
    buf = b""
    while not buf.endswith(b"\r\n.\r\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Connection closed mid-response")
        buf += chunk
    # Strip the trailing \r\n.\r\n and the leading status line
    lines = buf.decode("utf-8", errors="replace").split("\r\n", 1)
    status = lines[0]
    body   = lines[1].rsplit("\r\n.\r\n", 1)[0] if len(lines) > 1 else ""
    return status, body


def fetch_emails(username: str, password: str):
    """
    Fetch all inbox emails for a user through the proxy.
    Returns (success: bool, emails: list[dict] | error_str)
    Each dict: {"index": int, "raw": str}
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((config.PROXY_IP, config.PROXY_PORT))

        # ── Route announcement ──────────────────────────────────
        sock.sendall(b"ROUTE:POP3\r\n")
        ready = _recv_line(sock)
        if ready != "READY":
            return False, f"Proxy not ready: {ready}"

        # ── POP3 login ──────────────────────────────────────────
        _recv_line(sock)  # +OK banner

        sock.sendall(f"USER {username}\r\n".encode())
        resp = _recv_line(sock)
        if not resp.startswith("+OK"):
            return False, f"USER rejected: {resp}"

        sock.sendall(f"PASS {password}\r\n".encode())
        resp = _recv_line(sock)
        if resp.startswith("-ERR"):
            return False, "Authentication failed. Check username/password."

        # ── STAT – how many messages? ───────────────────────────
        sock.sendall(b"STAT\r\n")
        stat = _recv_line(sock)  # +OK N M
        parts = stat.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return False, f"Bad STAT response: {stat}"
        msg_count = int(parts[1])

        # ── RETR each message ───────────────────────────────────
        emails = []
        for i in range(1, msg_count + 1):
            sock.sendall(f"RETR {i}\r\n".encode())
            status, body = _recv_multiline(sock)
            if status.startswith("+OK"):
                emails.append({"index": i, "raw": body})

        sock.sendall(b"QUIT\r\n")
        _recv_line(sock)
        return True, emails

    except ConnectionRefusedError:
        return False, "Could not connect to proxy. Is Node 2 running?"
    except socket.timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)
    finally:
        if sock:
            sock.close()
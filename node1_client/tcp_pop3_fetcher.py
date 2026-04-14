"""
Node 1 – POP3 Fetcher / Client (Prashant)
==========================================
Connects through the Node 2 proxy to the Node 4 POP3 server.

Changes in this version:
  • fetch_emails now also parses Message-ID and In-Reply-To headers
    so the GUI can build threaded conversation views.

Exports:
  fetch_emails(username, password, folder="inbox")
      → (True, [{
            "index"       : int,
            "raw"         : str,
            "message_id"  : str,   ← NEW: value of Message-ID header
            "in_reply_to" : str,   ← NEW: value of In-Reply-To header (or "")
         }, …]) | (False, error_str)

  delete_email(username, password, folder, msg_index)
      → (True, "Message #N deleted.") | (False, error_str)
      Uses XDELE – an extended command that immediately removes the
      message from Node 4 AND triggers deletion on Node 3.
"""

import socket
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ── Socket helpers ────────────────────────────────────────────────────────────

def _recv_line(sock: socket.socket) -> str:
    """Read one CRLF-terminated line from socket."""
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Connection closed unexpectedly")
        buf += ch
    return buf.decode("utf-8", errors="replace").strip()


def _recv_multiline(sock: socket.socket):
    """
    Read a POP3 multi-line response ending with CRLF.CRLF.
    Returns (status_line: str, body: str).
    """
    buf = b""
    while not buf.endswith(b"\r\n.\r\n"):
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Connection closed mid-response")
        buf += chunk
    lines = buf.decode("utf-8", errors="replace").split("\r\n", 1)
    status = lines[0]
    body   = lines[1].rsplit("\r\n.\r\n", 1)[0] if len(lines) > 1 else ""
    return status, body


# ── Header parsing helper ─────────────────────────────────────────────────────

def _extract_header(raw: str, header_name: str) -> str:
    """
    Return the value of the first occurrence of header_name (case-insensitive)
    from the header block of a raw RFC-822 message, or "" if not found.
    """
    pattern = re.compile(
        r"^" + re.escape(header_name) + r"\s*:\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(raw)
    return m.group(1).strip() if m else ""


# ── Internal: connect + authenticate ─────────────────────────────────────────

def _connect_and_auth(username: str, password: str):
    """
    Open a connection through the proxy and log in.
    Returns (socket, None) on success, (None, error_str) on failure.
    Caller is responsible for closing the socket.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect((config.PROXY_IP, config.PROXY_PORT))

    # Announce POP3 route to proxy
    sock.sendall(b"ROUTE:POP3\r\n")
    ready = _recv_line(sock)
    if ready != "READY":
        sock.close()
        return None, f"Proxy not ready: {ready}"

    _recv_line(sock)  # consume +OK banner

    sock.sendall(f"USER {username}\r\n".encode())
    resp = _recv_line(sock)
    if not resp.startswith("+OK"):
        sock.close()
        return None, f"USER rejected: {resp}"

    sock.sendall(f"PASS {password}\r\n".encode())
    resp = _recv_line(sock)
    if resp.startswith("-ERR"):
        sock.close()
        return None, "Authentication failed. Check username/password."

    return sock, None


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_emails(username: str, password: str, folder: str = "inbox"):
    """
    Fetch all emails from the specified folder via proxy → Node 4.

    Parameters
    ----------
    username : str   e.g. "xyz@project.local"
    password : str
    folder   : str   "inbox" (default) or "spam"

    Returns
    -------
    (True,  [{
        "index"       : int,
        "raw"         : str,
        "message_id"  : str,
        "in_reply_to" : str,
    }, …])                on success
    (False, error_str)    on failure
    """
    sock = None
    try:
        sock, err = _connect_and_auth(username, password)
        if err:
            return False, err

        # Switch folder if not the default inbox
        if folder != "inbox":
            sock.sendall(f"XFOLDER {folder}\r\n".encode())
            resp = _recv_line(sock)
            if not resp.startswith("+OK"):
                return False, f"Could not switch to '{folder}': {resp}"

        # STAT – how many messages are in this folder?
        sock.sendall(b"STAT\r\n")
        stat  = _recv_line(sock)          # +OK N total_bytes
        parts = stat.split()
        if len(parts) < 2 or not parts[1].isdigit():
            return False, f"Bad STAT response: {stat}"
        msg_count = int(parts[1])

        # RETR each message
        emails = []
        for i in range(1, msg_count + 1):
            sock.sendall(f"RETR {i}\r\n".encode())
            status, body = _recv_multiline(sock)
            if status.startswith("+OK"):
                emails.append({
                    "index":       i,
                    "raw":         body,
                    "message_id":  _extract_header(body, "Message-ID"),
                    "in_reply_to": _extract_header(body, "In-Reply-To"),
                })

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


def delete_email(username: str, password: str, folder: str, msg_index: int):
    """
    Immediately delete message #msg_index from *folder* on Node 4.

    Uses the extended XDELE command which:
      1. Deletes the file from Node 4's storage immediately.
      2. Notifies Node 3 to delete its own copy of the same file.

    Returns
    -------
    (True,  "Message #N deleted.")  on success
    (False, error_str)              on failure
    """
    sock = None
    try:
        sock, err = _connect_and_auth(username, password)
        if err:
            return False, err

        # Switch to the target folder
        if folder != "inbox":
            sock.sendall(f"XFOLDER {folder}\r\n".encode())
            resp = _recv_line(sock)
            if not resp.startswith("+OK"):
                return False, f"Could not switch to '{folder}': {resp}"

        # XDELE = immediate delete + cross-node notification
        sock.sendall(f"XDELE {msg_index}\r\n".encode())
        resp = _recv_line(sock)
        if not resp.startswith("+OK"):
            return False, f"Delete failed: {resp}"

        sock.sendall(b"QUIT\r\n")
        _recv_line(sock)
        return True, f"Message #{msg_index} deleted."

    except ConnectionRefusedError:
        return False, "Could not connect to proxy. Is Node 2 running?"
    except socket.timeout:
        return False, "Connection timed out."
    except Exception as e:
        return False, str(e)
    finally:
        if sock:
            sock.close()

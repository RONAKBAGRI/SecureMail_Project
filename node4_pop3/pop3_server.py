"""
Node 4 – POP3 Server / MAA (Sunny)

Handles: USER, PASS, STAT, LIST, RETR, DELE, RSET, NOOP, QUIT
On startup also launches:
  • file_receiver  – receives emails pushed from Node 3 (port 4501)
  • registration_server – handles new user signups (port 4502)
"""
import socket
import threading
import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from file_receiver import start_file_receiver
from registration_server import start_registration_server
from user_manager import load_users

logging.basicConfig(
    level=logging.INFO,
    format="[NODE4-POP3][%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

LISTEN_IP = "0.0.0.0"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Client disconnected")
        buf += ch
    return buf.decode("utf-8", errors="replace").rstrip("\r\n")


def _get_inbox_files(username: str) -> list:
    """Return sorted list of .enc filenames in the user's inbox."""
    inbox = os.path.join(config.SHARED_STORAGE_DIR, username, "inbox")
    if not os.path.exists(inbox):
        return []
    return sorted(f for f in os.listdir(inbox) if f.endswith(".enc"))


# ── Per-session handler ───────────────────────────────────────────────────────

def _handle_client(conn: socket.socket, addr):
    users    = load_users()   # fresh credential snapshot for this session
    username = None
    authed   = False
    deleted  = set()          # 1-based indices marked for deletion this session

    try:
        conn.sendall(b"+OK SecureMail POP3 Server Ready\r\n")
        log.info(f"Connection from {addr[0]}")

        while True:
            line  = _recv_line(conn)
            parts = line.split(None, 1)
            if not parts:
                continue
            cmd = parts[0].upper()
            arg = parts[1] if len(parts) > 1 else ""

            # ── Pre-auth ──────────────────────────────────────────
            if cmd == "USER":
                username = arg.strip().lower()
                conn.sendall(b"+OK Send PASS\r\n")

            elif cmd == "PASS":
                if username and users.get(username) == arg.strip():
                    authed = True
                    conn.sendall(b"+OK Logged in\r\n")
                    log.info(f"Authenticated: {username}")
                else:
                    conn.sendall(b"-ERR Authentication failed\r\n")
                    log.warning(f"Auth failed for: {username}")
                    username = None

            elif cmd == "QUIT":
                # Apply pending deletions before closing
                if authed and deleted:
                    files = _get_inbox_files(username)
                    inbox = os.path.join(config.SHARED_STORAGE_DIR, username, "inbox")
                    for idx in sorted(deleted, reverse=True):
                        if 1 <= idx <= len(files):
                            path = os.path.join(inbox, files[idx - 1])
                            try:
                                os.remove(path)
                                meta = path.replace(".enc", ".meta")
                                if os.path.exists(meta):
                                    os.remove(meta)
                                log.info(f"Deleted message #{idx}")
                            except OSError as e:
                                log.error(f"Could not delete #{idx}: {e}")
                conn.sendall(b"+OK Bye\r\n")
                break

            # ── Auth-gated ────────────────────────────────────────
            elif not authed:
                conn.sendall(b"-ERR Not authenticated\r\n")

            elif cmd == "STAT":
                files  = _get_inbox_files(username)
                active = [f for i, f in enumerate(files, 1) if i not in deleted]
                inbox  = os.path.join(config.SHARED_STORAGE_DIR, username, "inbox")
                total  = sum(
                    os.path.getsize(os.path.join(inbox, f)) for f in active
                )
                conn.sendall(f"+OK {len(active)} {total}\r\n".encode())

            elif cmd == "LIST":
                files = _get_inbox_files(username)
                inbox = os.path.join(config.SHARED_STORAGE_DIR, username, "inbox")
                if arg:
                    try:
                        idx = int(arg)
                    except ValueError:
                        conn.sendall(b"-ERR Invalid message number\r\n")
                        continue
                    if idx in deleted or idx < 1 or idx > len(files):
                        conn.sendall(b"-ERR No such message\r\n")
                    else:
                        sz = os.path.getsize(os.path.join(inbox, files[idx - 1]))
                        conn.sendall(f"+OK {idx} {sz}\r\n".encode())
                else:
                    active = [(i, f) for i, f in enumerate(files, 1) if i not in deleted]
                    lines  = [f"+OK {len(active)} messages"]
                    for i, f in active:
                        sz = os.path.getsize(os.path.join(inbox, f))
                        lines.append(f"{i} {sz}")
                    conn.sendall(("\r\n".join(lines) + "\r\n.\r\n").encode())

            elif cmd == "RETR":
                files = _get_inbox_files(username)
                try:
                    idx = int(arg)
                except ValueError:
                    conn.sendall(b"-ERR Invalid message number\r\n")
                    continue
                if idx in deleted or idx < 1 or idx > len(files):
                    conn.sendall(b"-ERR No such message\r\n")
                else:
                    inbox    = os.path.join(config.SHARED_STORAGE_DIR, username, "inbox")
                    filepath = os.path.join(inbox, files[idx - 1])
                    with open(filepath, "r", encoding="utf-8") as f:
                        body = f.read()
                    size = os.path.getsize(filepath)
                    conn.sendall(f"+OK {size} octets\r\n".encode())
                    conn.sendall(body.encode("utf-8") + b"\r\n.\r\n")
                    log.info(f"RETR #{idx} → {files[idx - 1]} ({size} B)")

            elif cmd == "DELE":
                files = _get_inbox_files(username)
                try:
                    idx = int(arg)
                except ValueError:
                    conn.sendall(b"-ERR Invalid message number\r\n")
                    continue
                if idx < 1 or idx > len(files) or idx in deleted:
                    conn.sendall(b"-ERR No such message\r\n")
                else:
                    deleted.add(idx)
                    conn.sendall(f"+OK Message #{idx} marked for deletion\r\n".encode())

            elif cmd == "RSET":
                deleted.clear()
                conn.sendall(b"+OK Deleted messages restored\r\n")

            elif cmd == "NOOP":
                conn.sendall(b"+OK\r\n")

            else:
                conn.sendall(b"-ERR Command not recognized\r\n")

    except ConnectionError as e:
        log.warning(f"Client {addr[0]} disconnected: {e}")
    except Exception as e:
        log.error(f"Error handling {addr}: {e}", exc_info=True)
    finally:
        conn.close()
        log.info(f"Session closed for {addr[0]}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    start_file_receiver()         # port 4501 — receives emails from Node 3
    start_registration_server()   # port 4502 — handles new user signups

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_IP, config.POP3_PORT))
    srv.listen(10)
    log.info(f"POP3 Server listening on {LISTEN_IP}:{config.POP3_PORT}")

    try:
        while True:
            conn, addr = srv.accept()
            conn.settimeout(60)
            threading.Thread(
                target=_handle_client,
                args=(conn, addr),
                daemon=True
            ).start()
    except KeyboardInterrupt:
        log.info("POP3 Server shutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()

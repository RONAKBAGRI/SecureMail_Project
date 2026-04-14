"""
Node 4 – POP3 Server / MAA (Sunny)
=====================================
Handles: USER, PASS, STAT, LIST, RETR, DELE, RSET, NOOP, QUIT
Extended: XFOLDER <folder>   – switch active folder (inbox / spam)
          XDELE <n>          – immediately delete message #n from active
                               folder AND notify Node 3 to delete its copy

On startup also launches:
  • file_receiver       – receives emails pushed from Node 3 (port 4501)
  • registration_server – handles new user signups         (port 4502)
"""

import socket
import threading
import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from file_receiver        import start_file_receiver
from registration_server  import start_registration_server
from user_manager         import load_users

logging.basicConfig(
    level=logging.INFO,
    format="[NODE4-POP3][%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

LISTEN_IP       = "0.0.0.0"
VALID_FOLDERS   = {"inbox", "spam"}


# ── Socket helpers ────────────────────────────────────────────────────────────

def _recv_line(sock: socket.socket) -> str:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Client disconnected")
        buf += ch
    return buf.decode("utf-8", errors="replace").rstrip("\r\n")


# ── Storage helpers ───────────────────────────────────────────────────────────

def _get_folder_files(username: str, folder: str) -> list:
    """Return sorted list of .enc filenames in the user's folder."""
    path = os.path.join(config.SHARED_STORAGE_DIR, username, folder)
    if not os.path.exists(path):
        return []
    return sorted(f for f in os.listdir(path) if f.endswith(".enc"))


def _delete_file(username: str, folder: str, filename: str) -> None:
    """Delete .enc and companion .meta file from Node 4 storage."""
    base = os.path.join(config.SHARED_STORAGE_DIR, username, folder, filename)
    for path in (base, base.replace(".enc", ".meta")):
        try:
            if os.path.exists(path):
                os.remove(path)
                log.info(f"[DELETE] Removed {path}")
        except OSError as e:
            log.error(f"[DELETE] Could not remove {path}: {e}")


# ── Node 3 deletion notification ──────────────────────────────────────────────

def _notify_node3_delete(username: str, folder: str, filename: str) -> bool:
    """
    Tell Node 3 to delete its local copy of this email.
    Connects directly to Node 3 on DELETE_PORT (4503).
    Returns True if Node 3 acknowledged, False otherwise (non-fatal).
    """
    payload = json.dumps({
        "username": username,
        "folder":   folder,
        "filename": filename,
    }).encode("utf-8")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((config.SMTP_IP, config.DELETE_PORT))
        sock.sendall(len(payload).to_bytes(4, "big") + payload)
        ack = sock.recv(8).strip()
        sock.close()
        if ack == b"ACK":
            log.info(f"[DELETE] Node 3 confirmed deletion of {filename}")
            return True
        else:
            log.warning(f"[DELETE] Node 3 gave unexpected ack: {ack!r}")
            return False
    except ConnectionRefusedError:
        log.warning("[DELETE] Node 3 delete server unreachable — file may remain on Node 3.")
        return False
    except socket.timeout:
        log.warning("[DELETE] Timed out notifying Node 3.")
        return False
    except Exception as e:
        log.warning(f"[DELETE] Could not notify Node 3: {e}")
        return False


# ── Per-session handler ───────────────────────────────────────────────────────

def _handle_client(conn: socket.socket, addr):
    users         = load_users()   # fresh credential snapshot for this session
    username      = None
    authed        = False
    active_folder = "inbox"        # default folder; changed by XFOLDER
    deleted       = set()          # 1-based indices marked for standard DELE

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

            # ── Pre-auth commands ──────────────────────────────────────────────
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
                # Apply pending standard DELE deletions before closing
                if authed and deleted:
                    files = _get_folder_files(username, active_folder)
                    for idx in sorted(deleted, reverse=True):
                        if 1 <= idx <= len(files):
                            fname = files[idx - 1]
                            _delete_file(username, active_folder, fname)
                            _notify_node3_delete(username, active_folder, fname)
                conn.sendall(b"+OK Bye\r\n")
                break

            # ── Require authentication for all commands below ──────────────────
            elif not authed:
                conn.sendall(b"-ERR Not authenticated\r\n")

            # ── XFOLDER: switch active folder  (NEW) ──────────────────────────
            elif cmd == "XFOLDER":
                requested = arg.strip().lower()
                if requested not in VALID_FOLDERS:
                    conn.sendall(
                        f"-ERR Unknown folder '{requested}'. "
                        f"Valid: {', '.join(VALID_FOLDERS)}\r\n".encode()
                    )
                else:
                    active_folder = requested
                    deleted.clear()    # reset deletion marks when folder changes
                    count = len(_get_folder_files(username, active_folder))
                    conn.sendall(
                        f"+OK Switched to {active_folder} "
                        f"({count} message(s))\r\n".encode()
                    )
                    log.info(f"[{username}] XFOLDER → {active_folder}")

            # ── XDELE: immediate delete + Node 3 notification  (NEW) ──────────
            elif cmd == "XDELE":
                files = _get_folder_files(username, active_folder)
                try:
                    idx = int(arg)
                except ValueError:
                    conn.sendall(b"-ERR Invalid message number\r\n")
                    continue

                if idx < 1 or idx > len(files):
                    conn.sendall(b"-ERR No such message\r\n")
                    continue

                fname = files[idx - 1]
                _delete_file(username, active_folder, fname)
                _notify_node3_delete(username, active_folder, fname)
                conn.sendall(
                    f"+OK Message #{idx} ({fname}) permanently deleted\r\n"
                    .encode()
                )
                log.info(f"[{username}] XDELE #{idx} ({fname}) from {active_folder}")

            # ── STAT ───────────────────────────────────────────────────────────
            elif cmd == "STAT":
                files  = _get_folder_files(username, active_folder)
                active = [f for i, f in enumerate(files, 1) if i not in deleted]
                folder_path = os.path.join(
                    config.SHARED_STORAGE_DIR, username, active_folder
                )
                total = sum(
                    os.path.getsize(os.path.join(folder_path, f)) for f in active
                )
                conn.sendall(f"+OK {len(active)} {total}\r\n".encode())

            # ── LIST ───────────────────────────────────────────────────────────
            elif cmd == "LIST":
                files       = _get_folder_files(username, active_folder)
                folder_path = os.path.join(
                    config.SHARED_STORAGE_DIR, username, active_folder
                )
                if arg:
                    try:
                        idx = int(arg)
                    except ValueError:
                        conn.sendall(b"-ERR Invalid message number\r\n")
                        continue
                    if idx in deleted or idx < 1 or idx > len(files):
                        conn.sendall(b"-ERR No such message\r\n")
                    else:
                        sz = os.path.getsize(os.path.join(folder_path, files[idx - 1]))
                        conn.sendall(f"+OK {idx} {sz}\r\n".encode())
                else:
                    active = [(i, f) for i, f in enumerate(files, 1) if i not in deleted]
                    lines  = [f"+OK {len(active)} messages"]
                    for i, f in active:
                        sz = os.path.getsize(os.path.join(folder_path, f))
                        lines.append(f"{i} {sz}")
                    conn.sendall(("\r\n".join(lines) + "\r\n.\r\n").encode())

            # ── RETR ───────────────────────────────────────────────────────────
            elif cmd == "RETR":
                files = _get_folder_files(username, active_folder)
                try:
                    idx = int(arg)
                except ValueError:
                    conn.sendall(b"-ERR Invalid message number\r\n")
                    continue
                if idx in deleted or idx < 1 or idx > len(files):
                    conn.sendall(b"-ERR No such message\r\n")
                else:
                    folder_path = os.path.join(
                        config.SHARED_STORAGE_DIR, username, active_folder
                    )
                    filepath = os.path.join(folder_path, files[idx - 1])
                    with open(filepath, "r", encoding="utf-8") as fh:
                        body = fh.read()
                    size = os.path.getsize(filepath)
                    conn.sendall(f"+OK {size} octets\r\n".encode())
                    conn.sendall(body.encode("utf-8") + b"\r\n.\r\n")
                    log.info(f"RETR #{idx} from {active_folder} → {files[idx - 1]} ({size} B)")

            # ── DELE (standard: marks for deletion at QUIT) ────────────────────
            elif cmd == "DELE":
                files = _get_folder_files(username, active_folder)
                try:
                    idx = int(arg)
                except ValueError:
                    conn.sendall(b"-ERR Invalid message number\r\n")
                    continue
                if idx < 1 or idx > len(files) or idx in deleted:
                    conn.sendall(b"-ERR No such message\r\n")
                else:
                    deleted.add(idx)
                    conn.sendall(
                        f"+OK Message #{idx} marked for deletion\r\n".encode()
                    )

            # ── RSET ───────────────────────────────────────────────────────────
            elif cmd == "RSET":
                deleted.clear()
                conn.sendall(b"+OK Deleted messages restored\r\n")

            # ── NOOP ───────────────────────────────────────────────────────────
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

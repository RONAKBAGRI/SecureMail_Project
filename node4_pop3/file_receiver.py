"""
Node 4 – File Receiver (Sunny)
Listens on FILE_TRANSFER_PORT for emails pushed immediately by Node 3.
Each incoming push is a length-prefixed JSON payload containing the
email content and metadata. Saves .enc and .meta to local storage.
Started as a background daemon thread by pop3_server.py.
"""
import socket
import threading
import json
import os
import logging
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

log = logging.getLogger(__name__)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes — keeps reading until full or socket closes."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes received")
        buf += chunk
    return buf


def _handle_push(conn: socket.socket, addr):
    try:
        # Read 4-byte big-endian length prefix
        raw_len = _recv_exact(conn, 4)
        length  = int.from_bytes(raw_len, "big")

        if length > 50 * 1024 * 1024:
            log.error(f"[RECEIVER] Payload too large ({length} bytes) from {addr[0]}; rejecting.")
            conn.sendall(b"ERR")
            return

        raw_payload = _recv_exact(conn, length)
        data        = json.loads(raw_payload.decode("utf-8"))

        recipient = data["recipient"]
        folder    = data["folder"]      # "inbox" or "spam"
        filename  = data["filename"]    # e.g. "1711902000123.enc"
        content   = data["content"]
        meta      = data.get("meta", {})

        # Save .enc file
        save_dir  = os.path.join(config.SHARED_STORAGE_DIR, recipient, folder)
        os.makedirs(save_dir, exist_ok=True)

        enc_path  = os.path.join(save_dir, filename)
        meta_path = enc_path.replace(".enc", ".meta")

        with open(enc_path, "w", encoding="utf-8") as f:
            f.write(content)

        if meta:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

        conn.sendall(b"ACK")
        log.info(f"[RECEIVER] Saved → {enc_path}")

    except json.JSONDecodeError as e:
        log.error(f"[RECEIVER] Malformed JSON from {addr[0]}: {e}")
        try:
            conn.sendall(b"ERR")
        except Exception:
            pass
    except Exception as e:
        log.error(f"[RECEIVER] Error from {addr[0]}: {e}", exc_info=True)
        try:
            conn.sendall(b"ERR")
        except Exception:
            pass
    finally:
        conn.close()


def start_file_receiver():
    """Bind on FILE_TRANSFER_PORT and spawn a daemon thread per push."""
    def _serve():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", config.FILE_TRANSFER_PORT))
        srv.listen(20)
        log.info(f"[RECEIVER] Listening on port {config.FILE_TRANSFER_PORT}")
        while True:
            conn, addr = srv.accept()
            conn.settimeout(15)
            threading.Thread(target=_handle_push, args=(conn, addr), daemon=True).start()

    threading.Thread(target=_serve, daemon=True, name="FileReceiver").start()
    log.info("[RECEIVER] File receiver thread started.")

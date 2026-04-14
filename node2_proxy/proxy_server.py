"""
Node 2 – Proxy Server (Ronak)

Routes:
  ROUTE:SMTP     → Node 3 port 2525  (with body encryption)
  ROUTE:POP3     → Node 4 port 1100  (with body decryption)
  ROUTE:REGISTER → Node 4 port 4502  (plain passthrough)
"""
import socket
import threading
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from crypto import encrypt_data, decrypt_data
from security_manager import is_ip_allowed
from udp_client_helper import check_spam_score 

logging.basicConfig(
    level=logging.INFO,
    format="[NODE2-PROXY][%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

LISTEN_IP  = config.PROXY_IP
BUFFER    = 4096
MAX_BODY  = 10 * 1024 * 1024


# ── Socket helpers ────────────────────────────────────────────────────────────

def _recv_line(sock: socket.socket) -> bytes:
    buf = b""
    while not buf.endswith(b"\r\n"):
        ch = sock.recv(1)
        if not ch:
            raise ConnectionError("Socket closed")
        buf += ch
    return buf


def _recv_until(sock: socket.socket, terminator: bytes, max_size: int = MAX_BODY) -> bytes:
    buf = b""
    while not buf.endswith(terminator):
        chunk = sock.recv(BUFFER)
        if not chunk:
            raise ConnectionError("Socket closed mid-stream")
        buf += chunk
        if len(buf) > max_size:
            raise OverflowError("Payload too large")
    return buf


# ── Protocol handlers ─────────────────────────────────────────────────────────

def _proxy_smtp(client: socket.socket, server: socket.socket):
    """Forward SMTP, encrypting the email body before it reaches Node 3."""
    try:
        client.sendall(_recv_line(server))   # forward 220 banner

        while True:
            line       = _recv_line(client)
            first_word = line.decode("utf-8", errors="replace").strip().upper().split()
            cmd        = first_word[0] if first_word else ""

            if cmd in ("HELO", "EHLO", "MAIL", "RCPT", "NOOP", "RSET"):
                server.sendall(line)
                client.sendall(_recv_line(server))

            # ── AFTER (fixed code) ────────────────────────────────────────────────────
            elif cmd == "DATA":
                server.sendall(line)
                resp = _recv_line(server)
                client.sendall(resp)
                if resp.decode().startswith("354"):
                    raw_body = _recv_until(client, b"\r\n.\r\n")
                    plaintext = raw_body[:-5].decode("utf-8", errors="replace")

                    # ── SPAM CHECK ON PLAINTEXT (before any encryption) ──────────────
                    is_spam = check_spam_score(plaintext)
                    spam_flag = b"SPAM:YES\r\n" if is_spam else b"SPAM:NO\r\n"
                    log.info(f"Spam check on plaintext → is_spam={is_spam}")
                    # ─────────────────────────────────────────────────────────────────

                    ciphertext = encrypt_data(plaintext)

                    # Prepend spam flag as first line, then ciphertext, then terminator
                    server.sendall(spam_flag + ciphertext.encode() + b"\r\n.\r\n")
                    log.info("Email body encrypted → SMTP server.")
                    client.sendall(_recv_line(server))

            elif cmd == "QUIT":
                server.sendall(line)
                try:
                    client.sendall(_recv_line(server))
                except ConnectionError:
                    pass
                break

            else:
                server.sendall(line)
                try:
                    client.sendall(_recv_line(server))
                except ConnectionError:
                    break

    except ConnectionError as e:
        log.debug(f"SMTP proxy ended: {e}")


def _proxy_pop3(client: socket.socket, server: socket.socket):
    """Forward POP3, decrypting email bodies before they reach the client."""
    try:
        client.sendall(_recv_line(server))   # forward +OK banner

        while True:
            line  = _recv_line(client)
            parts = line.decode("utf-8", errors="replace").strip().upper().split()
            cmd   = parts[0] if parts else ""

            if cmd in ("USER", "PASS", "STAT", "DELE", "NOOP", "RSET"):
                server.sendall(line)
                client.sendall(_recv_line(server))

            elif cmd == "RETR":
                server.sendall(line)
                raw = _recv_until(server, b"\r\n.\r\n")
                if raw.startswith(b"+OK"):
                    header_end     = raw.index(b"\r\n") + 2
                    status_line    = raw[:header_end]
                    encrypted_body = raw[header_end:-5].decode("utf-8", errors="replace")
                    plaintext      = decrypt_data(encrypted_body)
                    client.sendall(status_line + plaintext.encode("utf-8") + b"\r\n.\r\n")
                    log.info("Email body decrypted → client.")
                else:
                    client.sendall(raw)

            elif cmd == "LIST":
                server.sendall(line)
                if len(parts) > 1:
                    client.sendall(_recv_line(server))
                else:
                    client.sendall(_recv_until(server, b"\r\n.\r\n"))

            elif cmd == "QUIT":
                server.sendall(line)
                try:
                    client.sendall(_recv_line(server))
                except ConnectionError:
                    pass
                break

            else:
                server.sendall(line)
                try:
                    client.sendall(_recv_line(server))
                except ConnectionError:
                    break

    except ConnectionError as e:
        log.debug(f"POP3 proxy ended: {e}")


def _proxy_register(client: socket.socket, server: socket.socket):
    """
    Single round-trip passthrough for user registration.
    Client sends one REGISTER line, server responds with +OK or -ERR.
    No encryption needed.
    """
    try:
        line = _recv_line(client)    # REGISTER <email> <password>\r\n
        server.sendall(line)
        resp = _recv_line(server)    # +OK … or -ERR …
        client.sendall(resp)
    except ConnectionError as e:
        log.debug(f"REGISTER proxy ended: {e}")


# ── Connection dispatcher ─────────────────────────────────────────────────────

def _handle_connection(client_sock: socket.socket, addr):
    server_sock = None
    try:
        if not is_ip_allowed(addr[0]):
            client_sock.sendall(b"550 Access denied.\r\n")
            return

        route = _recv_line(client_sock).decode("utf-8", errors="replace").strip()
        log.info(f"Connection from {addr[0]} | Route: {route}")

        if route == "ROUTE:SMTP":
            target  = (config.SMTP_IP, config.SMTP_PORT)
            handler = _proxy_smtp
        elif route == "ROUTE:POP3":
            target  = (config.POP3_IP, config.POP3_PORT)
            handler = _proxy_pop3
        elif route == "ROUTE:REGISTER":
            target  = (config.POP3_IP, config.REGISTRATION_PORT)
            handler = _proxy_register
        else:
            log.warning(f"Unknown route from {addr[0]}: {route!r}")
            client_sock.sendall(b"500 Unknown route.\r\n")
            return

        client_sock.sendall(b"READY\r\n")

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.settimeout(30)
        server_sock.connect(target)
        log.info(f"Tunnel {addr[0]} → {target[0]}:{target[1]}")

        handler(client_sock, server_sock)

    except ConnectionRefusedError as e:
        log.error(f"Backend unreachable: {e}")
    except Exception as e:
        log.error(f"Error for {addr}: {e}", exc_info=True)
    finally:
        if server_sock:
            server_sock.close()
        client_sock.close()
        log.info(f"Connection from {addr[0]} closed.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_IP, config.PROXY_PORT))
    srv.listen(20)
    log.info(f"Proxy listening on {LISTEN_IP}:{config.PROXY_PORT}")
    log.info(f"  SMTP     → {config.SMTP_IP}:{config.SMTP_PORT}")
    log.info(f"  POP3     → {config.POP3_IP}:{config.POP3_PORT}")
    log.info(f"  REGISTER → {config.POP3_IP}:{config.REGISTRATION_PORT}")

    try:
        while True:
            client, addr = srv.accept()
            client.settimeout(30)
            threading.Thread(
                target=_handle_connection,
                args=(client, addr),
                daemon=True
            ).start()
    except KeyboardInterrupt:
        log.info("Proxy shutting down.")
    finally:
        srv.close()


if __name__ == "__main__":
    main()
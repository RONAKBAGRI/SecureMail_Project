import socket
import threading
import os
import time
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# Import your helper functions
from udp_client_helper import verify_user, check_spam
from receipt_manager import generate_read_receipt

def handle_client(conn, addr):
    print(f"[+] Proxy connected from {addr}")
    conn.send(b"220 projectmail.local SMTP Service Ready\r\n")
    
    # Session state variables
    sender = ""
    recipient = ""
    recipient_username = ""
    is_data_mode = False
    email_payload = []
    
    try:
        while True:
            if is_data_mode:
                # In DATA mode, read chunks until we see the termination sequence: \r\n.\r\n
                chunk = conn.recv(4096).decode('utf-8', errors='ignore')
                if not chunk: break
                
                email_payload.append(chunk)
                full_data = "".join(email_payload)
                
                if "\r\n.\r\n" in full_data:
                    # End of email payload detected
                    email_body = full_data.split("\r\n.\r\n")[0]
                    
                    # 1. Ask Amit if it's spam
                    is_spam = check_spam(email_body)
                    folder = "spam" if is_spam else "inbox"
                    
                    # 2. Save the file
                    user_dir = os.path.join(config.STORAGE_DIR, recipient_username, folder)
                    os.makedirs(user_dir, exist_ok=True)
                    
                    filename = f"mail_{int(time.time())}.txt"
                    filepath = os.path.join(user_dir, filename)
                    
                    with open(filepath, 'w') as f:
                        f.write(email_body)
                        
                    print(f"[+] Email saved to {filepath}")
                    conn.send(b"250 Message accepted for delivery\r\n")
                    
                    # Reset state for the next email in this session
                    is_data_mode = False
                    email_payload = []
            else:
                # Normal command mode
                line = conn.recv(1024).decode('utf-8').strip()
                if not line: break
                
                print(f" [Client] {line}")
                cmd = line[:4].upper()
                
                if cmd in ["EHLO", "HELO"]:
                    conn.send(b"250 Hello\r\n")
                    
                elif cmd == "MAIL": # MAIL FROM:<sender>
                    sender = line.split("<")[1].split(">")[0] if "<" in line else line.split(":")[1].strip()
                    conn.send(b"250 OK\r\n")
                    
                elif cmd == "RCPT": # RCPT TO:<receiver>
                    recipient = line.split("<")[1].split(">")[0] if "<" in line else line.split(":")[1].strip()
                    
                    # Ask Amit if user exists via UDP
                    if verify_user(recipient):
                        recipient_username = recipient.split("@")[0]
                        conn.send(b"250 OK\r\n")
                    else:
                        conn.send(b"550 No such user here\r\n")
                        
                elif cmd == "DATA":
                    conn.send(b"354 Start mail input; end with <CRLF>.<CRLF>\r\n")
                    is_data_mode = True
                    
                elif cmd == "NOTI": 
                    # Custom Command: NOTIFY_READ sender@mail.com receiver@mail.com
                    # Sunny's POP3 server will hit this when an email is fetched.
                    parts = line.split()
                    if len(parts) == 3:
                        generate_read_receipt(sender_email=parts[1], receiver_email=parts[2])
                        conn.send(b"250 Read receipt queued\r\n")
                    else:
                        conn.send(b"500 Syntax error in NOTIFY command\r\n")
                        
                elif cmd == "QUIT":
                    conn.send(b"221 projectmail.local Service closing transmission channel\r\n")
                    break
                    
                else:
                    conn.send(b"500 Command unrecognized\r\n")
                    
    except Exception as e:
        print(f"[!] Connection error: {e}")
    finally:
        conn.close()
        print(f"[-] Connection closed with {addr}")

def start_smtp():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Allow port reuse so you don't get "Address already in use" errors during rapid testing
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
    server.bind((config.SMTP_IP, config.SMTP_PORT))
    server.listen(5)
    
    print(f"[*] Gaurav's SMTP Server listening on {config.SMTP_IP}:{config.SMTP_PORT}")
    
    while True:
        client_conn, addr = server.accept()
        # Handle each incoming email in a new thread so the server doesn't freeze
        client_thread = threading.Thread(target=handle_client, args=(client_conn, addr))
        client_thread.start()

if __name__ == "__main__":
    start_smtp()
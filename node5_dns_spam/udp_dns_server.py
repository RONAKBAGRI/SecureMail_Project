import socket
import json
import os
import sys
from datetime import datetime

# Add parent directory to path so we can import config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from spam_filter import check_spam

def load_users():
    users_file = os.path.join(os.path.dirname(__file__), 'valid_users.json')
    try:
        with open(users_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("[!] Warning: valid_users.json not found!")
        return []

def log_spam(email_body, score):
    log_file = os.path.join(os.path.dirname(__file__), 'spam_log.txt')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Clean up the snippet so it prints nicely on one line
    snippet = email_body[:40].replace('\n', ' ') 
    
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] SPAM CAUGHT | Score: {score} | Snippet: '{snippet}...'\n")

def start_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((config.UDP_DNS_IP, config.UDP_DNS_PORT))
    print(f"[*] Amit's UDP Server (DNS & Spam) running on {config.UDP_DNS_IP}:{config.UDP_DNS_PORT}")

    valid_users = load_users()

    while True:
        data, addr = sock.recvfrom(4096)
        message = data.decode('utf-8')

        # --- TASK 1: USER DIRECTORY LOOKUP ---
        if message.startswith("VERIFY:"):
            email_to_check = message.split("VERIFY:")[1].strip()
            if email_to_check in valid_users:
                sock.sendto(b"VALID", addr)
                print(f"[+] Directory Check: {email_to_check} -> VALID")
            else:
                sock.sendto(b"INVALID", addr)
                print(f"[-] Directory Check: {email_to_check} -> INVALID")

        # --- TASK 2: SPAM CHECKING ---
        elif message.startswith("SPAM_CHECK:"):
            email_body = message.split("SPAM_CHECK:")[1].strip()
            is_spam, score = check_spam(email_body)

            if is_spam:
                log_spam(email_body, score)
                response = f"SPAM:{score}"
                print(f"[!] Spam Blocked (Score: {score})")
            else:
                response = f"CLEAN:{score}"
                print(f"[+] Message Clean (Score: {score})")

            sock.sendto(response.encode('utf-8'), addr)

if __name__ == "__main__":
    start_server()
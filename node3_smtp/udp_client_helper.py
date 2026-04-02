import socket
import sys
import os

# Ensure we can read config.py from the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def ask_amit(message):
    """Sends a UDP packet to Node 5 and waits for a response."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(3.0) # Don't hang forever if Amit's server is down
        sock.sendto(message.encode('utf-8'), (config.UDP_DNS_IP, config.UDP_DNS_PORT))
        
        data, _ = sock.recvfrom(1024)
        return data.decode('utf-8')
    except socket.timeout:
        print("[!] Timeout: Amit's UDP server did not respond.")
        return "ERROR_TIMEOUT"
    except Exception as e:
        print(f"[!] UDP Error: {e}")
        return "ERROR"

def verify_user(email_address):
    """Asks Node 5 if the recipient exists."""
    print(f"[*] Verifying user {email_address} with Node 5...")
    response = ask_amit(f"VERIFY:{email_address}")
    
    # Assuming Amit replies with "VALID" or "INVALID"
    if "VALID" in response.upper() and "INVALID" not in response.upper():
        return True
    return False

def check_spam(email_body):
    """Sends a snippet of the email body to Node 5 for spam scoring."""
    print("[*] Sending payload to Node 5 for Spam Check...")
    # Send only the first 500 characters to avoid massive UDP packets
    snippet = email_body[:500] 
    response = ask_amit(f"SPAM_CHECK:{snippet}")
    
    # Assuming Amit replies with something like "SPAM:85" or "CLEAN:10"
    if "SPAM" in response.upper():
        print(f"[!] Spam detected by Node 5: {response}")
        return True
    
    print("[*] Payload marked as CLEAN.")
    return False
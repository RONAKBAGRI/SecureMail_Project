import os
import time
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def generate_read_receipt(sender_email, receiver_email):
    """
    Generates an automated system email notifying the sender 
    that their message was read.
    """
    print(f"[*] Generating Read Receipt for {sender_email}...")
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    receipt_body = (
        f"Subject: Read Receipt: Your email to {receiver_email}\n"
        f"From: system@projectmail.local\n"
        f"To: {sender_email}\n"
        f"X-System-Automated: yes\n\n"
        f"This is an automated notification.\n"
        f"Your email to {receiver_email} was successfully opened and read on {timestamp}."
    )
    
    # Extract the username (e.g., "prashant" from "prashant@projectmail.local")
    username = sender_email.split('@')[0]
    
    # Define where this receipt gets saved
    user_inbox_dir = os.path.join(config.STORAGE_DIR, username, "inbox")
    
    # Ensure the directory exists
    os.makedirs(user_inbox_dir, exist_ok=True)
    
    filename = f"receipt_{int(time.time())}.txt"
    filepath = os.path.join(user_inbox_dir, filename)
    
    try:
        with open(filepath, 'w') as f:
            f.write(receipt_body)
        print(f"[+] Read receipt successfully placed in {username}'s inbox.")
        return True
    except Exception as e:
        print(f"[!] Failed to write read receipt: {e}")
        return False
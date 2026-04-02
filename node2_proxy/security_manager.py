import os

def is_sender_allowed(sender_email):
    """
    Checks if an email is in the blacklist. 
    Returns True if allowed, False if blocked.
    """
    # Clean up the email string (removes whitespace and < > brackets common in SMTP)
    clean_email = sender_email.strip("<> \r\n")
    
    blacklist_path = os.path.join(os.path.dirname(__file__), "blacklist.txt")
    
    if os.path.exists(blacklist_path):
        with open(blacklist_path, "r") as f:
            # Read non-empty lines
            blacklisted_emails = [line.strip() for line in f.readlines() if line.strip()]
            
            if clean_email in blacklisted_emails:
                print(f"[SECURITY ALERT] Dropped connection from blacklisted sender: {clean_email}")
                return False
                
    return True
from cryptography.fernet import Fernet
import os

KEY_FILE = os.path.join(os.path.dirname(__file__), "secret.key")

def load_or_generate_key():
    """Generates a secure key if it doesn't exist, otherwise loads it."""
    if not os.path.exists(KEY_FILE):
        print("[*] Generating new encryption key...")
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
    else:
        with open(KEY_FILE, "rb") as key_file:
            key = key_file.read()
    return key

# Initialize the cipher globally so it's ready to use
cipher = Fernet(load_or_generate_key())

def encrypt_payload(text):
    """Takes a plain text string and returns an encrypted string."""
    try:
        encrypted_bytes = cipher.encrypt(text.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"[!] Encryption Error: {e}")
        return text

def decrypt_payload(encrypted_text):
    """Takes an encrypted string and returns the plain text."""
    try:
        decrypted_bytes = cipher.decrypt(encrypted_text.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        print(f"[!] Decryption Error: {e}")
        return encrypted_text
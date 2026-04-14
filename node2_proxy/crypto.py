"""
Fernet (AES-128-CBC + HMAC-SHA256) encryption module.
The secret key is generated once and stored in secret.key.
All nodes that need to encrypt/decrypt must share this file.
"""
import os
import logging
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)
KEY_FILE = os.path.join(os.path.dirname(__file__), "secret.key")


def _load_or_create_key() -> bytes:
    if not os.path.exists(KEY_FILE):
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        log.info(f"[CRYPTO] New encryption key generated: {KEY_FILE}")
    with open(KEY_FILE, "rb") as f:
        return f.read()


_cipher = Fernet(_load_or_create_key())


def encrypt_data(plaintext: str) -> str:
    """Encrypt a UTF-8 string; returns a URL-safe base64 token string."""
    return _cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_data(token: str) -> str:
    """Decrypt a Fernet token string; returns plaintext or original on failure."""
    try:
        return _cipher.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        log.warning(f"[CRYPTO] Decryption failed ({e}); returning raw data.")
        return token  # Graceful fallback
    

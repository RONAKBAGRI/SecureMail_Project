
import json
import os
import datetime
import logging

log = logging.getLogger(__name__)


def generate_receipt(email_filepath: str, sender: str, recipient: str, is_spam: bool = False):
    """
    Write a .meta file next to the .enc email file.
    Fields: sender, recipient, timestamp, status, spam.
    """
    meta_path = email_filepath.replace(".enc", ".meta")
    data = {
        "sender":    sender,
        "recipient": recipient,
        "timestamp": datetime.datetime.now().isoformat(),
        "status":    "Quarantined" if is_spam else "Delivered",
        "spam":      is_spam,
    }
    try:
        with open(meta_path, "w") as f:
            json.dump(data, f, indent=2)
        log.debug(f"Receipt written: {meta_path}")
    except OSError as e:
        log.error(f"Could not write receipt: {e}")
"""Keyword-based spam classifier with logging."""
import os
import datetime
import logging

log = logging.getLogger(__name__)

KEYWORDS_FILE = os.path.join(os.path.dirname(__file__), "spam_keywords.txt")
SPAM_LOG_FILE = os.path.join(os.path.dirname(__file__), "spam_log.txt")


def _load_keywords() -> list[str]:
    if not os.path.exists(KEYWORDS_FILE):
        return []
    with open(KEYWORDS_FILE, "r") as f:
        return [line.strip().lower() for line in f if line.strip()]


def is_spam(content: str) -> bool:
    """
    Returns True if the content contains any spam keywords.
    Logs detections to spam_log.txt.
    """
    keywords = _load_keywords()
    content_lower = content.lower()

    hits = [kw for kw in keywords if kw in content_lower]
    if hits:
        entry = (
            f"[{datetime.datetime.now().isoformat()}] "
            f"SPAM DETECTED – Keywords: {', '.join(hits)}\n"
        )
        try:
            with open(SPAM_LOG_FILE, "a") as logf:
                logf.write(entry)
        except OSError as e:
            log.error(f"Could not write spam log: {e}")
        log.warning(f"Spam detected. Keywords matched: {hits}")
        return True

    return False
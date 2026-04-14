"""
Node 1 – Local Email Cache (Prashant)
======================================
Persists fetched AND sent emails to disk so users can view their mail
even when offline.  Cache is strictly separated by username.

Storage layout:
  .mail_cache/
    <md5(username)>/
      inbox.json      ← list of {index, raw, …} dicts
      spam.json       ← list of {index, raw, …} dicts
      sent.json       ← list of sent-mail dicts (append-only)

Usage:
  from local_cache import (
      save_cache, load_cache, delete_from_cache, clear_cache,
      append_sent, load_sent,
  )
"""

import json
import os
import hashlib
import logging

log = logging.getLogger(__name__)

# Cache lives alongside this file so it's always findable on Node 1
CACHE_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mail_cache")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _user_dir(username: str) -> str:
    """Return the cache directory for this user (hashed so special chars are safe)."""
    safe = hashlib.md5(username.lower().strip().encode()).hexdigest()
    return os.path.join(CACHE_BASE, safe)


def _cache_path(username: str, folder: str) -> str:
    return os.path.join(_user_dir(username), f"{folder}.json")


# ── Inbox / Spam cache ────────────────────────────────────────────────────────

def save_cache(username: str, folder: str, emails: list) -> None:
    """
    Overwrite the cache for (username, folder) with the given email list.
    Each item should be a dict with at least {"index": int, "raw": str}.
    """
    try:
        d = _user_dir(username)
        os.makedirs(d, exist_ok=True)
        with open(_cache_path(username, folder), "w", encoding="utf-8") as f:
            json.dump(emails, f, ensure_ascii=False, indent=2)
        log.debug(f"[CACHE] Saved {len(emails)} email(s) → {folder} for {username}")
    except OSError as e:
        log.error(f"[CACHE] Could not save cache: {e}")


def load_cache(username: str, folder: str) -> list:
    """
    Load cached emails for (username, folder).
    Returns an empty list if no cache exists or if the file is corrupt.
    """
    path = _cache_path(username, folder)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        log.debug(f"[CACHE] Loaded {len(data)} email(s) ← {folder} for {username}")
        return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"[CACHE] Corrupt cache for {username}/{folder}: {e}")
        return []


def delete_from_cache(username: str, folder: str, msg_index: int) -> None:
    """
    Remove the email whose 'index' field equals msg_index from the cache,
    then re-number remaining emails so indices stay contiguous from 1.
    """
    emails = load_cache(username, folder)
    original_len = len(emails)
    emails = [e for e in emails if e.get("index") != msg_index]
    for i, e in enumerate(emails, 1):
        e["index"] = i
    save_cache(username, folder, emails)
    removed = original_len - len(emails)
    log.debug(f"[CACHE] Removed {removed} email(s) at index {msg_index} from {folder}")


def clear_cache(username: str, folder: str) -> None:
    """Wipe the entire cache for this user/folder (e.g. on explicit sign-out)."""
    path = _cache_path(username, folder)
    try:
        if os.path.exists(path):
            os.remove(path)
            log.debug(f"[CACHE] Cleared {folder} cache for {username}")
    except OSError as e:
        log.warning(f"[CACHE] Could not clear cache: {e}")


# ── Sent-mail cache ───────────────────────────────────────────────────────────

def _sent_path(username: str) -> str:
    return _cache_path(username, "sent")


def append_sent(username: str, sent_dict: dict) -> None:
    """
    Append one sent-mail record to the user's Sent cache.
    sent_dict should contain at minimum:
      {message_id, from, to, cc, subject, body, timestamp, raw}
    The record is assigned a sequential 'index' for GUI consistency.
    """
    try:
        existing = load_sent(username)
        next_idx = (existing[-1]["index"] + 1) if existing else 1
        sent_dict = dict(sent_dict)          # copy so we don't mutate caller's dict
        sent_dict["index"] = next_idx
        existing.append(sent_dict)
        d = _user_dir(username)
        os.makedirs(d, exist_ok=True)
        with open(_sent_path(username), "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        log.debug(f"[CACHE] Appended sent message #{next_idx} for {username}")
    except OSError as e:
        log.error(f"[CACHE] Could not append to Sent cache: {e}")


def load_sent(username: str) -> list:
    """
    Load the Sent cache for username.
    Returns an empty list if nothing has been sent yet or the file is corrupt.
    """
    path = _sent_path(username)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        log.debug(f"[CACHE] Loaded {len(data)} sent message(s) for {username}")
        return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"[CACHE] Corrupt Sent cache for {username}: {e}")
        return []

# 📧 SecureMail — Distributed Secure Email System

> A fully distributed, multi-node secure email system built from scratch using raw TCP/UDP sockets in Python. Implements real SMTP/POP3 protocols, end-to-end Fernet encryption, AI-powered spam detection, DNS-based user verification, proxy routing, and a complete Tkinter GUI client — all deployable across multiple physical machines over a LAN/hotspot.

---

## 📖 Table of Contents

- [Project Overview](#project-overview)
- [Architecture](#architecture)
- [Node Details & Functionality](#node-details--functionality)
  - [Node 1 — Client (GUI)](#node-1--client-gui)
  - [Node 2 — Proxy Server](#node-2--proxy-server)
  - [Node 3 — SMTP Server](#node-3--smtp-server)
  - [Node 4 — POP3 + Registration Server](#node-4--pop3--registration-server)
  - [Node 5 — DNS + AI Spam Filter](#node-5--dns--ai-spam-filter)
- [Security Features](#security-features)
- [Configuration](#configuration)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Running the System](#running-the-system)
- [Port Reference](#port-reference)
- [File Structure](#file-structure)

---

## Project Overview

SecureMail is a ground-up implementation of a secure email infrastructure. Rather than using standard libraries like `smtplib` or third-party mail services, every protocol exchange is implemented over raw sockets. The system is built across **5 nodes**, each running on a separate machine or process, simulating a real-world distributed email service.

**Key highlights:**
- Raw TCP socket SMTP and POP3 protocol implementations
- UDP-based DNS-style user verification and spam scanning
- Fernet (AES-128-CBC + HMAC-SHA256) encryption for all email bodies in transit
- Logistic Regression + TF-IDF AI spam classifier running on Node 5
- IP-based blacklist/whitelist access control at the proxy
- Local email caching on the client for offline reading
- Full Tkinter GUI with Inbox, Compose, Login, Registration, and Admin panels
- Designed for multi-machine deployment over a Wi-Fi hotspot

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SYSTEM FLOW                                   │
│                                                                      │
│  [Node 1: Client GUI]                                                │
│      │  TCP :8000 (all traffic goes through proxy)                   │
│      ▼                                                               │
│  [Node 2: Proxy Server] ──── UDP :5053 ──── [Node 5: DNS + Spam]    │
│      │  ROUTE:SMTP  ──► TCP :2525 ──► [Node 3: SMTP Server]         │
│      │  ROUTE:POP3  ──► TCP :1100 ──► [Node 4: POP3 Server]         │
│      └  ROUTE:REGISTER ──► TCP :4502 ──► [Node 4: Registration]     │
│                                                                      │
│  [Node 3: SMTP] ──── TCP :4501 (file push) ──── [Node 4: POP3]      │
│  [Node 4: POP3] ──── TCP :4503 (delete notify) ── [Node 3: SMTP]    │
└──────────────────────────────────────────────────────────────────────┘
```

All client traffic passes exclusively through **Node 2 (Proxy)** — clients never connect directly to SMTP, POP3, or DNS nodes. The proxy inspects, routes, encrypts/decrypts, and filters all traffic.

---

## Node Details & Functionality

### Node 1 — Client (GUI)

**Machine:** Client machine (any team member)  
**Directory:** `node1_client/`

This node provides the full user-facing experience through a Tkinter GUI application.

**Files:**
| File | Purpose |
|------|---------|
| `client_gui.py` | Main GUI — Login, Register, Inbox, Compose, Admin Dashboard |
| `tcp_smtp_sender.py` | Handles composing and sending emails via SMTP through the proxy |
| `tcp_pop3_fetcher.py` | Fetches, lists, and deletes emails via POP3 through the proxy |
| `auth_client.py` | Sends `REGISTER` commands through the proxy to Node 4 |
| `local_cache.py` | Caches fetched emails locally in `.mail_cache/` for offline access |

**Features:**
- **Login screen** — Authenticates against POP3 using `USER` + `PASS` commands
- **Registration** — Creates new accounts; validates via Node 5 DNS and persists to Node 4
- **Inbox** — Lists emails from POP3, reads from local cache when available, marks read status
- **Compose** — Full compose window with To, Subject, Body fields; sends via SMTP route
- **Delete** — Deletes emails from server and removes from local cache
- **Admin Dashboard** — View registered users and email statistics (Node 4 admin endpoint)
- **Local caching** — Email bodies are saved in `.mail_cache/<user>/` as JSON files, reducing redundant POP3 fetches

---

### Node 2 — Proxy Server

**Machine:** Ronak's machine (`172.18.4.117`)  
**Directory:** `node2_proxy/`  
**Port:** `8000` (TCP)

The proxy is the **single entry point** for all client connections. It inspects the first line of each TCP connection to determine the route, then transparently forwards traffic to the appropriate backend node — with encryption and security checks applied.

**Files:**
| File | Purpose |
|------|---------|
| `proxy_server.py` | Core routing engine — SMTP, POP3, REGISTER routes |
| `crypto.py` | Fernet symmetric encryption/decryption module |
| `security_manager.py` | IP whitelist/blacklist access control |
| `udp_client_helper.py` | UDP client for querying Node 5 (spam check, DNS verify) |
| `blacklist.txt` | Blocked IP addresses |
| `whitelist.txt` | Explicitly allowed IP addresses |

**Routing logic:**
- `ROUTE:SMTP` → Proxy reads the email body from client, **encrypts** it with Fernet, then forwards to Node 3 on port `2525`
- `ROUTE:POP3` → Proxy fetches encrypted email from Node 4 on port `1100`, **decrypts** it, and streams back to client
- `ROUTE:REGISTER` → Plain passthrough to Node 4 registration server on port `4502`

**Security checks at proxy:**
1. IP is checked against `blacklist.txt` — blocked IPs get connection refused immediately
2. Before forwarding SMTP mail, the body is sent to Node 5 via UDP for spam analysis
3. If Node 5 returns `is_spam: true`, the proxy drops the email and returns `-ERR Spam detected`

---

### Node 3 — SMTP Server

**Machine:** Gaurav's machine (`172.18.0.236`)  
**Directory:** `node3_smtp/`  
**Port:** `2525` (TCP)

Implements a custom SMTP server that receives **already-encrypted** email bodies from the proxy, stores them, and immediately pushes them to Node 4.

**Files:**
| File | Purpose |
|------|---------|
| `smtp_server.py` | SMTP protocol handler — HELO, MAIL FROM, RCPT TO, DATA, QUIT |
| `file_pusher.py` | Pushes received `.eml` files to Node 4 via TCP on port `4501` |
| `receipt_manager.py` | Logs delivery receipts and acknowledgments |
| `delete_server.py` | Listens on port `4503` for delete notifications from Node 4 |
| `udp_client_helper.py` | Verifies recipient addresses against Node 5 DNS before accepting |

**Flow:**
1. Proxy connects and runs through SMTP handshake (`HELO` → `MAIL FROM` → `RCPT TO` → `DATA`)
2. Before accepting, SMTP server queries Node 5 UDP to verify the recipient email exists
3. If valid, the encrypted body is written to `storage/<recipient>/` as a `.eml` file
4. `file_pusher.py` immediately opens a TCP connection to Node 4 (port `4501`) and pushes the file
5. On successful push, the local copy can be cleared; delivery receipt is logged

---

### Node 4 — POP3 + Registration Server

**Machine:** Sunny's machine (`172.18.13.91`)  
**Directory:** `node4_pop3/`  
**Ports:** `1100` (POP3), `4501` (file receiver), `4502` (registration), `4503` (delete notify sender)

This is the **mailbox node** — it stores all delivered emails, handles retrieval, user registration, and account management.

**Files:**
| File | Purpose |
|------|---------|
| `pop3_server.py` | Full POP3 protocol server — STAT, LIST, RETR, DELE, QUIT |
| `registration_server.py` | Handles `REGISTER <email> <password>` TCP commands |
| `file_receiver.py` | TCP server on port `4501` receiving pushed `.eml` files from Node 3 |
| `user_manager.py` | User CRUD — add, verify credentials, list users; persists to `users.txt` |
| `admin_dashboard.py` | Exposes admin statistics endpoint for GUI dashboard |
| `users.txt` | Flat-file user store (`email:hashed_password` format) |

**POP3 Protocol implementation:**
- `USER <email>` — sets the session user
- `PASS <password>` — authenticates; verified against `users.txt`
- `STAT` — returns mailbox message count and total size
- `LIST` — lists all message IDs with sizes
- `RETR <id>` — retrieves full encrypted email body (proxy decrypts before sending to client)
- `DELE <id>` — marks message for deletion and notifies Node 3 to remove its copy
- `QUIT` — finalizes deletions and closes session

**Delete synchronization:** When a client deletes an email, Node 4 sends a TCP notification to Node 3 on port `4503` so both nodes stay in sync.

---

### Node 5 — DNS + AI Spam Filter

**Machine:** Amit's machine (`172.18.1.42`)  
**Directory:** `node5_dns_spam/`  
**Port:** `5053` (UDP)

A **UDP server** serving two purposes: DNS-style user verification and AI-based spam classification.

**Files:**
| File | Purpose |
|------|---------|
| `udp_dns_server.py` | UDP listener handling VERIFY, SPAM_CHECK, REGISTER actions |
| `spam_filter.py` | ML spam classifier wrapper using Logistic Regression + TF-IDF |
| `valid_users.json` | JSON registry of all valid email addresses |

**Supported UDP actions (JSON protocol):**

```json
// Verify if a user/email exists
{"action": "VERIFY", "email": "user@domain"}
→ {"status": "OK"} | {"status": "FAIL"}

// Run AI spam classification on email body
{"action": "SPAM_CHECK", "content": "email body text here"}
→ {"is_spam": true} | {"is_spam": false}

// Register new user in DNS registry
{"action": "REGISTER", "email": "newuser@domain"}
→ {"status": "OK"} | {"status": "ERR", "reason": "..."}
```

**AI Spam Classifier:**
- Model: **Logistic Regression** trained on a labeled spam/ham dataset
- Vectorizer: **TF-IDF** (Term Frequency–Inverse Document Frequency)
- Artifacts loaded at startup: `spam_logistic_model.pkl` + `tfidf_vectorizer.pkl`
- Returns a boolean prediction — integrated directly into the SMTP receive pipeline
- Graceful fallback: if model files are missing, the node logs an error but other services continue

---

## Security Features

| Feature | Implementation |
|---------|---------------|
| **End-to-End Encryption** | Fernet (AES-128-CBC + HMAC-SHA256) — email bodies encrypted at proxy before reaching SMTP node |
| **AI Spam Filtering** | Logistic Regression + TF-IDF classifier on Node 5, queried via UDP before accepting any email |
| **DNS User Verification** | Recipient email validated against Node 5 registry before SMTP accepts the message |
| **IP Access Control** | Node 2 proxy checks `blacklist.txt` and `whitelist.txt` on every incoming connection |
| **Password Hashing** | User passwords stored hashed in `users.txt` on Node 4 |
| **Shared Secret Key** | `secret.key` Fernet key file must be present on all nodes that encrypt/decrypt |
| **Proxy-Only Access** | Backend nodes (SMTP, POP3, DNS) are not directly accessible from clients |

---

## Configuration

All network configuration is centralized in `config.py` at the root of the repository.

```python
# config.py
PROXY_IP      = "172.18.4.117"   # Node 2 – Proxy
SMTP_IP       = "172.18.0.236"   # Node 3 – SMTP
POP3_IP       = "172.18.13.91"   # Node 4 – POP3
DNS_SPAM_IP   = "172.18.1.42"    # Node 5 – DNS/Spam

PROXY_PORT         = 8000
SMTP_PORT          = 2525
POP3_PORT          = 1100
DNS_SPAM_PORT      = 5053
FILE_TRANSFER_PORT = 4501   # Node 3 → Node 4 push
REGISTRATION_PORT  = 4502   # Node 4 registration
DELETE_PORT        = 4503   # Node 4 → Node 3 delete sync

SHARED_STORAGE_DIR = "storage"
```

**For single-machine local testing:** Replace all IPs with `127.0.0.1`.  
**For multi-machine hotspot deployment:** Set each `*_IP` to the actual hotspot IP of the respective machine (find with `ip addr` on Linux or `ipconfig` on Windows). IPs can also be overridden via environment variables: `PROXY_IP`, `SMTP_IP`, `POP3_IP`, `DNS_IP`.

---

## Prerequisites

- Python **3.8+**
- The following Python packages:

```
cryptography       # Fernet encryption
joblib             # Loading ML model artifacts
scikit-learn       # Logistic Regression + TF-IDF (for training/inference)
tkinter            # GUI (usually bundled with Python; install python3-tk on Linux)
```

Install dependencies:

```bash
pip install cryptography joblib scikit-learn
# On Ubuntu/Debian for tkinter:
sudo apt install python3-tk
```

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/RONAKBAGRI/SecureMail_Project.git
cd SecureMail_Project
```

### 2. Configure IPs

Edit `config.py` and set the IP addresses for each node to match the machines in your network. For local testing, keep all IPs as `127.0.0.1`.

### 3. Generate/share the encryption key

The Fernet key (`secret.key`) is auto-generated on first run of the proxy. **Copy it to all nodes** that need to encrypt or decrypt (Node 2 and Node 4 at minimum):

```bash
# Run proxy once to generate key, then copy:
cp node2_proxy/secret.key node4_pop3/secret.key
```

### 4. Prepare AI spam model artifacts

Node 5 requires `spam_logistic_model.pkl` and `tfidf_vectorizer.pkl` in the `node5_dns_spam/` directory. Train or obtain these from the project team and place them there.

### 5. Create storage directories

```bash
mkdir -p node3_smtp/storage
mkdir -p node4_pop3/storage
```

---

## Running the System

Start each node **in order** on its respective machine. Each command should be run from the **repository root**.

### Step 1 — Start Node 5 (DNS + Spam Filter)
```bash
python node5_dns_spam/udp_dns_server.py
```

### Step 2 — Start Node 4 (POP3 + Registration)
```bash
python node4_pop3/pop3_server.py
```

### Step 3 — Start Node 3 (SMTP)
```bash
python node3_smtp/smtp_server.py
```

### Step 4 — Start Node 2 (Proxy)
```bash
python node2_proxy/proxy_server.py
```

### Step 5 — Launch Node 1 (Client GUI)
```bash
python node1_client/client_gui.py
```

> **Tip:** For single-machine testing, open 5 separate terminal windows and run each command simultaneously.

---

## Port Reference

| Port | Protocol | Node | Purpose |
|------|----------|------|---------|
| `8000` | TCP | Node 2 | Client → Proxy (all traffic) |
| `25` | TCP | Node 3 | Proxy → SMTP server |
| `110` | TCP | Node 4 | Proxy → POP3 server |
| `5053` | **UDP** | Node 5 | DNS verification + Spam check |
| `4501` | TCP | Node 4 | Node 3 → Node 4 email file push |
| `4502` | TCP | Node 4 | Proxy → Registration server |
| `4503` | TCP | Node 3 | Node 4 → Node 3 delete sync |

---

## File Structure

```
SecureMail_Project/
│
├── config.py                        # Centralized IP and port configuration
├── requirements.txt                 # Python dependencies
├── .gitignore
│
├── node1_client/                    # CLIENT — GUI application
│   ├── client_gui.py                # Tkinter GUI (Login, Inbox, Compose, Admin)
│   ├── tcp_smtp_sender.py           # SMTP client (send emails)
│   ├── tcp_pop3_fetcher.py          # POP3 client (fetch/delete emails)
│   ├── auth_client.py               # Registration client
│   ├── local_cache.py               # Local email cache manager
│   └── .mail_cache/                 # Cached email storage (auto-created)
│
├── node2_proxy/                     # PROXY SERVER — security + routing
│   ├── proxy_server.py              # Main routing engine
│   ├── crypto.py                    # Fernet encrypt/decrypt
│   ├── security_manager.py          # IP access control
│   ├── udp_client_helper.py         # UDP queries to Node 5
│   ├── blacklist.txt                # Blocked IPs
│   ├── whitelist.txt                # Allowed IPs
│   └── secret.key                   # Fernet key (auto-generated, share with Node 4)
│
├── node3_smtp/                      # SMTP SERVER — receive and relay emails
│   ├── smtp_server.py               # SMTP protocol handler
│   ├── file_pusher.py               # Push .eml to Node 4
│   ├── receipt_manager.py           # Delivery receipt logging
│   ├── delete_server.py             # Delete notification listener
│   ├── udp_client_helper.py         # DNS recipient verification
│   └── storage/                     # Stored emails (auto-created)
│
├── node4_pop3/                      # POP3 SERVER — mailbox storage
│   ├── pop3_server.py               # POP3 protocol handler
│   ├── registration_server.py       # User registration TCP server
│   ├── file_receiver.py             # Receive pushed .eml from Node 3
│   ├── user_manager.py              # User CRUD with hashed passwords
│   ├── admin_dashboard.py           # Admin stats endpoint
│   ├── users.txt                    # User database (email:hash)
│   └── storage/                     # Mailbox storage (auto-created)
│
└── node5_dns_spam/                  # DNS + SPAM FILTER — UDP service
    ├── udp_dns_server.py            # UDP server (VERIFY, SPAM_CHECK, REGISTER)
    ├── spam_filter.py               # ML spam classifier
    ├── valid_users.json             # Email registry
    ├── spam_logistic_model.pkl      # Pre-trained Logistic Regression model
    └── tfidf_vectorizer.pkl         # Pre-trained TF-IDF vectorizer
```

---

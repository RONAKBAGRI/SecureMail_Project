import os

# ============================================================
# MASTER CONFIGURATION
# For multi-machine hotspot: replace 127.0.0.1 with the actual
# hotspot IP of each machine (find with `ipconfig` / `ip addr`)
# For single-machine local testing: keep everything as 127.0.0.1
# ============================================================

PROXY_IP      = os.getenv("PROXY_IP",   "10.71.3.74")   # Node 2 – Ronak's machine
SMTP_IP       = os.getenv("SMTP_IP",    "10.71.3.193")   # Node 3 – Gaurav's machine
POP3_IP       = os.getenv("POP3_IP",    "10.71.3.241")   # Node 4 – Sunny's machine
DNS_SPAM_IP   = os.getenv("DNS_IP",     "10.71.3.45")   # Node 5 – Amit's machine

PROXY_PORT    = 8000
SMTP_PORT     = 2525
POP3_PORT     = 1100
DNS_SPAM_PORT = 5053

SHARED_STORAGE_DIR = "storage"
import tkinter as tk
from tkinter import ttk
import os
import sys

# Paths
STORAGE_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'storage'))
SPAM_LOG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'node5_dns_spam', 'spam_log.txt'))

class AdminDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("System Admin Dashboard")
        self.root.geometry("400x350")
        self.root.configure(bg="#1e1e2e")
        
        # Styling
        style = ttk.Style()
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4", font=("Arial", 12))
        style.configure("Header.TLabel", font=("Arial", 18, "bold"), foreground="#89b4fa")
        
        # Header
        ttk.Label(root, text="Email System Metrics", style="Header.TLabel").pack(pady=20)
        
        # Metric Labels
        self.lbl_users = ttk.Label(root, text="Active Users: 0")
        self.lbl_users.pack(pady=10)
        
        self.lbl_emails = ttk.Label(root, text="Total Emails Stored: 0")
        self.lbl_emails.pack(pady=10)
        
        self.lbl_spam = ttk.Label(root, text="Spam Intercepted: 0")
        self.lbl_spam.pack(pady=10)
        
        self.lbl_size = ttk.Label(root, text="Storage Used: 0 KB")
        self.lbl_size.pack(pady=10)
        
        # Start the update loop
        self.update_metrics()

    def update_metrics(self):
        """Calculates system metrics by scanning the file system."""
        total_users = 0
        total_emails = 0
        total_size_bytes = 0
        total_spam = 0
        
        # Check Storage
        if os.path.exists(STORAGE_BASE):
            users = os.listdir(STORAGE_BASE)
            total_users = len(users)
            
            for user in users:
                user_inbox = os.path.join(STORAGE_BASE, user, 'inbox')
                user_spam = os.path.join(STORAGE_BASE, user, 'spam')
                
                # Count inbox emails & sizes
                if os.path.exists(user_inbox):
                    for f in os.listdir(user_inbox):
                        filepath = os.path.join(user_inbox, f)
                        if os.path.isfile(filepath):
                            total_emails += 1
                            total_size_bytes += os.path.getsize(filepath)
                            
                # Count stored spam
                if os.path.exists(user_spam):
                    for f in os.listdir(user_spam):
                        filepath = os.path.join(user_spam, f)
                        if os.path.isfile(filepath):
                            total_size_bytes += os.path.getsize(filepath)
        
        # Check Amit's Spam Log (if Amit has created it yet)
        if os.path.exists(SPAM_LOG_FILE):
            with open(SPAM_LOG_FILE, 'r') as f:
                total_spam = sum(1 for line in f)

        # Update GUI text
        self.lbl_users.config(text=f"Active Users: {total_users}")
        self.lbl_emails.config(text=f"Total Emails Stored: {total_emails}")
        self.lbl_spam.config(text=f"Spam Intercepted: {total_spam}")
        self.lbl_size.config(text=f"Storage Used: {total_size_bytes / 1024:.2f} KB")
        
        # Schedule the next update in 3000ms (3 seconds)
        self.root.after(3000, self.update_metrics)

if __name__ == "__main__":
    root = tk.Tk()
    app = AdminDashboard(root)
    root.mainloop()
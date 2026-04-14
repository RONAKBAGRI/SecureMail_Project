import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tcp_smtp_sender import send_email
from tcp_pop3_fetcher import fetch_emails

# ── Credentials (change per user) ──────────────────────────────
MY_EMAIL    = "prashant@project.local"
MY_PASSWORD = "password123"

# ── Color palette ───────────────────────────────────────────────
BG      = "#1a1a2e"
PANEL   = "#16213e"
ACCENT  = "#0f3460"
BLUE    = "#533483"
WHITE   = "#e0e0e0"
GREEN   = "#4ecca3"
RED     = "#e94560"
FONT    = ("Liberation Mono", 10)
FONT_B  = ("Liberation Mono", 10, "bold")
FONT_H  = ("Liberation Mono", 13, "bold")


class SecureMailApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SecureMail – Distributed Email Client")
        self.root.configure(bg=BG)
        self.root.geometry("900x650")
        self.root.resizable(True, True)
        self.emails: list[dict] = []
        self._build_ui()

    # ── UI Construction ─────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=ACCENT, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="SecureMail", font=("Liberation Mono", 15, "bold"),
                 bg=ACCENT, fg=GREEN).pack(side="left", padx=16)
        tk.Label(hdr, text=f"Logged in as: {MY_EMAIL}", font=FONT,
                 bg=ACCENT, fg=WHITE).pack(side="right", padx=16)

        # Notebook tabs
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",        background=BG, borderwidth=0)
        style.configure("TNotebook.Tab",    background=ACCENT, foreground=WHITE,
                         font=FONT_B, padding=[14, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", BLUE)],
                  foreground=[("selected", GREEN)])

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        compose_tab = tk.Frame(nb, bg=BG)
        inbox_tab   = tk.Frame(nb, bg=BG)
        nb.add(compose_tab, text="  Compose  ")
        nb.add(inbox_tab,   text="  Inbox  ")

        self._build_compose(compose_tab)
        self._build_inbox(inbox_tab)

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var, font=FONT,
            bg=PANEL, fg=GREEN, anchor="w", pady=4, padx=10
        )
        self.status_label.pack(fill="x", side="bottom")

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_B, bg=BG, fg=GREEN).pack(anchor="w", padx=20, pady=(10, 2))

    def _entry(self, parent):
        e = tk.Entry(parent, font=FONT, bg=PANEL, fg=WHITE,
                     insertbackground=WHITE, relief="flat",
                     highlightthickness=1, highlightcolor=BLUE,
                     highlightbackground=ACCENT)
        e.pack(fill="x", padx=20, ipady=4)
        return e

    def _build_compose(self, frame):
        self._label(frame, "To:")
        self.to_entry = self._entry(frame)

        self._label(frame, "Subject:")
        self.subj_entry = self._entry(frame)

        self._label(frame, "Message:")
        self.body_text = tk.Text(frame, font=FONT, bg=PANEL, fg=WHITE,
                                  insertbackground=WHITE, relief="flat",
                                  highlightthickness=1, highlightcolor=BLUE,
                                  highlightbackground=ACCENT, height=14)
        self.body_text.pack(fill="both", expand=True, padx=20, pady=(2, 10))

        btn_frame = tk.Frame(frame, bg=BG)
        btn_frame.pack(pady=6)
        self._btn(btn_frame, "  Send Email  ", self._handle_send, GREEN).pack(side="left", padx=8)
        self._btn(btn_frame, "  Clear  ", self._clear_compose, WHITE).pack(side="left", padx=8)

    def _build_inbox(self, frame):
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x", padx=20, pady=10)
        tk.Label(top, text="Inbox", font=FONT_H, bg=BG, fg=GREEN).pack(side="left")
        self._btn(top, "  Refresh  ", self._handle_fetch, GREEN).pack(side="right")

        pane = tk.PanedWindow(frame, orient="horizontal", bg=BG,
                               sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Left – email list
        list_frame = tk.Frame(pane, bg=PANEL, width=260)
        pane.add(list_frame, minsize=200)

        self.email_listbox = tk.Listbox(
            list_frame, font=FONT, bg=PANEL, fg=WHITE,
            selectbackground=BLUE, selectforeground=GREEN,
            relief="flat", borderwidth=0, activestyle="none"
        )
        self.email_listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self.email_listbox.bind("<<ListboxSelect>>", self._on_select_email)

        # Right – email viewer
        view_frame = tk.Frame(pane, bg=PANEL)
        pane.add(view_frame, minsize=300)

        self.email_view = scrolledtext.ScrolledText(
            view_frame, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            borderwidth=0, state="disabled", wrap="word"
        )
        self.email_view.pack(fill="both", expand=True, padx=6, pady=6)

    def _btn(self, parent, text, cmd, color):
        return tk.Button(parent, text=text, command=cmd, font=FONT_B,
                         bg=ACCENT, fg=color, activebackground=BLUE,
                         activeforeground=GREEN, relief="flat",
                         cursor="hand2", padx=6, pady=4)

    # ── Event Handlers ──────────────────────────────────────────
    def _set_status(self, msg, color=GREEN):
        self.status_var.set(msg)
        self.status_label.config(fg=color)

    def _handle_send(self):
        to      = self.to_entry.get().strip()
        subject = self.subj_entry.get().strip()
        body    = self.body_text.get("1.0", tk.END).strip()

        if not to or not body:
            messagebox.showwarning("Missing Fields", "Please fill in 'To' and 'Message'.")
            return

        self._set_status("Sending...")
        self.root.update_idletasks()

        def worker():
            ok, msg = send_email(MY_EMAIL, to, subject, body)
            if ok:
                self.root.after(0, lambda: (
                    messagebox.showinfo("Sent", msg),
                    self._set_status(f"Email sent to {to}.", GREEN),
                    self._clear_compose()
                ))
            else:
                self.root.after(0, lambda: (
                    messagebox.showerror("Send Failed", msg),
                    self._set_status(f"Send failed: {msg}", RED)
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_fetch(self):
        self._set_status("Fetching inbox...")
        self.root.update_idletasks()

        def worker():
            ok, result = fetch_emails(MY_EMAIL, MY_PASSWORD)
            if ok:
                self.emails = result
                self.root.after(0, self._populate_inbox)
                self.root.after(0, lambda: self._set_status(f"{len(result)} message(s) in inbox."))
            else:
                self.root.after(0, lambda: (
                    messagebox.showerror("Fetch Failed", result),
                    self._set_status(f"Fetch failed: {result}", RED)
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _populate_inbox(self):
        self.email_listbox.delete(0, tk.END)
        if not self.emails:
            self.email_listbox.insert(tk.END, "  (empty inbox)")
            return
        for em in self.emails:
            preview = em["raw"].replace("\r\n", " ")[:50]
            self.email_listbox.insert(tk.END, f"  #{em['index']}  {preview}...")

    def _on_select_email(self, _event):
        sel = self.email_listbox.curselection()
        if not sel or not self.emails:
            return
        idx = sel[0]
        if idx >= len(self.emails):
            return
        raw = self.emails[idx]["raw"]
        self.email_view.config(state="normal")
        self.email_view.delete("1.0", tk.END)
        self.email_view.insert(tk.END, raw)
        self.email_view.config(state="disabled")

    def _clear_compose(self):
        self.to_entry.delete(0, tk.END)
        self.subj_entry.delete(0, tk.END)
        self.body_text.delete("1.0", tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = SecureMailApp(root)
    root.mainloop()
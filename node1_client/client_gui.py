"""
Node 1 – SecureMail GUI (Prashant)
====================================
Flow: LoginScreen → MainApp → (logout) → LoginScreen

Features in this version:
  • Spam tab          – fetches from the spam folder on Node 4
  • Offline cache     – emails loaded from local JSON cache on login;
                        cache updated on every successful network Refresh
  • Reply             – pre-fills Compose with correct In-Reply-To header
                        so the reply is properly threaded on delivery
  • Threaded view     – replies shown indented below their parent email,
                        Gmail-style conversation grouping
  • Sent tab          – local-only; loads instantly from Sent cache on login
  • CC / BCC fields   – full multi-recipient support in Compose
  • Delete            – removes from GUI, local cache, Node 4, Node 3
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tcp_smtp_sender  import send_email
from tcp_pop3_fetcher import fetch_emails, delete_email
from auth_client      import register_user
from local_cache      import (
    save_cache, load_cache, delete_from_cache,
    append_sent, load_sent,
)

# ── Palette ───────────────────────────────────────────────────────────────────
BG     = "#0d1117"
PANEL  = "#161b22"
BORDER = "#30363d"
ACCENT = "#1f6feb"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#d29922"
ORANGE = "#e3b341"
WHITE  = "#e6edf3"
MUTED  = "#8b949e"
THREAD = "#21262d"   # background tint for threaded replies

FONT   = ("TkDefaultFont", 10)
FONT_B = ("TkDefaultFont", 10, "bold")
FONT_H = ("TkDefaultFont", 15, "bold")
FONT_S = ("TkDefaultFont", 9)
FONT_I = ("TkDefaultFont", 9, "italic")


# ── Widget factories ──────────────────────────────────────────────────────────

def _entry(parent, show=None):
    return tk.Entry(
        parent, font=FONT, bg=PANEL, fg=WHITE,
        show=show or "", insertbackground=WHITE,
        relief="flat", highlightthickness=1,
        highlightcolor=ACCENT, highlightbackground=BORDER,
    )


def _btn(parent, text, cmd, fg=WHITE, bg=None):
    return tk.Button(
        parent, text=text, command=cmd, font=FONT_B,
        bg=bg or BORDER, fg=fg,
        activebackground=ACCENT, activeforeground=WHITE,
        relief="flat", cursor="hand2",
        padx=10, pady=5, borderwidth=0,
    )


# ── Email parsing helpers ─────────────────────────────────────────────────────

def _parse_headers(raw: str) -> dict:
    """Extract common headers from a raw email string."""
    headers = {
        "from": "", "to": "", "cc": "",
        "subject": "", "message_id": "", "in_reply_to": "",
    }
    for line in raw.replace("\r\n", "\n").split("\n"):
        low = line.lower()
        if low.startswith("from:"):
            headers["from"] = line[5:].strip()
        elif low.startswith("to:"):
            headers["to"] = line[3:].strip()
        elif low.startswith("cc:"):
            headers["cc"] = line[3:].strip()
        elif low.startswith("subject:"):
            headers["subject"] = line[8:].strip()
        elif low.startswith("message-id:"):
            headers["message_id"] = line[11:].strip()
        elif low.startswith("in-reply-to:"):
            headers["in_reply_to"] = line[12:].strip()
        elif not line.strip():
            break  # end of header block
    return headers


def _body_only(raw: str) -> str:
    """Return only the body portion of a raw email (after the blank header line)."""
    sep = "\r\n\r\n" if "\r\n\r\n" in raw else "\n\n"
    parts = raw.split(sep, 1)
    return parts[1] if len(parts) > 1 else raw


def _list_preview(email: dict) -> str:
    """One-line summary for the email list panel."""
    h    = _parse_headers(email["raw"])
    frm  = h["from"] or "(unknown sender)"
    subj = h["subject"] or "(no subject)"
    return f" #{email['index']}  {frm}  —  {subj}"[:72]


def _thread_emails(emails: list) -> list:
    """
    Given a flat list of email dicts, return a list of 'thread roots'.
    Each root is a dict:
      {
        "email"   : <the original email dict>,
        "replies" : [<email dict>, …]   ← direct children, in order
      }
    Emails whose In-Reply-To matches another email's Message-ID are nested.
    Everything else is a root.
    """
    by_msg_id = {}
    for em in emails:
        mid = em.get("message_id") or _parse_headers(em["raw"]).get("message_id", "")
        if mid:
            by_msg_id[mid] = em

    roots   = []
    replies = {}   # parent_msg_id → [child email, …]

    for em in emails:
        irt = em.get("in_reply_to") or _parse_headers(em["raw"]).get("in_reply_to", "")
        if irt and irt in by_msg_id:
            replies.setdefault(irt, []).append(em)
        else:
            roots.append(em)

    threaded = []
    for root in roots:
        mid = root.get("message_id") or _parse_headers(root["raw"]).get("message_id", "")
        threaded.append({
            "email":   root,
            "replies": replies.get(mid, []),
        })
    return threaded


# ─────────────────────────────────────────────────────────────────────────────
# REGISTER DIALOG (modal)
# ─────────────────────────────────────────────────────────────────────────────

class RegisterDialog(tk.Toplevel):
    def __init__(self, parent, on_success):
        super().__init__(parent)
        self._on_success = on_success
        self.title("Create Account")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self.geometry("400x360")
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + parent.winfo_width()  // 2 - 200
        y = parent.winfo_rooty() + parent.winfo_height() // 2 - 180
        self.geometry(f"+{x}+{y}")

    def _build(self):
        pad = tk.Frame(self, bg=BG, padx=28, pady=24)
        pad.pack(fill="both", expand=True)

        tk.Label(pad, text="Create Account", font=FONT_H,
                 bg=BG, fg=GREEN).pack(anchor="w", pady=(0, 18))

        for label, attr, show in [
            ("Email  (e.g. alice@project.local)", "email_e", None),
            ("Password  (min 4 chars)",           "pass_e",  "●"),
            ("Confirm Password",                  "conf_e",  "●"),
        ]:
            tk.Label(pad, text=label, font=FONT_S, bg=BG, fg=MUTED).pack(anchor="w")
            e = _entry(pad, show=show)
            e.pack(fill="x", ipady=4, pady=(2, 10))
            setattr(self, attr, e)

        self._status = tk.StringVar()
        tk.Label(pad, textvariable=self._status, font=FONT_S,
                 bg=BG, fg=RED, wraplength=340).pack(anchor="w")

        row = tk.Frame(pad, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        _btn(row, "  Create Account  ", self._submit,
             fg=WHITE, bg=ACCENT).pack(side="left")
        _btn(row, "  Cancel  ", self.destroy,
             fg=MUTED, bg=PANEL).pack(side="left", padx=(8, 0))

    def _submit(self):
        email   = self.email_e.get().strip().lower()
        pw      = self.pass_e.get().strip()
        confirm = self.conf_e.get().strip()

        if not email or not pw:
            self._status.set("All fields are required.")
            return
        if "@" not in email:
            self._status.set("Enter a valid email (e.g. name@project.local).")
            return
        if pw != confirm:
            self._status.set("Passwords do not match.")
            return
        if len(pw) < 4:
            self._status.set("Password must be at least 4 characters.")
            return

        self._status.set("Registering…")
        self.update_idletasks()

        def _work():
            ok, msg = register_user(email, pw)
            if ok:
                self.after(0, lambda: (
                    messagebox.showinfo(
                        "Account Created",
                        f"Account created for:\n{email}\n\nYou can now log in.",
                        parent=self
                    ),
                    self._on_success(email, pw),
                    self.destroy()
                ))
            else:
                self.after(0, lambda: self._status.set(f"Error: {msg}"))

        threading.Thread(target=_work, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class LoginScreen(tk.Frame):
    def __init__(self, parent, on_success):
        super().__init__(parent, bg=BG)
        self._on_success = on_success
        self._build()

    def _build(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(wrap, text="◉  SecureMail", font=("TkDefaultFont", 22, "bold"),
                 bg=BG, fg=GREEN).pack(pady=(0, 4))
        tk.Label(wrap, text="Distributed Email System — Group 7",
                 font=FONT_S, bg=BG, fg=MUTED).pack(pady=(0, 28))

        card = tk.Frame(wrap, bg=PANEL, padx=32, pady=32,
                        highlightthickness=1, highlightbackground=BORDER)
        card.pack()

        tk.Label(card, text="Email", font=FONT_B,
                 bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
        self._email_e = _entry(card)
        self._email_e.pack(fill="x", ipady=5, pady=(2, 14))

        tk.Label(card, text="Password", font=FONT_B,
                 bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
        self._pass_e = _entry(card, show="●")
        self._pass_e.pack(fill="x", ipady=5, pady=(2, 18))

        self._status = tk.StringVar()
        tk.Label(card, textvariable=self._status, font=FONT_S,
                 bg=PANEL, fg=RED).pack(pady=(0, 10))

        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x")
        _btn(row, "  Login  ", self._login,
             fg=WHITE, bg=ACCENT).pack(side="left", expand=True, fill="x", padx=(0, 6))
        _btn(row, "  Register  ", self._open_register,
             fg=GREEN, bg=PANEL).pack(side="left", expand=True, fill="x")

        self._pass_e.bind("<Return>", lambda _: self._login())
        self._email_e.bind("<Return>", lambda _: self._pass_e.focus())

    def _login(self):
        email = self._email_e.get().strip().lower()
        pw    = self._pass_e.get().strip()
        if not email or not pw:
            self._status.set("Please enter email and password.")
            return
        self._status.set("Verifying…")
        self.update_idletasks()

        def _work():
            ok, result = fetch_emails(email, pw)
            if ok or isinstance(result, list):
                self.after(0, lambda: self._on_success(email, pw))
            else:
                err = result if isinstance(result, str) else "Login failed."
                self.after(0, lambda: self._status.set(err))

        threading.Thread(target=_work, daemon=True).start()

    def _open_register(self):
        RegisterDialog(
            self,
            on_success=lambda e, p: (
                self._email_e.delete(0, tk.END) or self._email_e.insert(0, e),
                self._pass_e.delete(0, tk.END)  or self._pass_e.insert(0, p),
                self._status.set("Account created — you can now log in.")
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP SCREEN
# ─────────────────────────────────────────────────────────────────────────────

class MainApp(tk.Frame):
    def __init__(self, parent, email: str, password: str, on_logout):
        super().__init__(parent, bg=BG)
        self._email    = email
        self._password = password
        self._logout   = on_logout

        # Per-folder flat email lists (raw from server/cache)
        self._inbox_emails: list = []
        self._spam_emails:  list = []
        self._sent_emails:  list = []

        # Threaded view data: list of {"email": …, "replies": […]}
        self._inbox_threads: list = []
        self._spam_threads:  list = []

        # Currently selected item
        self._sel_folder:   str = "inbox"
        self._sel_list_idx: int = -1
        self._sel_is_reply: bool = False   # True if the selected item is a reply row

        # Reply-compose state: Message-ID of email being replied to
        self._reply_to_msg_id: str = ""

        self._build()
        self._load_from_cache()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL,
                       highlightthickness=1, highlightbackground=BORDER)
        hdr.pack(fill="x")
        tk.Label(hdr, text="◉  SecureMail", font=("TkDefaultFont", 13, "bold"),
                 bg=PANEL, fg=GREEN, padx=16, pady=8).pack(side="left")
        tk.Label(hdr, text=self._email, font=FONT_S,
                 bg=PANEL, fg=MUTED, padx=6).pack(side="left")
        _btn(hdr, "Logout", self._do_logout,
             fg=RED, bg=PANEL).pack(side="right", padx=12, pady=6)

        # ── Notebook tabs ──────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                        font=FONT_B, padding=[16, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", WHITE)])

        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=10, pady=8)

        ct = tk.Frame(self._nb, bg=BG)
        it = tk.Frame(self._nb, bg=BG)
        st = tk.Frame(self._nb, bg=BG)
        sent_t = tk.Frame(self._nb, bg=BG)

        self._nb.add(ct,     text="  ✉  Compose  ")
        self._nb.add(it,     text="  📥  Inbox  ")
        self._nb.add(st,     text="  🚫  Spam  ")
        self._nb.add(sent_t, text="  📤  Sent  ")

        self._build_compose(ct)
        self._build_mail_tab(it, "inbox")
        self._build_mail_tab(st, "spam")
        self._build_sent_tab(sent_t)

        # ── Status bar ─────────────────────────────────────────────────────────
        self._sv = tk.StringVar(value="Ready.")
        self._sb = tk.Label(self, textvariable=self._sv, font=FONT_S,
                            bg=PANEL, fg=GREEN, anchor="w", pady=4, padx=12)
        self._sb.pack(fill="x", side="bottom")

    # ── Compose tab ───────────────────────────────────────────────────────────

    def _lbl(self, p, t):
        tk.Label(p, text=t, font=FONT_B, bg=BG,
                 fg=MUTED, anchor="w").pack(fill="x", padx=20, pady=(10, 2))

    def _build_compose(self, f):
        self._lbl(f, "To:  (comma-separated)")
        self._to = _entry(f)
        self._to.pack(fill="x", padx=20, ipady=4)

        self._lbl(f, "CC:  (optional, comma-separated)")
        self._cc = _entry(f)
        self._cc.pack(fill="x", padx=20, ipady=4)

        self._lbl(f, "BCC:  (optional, comma-separated — recipients hidden from others)")
        self._bcc = _entry(f)
        self._bcc.pack(fill="x", padx=20, ipady=4)

        self._lbl(f, "Subject:")
        self._subj = _entry(f)
        self._subj.pack(fill="x", padx=20, ipady=4)

        # Hidden label showing the In-Reply-To context
        self._reply_ctx_var = tk.StringVar(value="")
        self._reply_ctx_lbl = tk.Label(
            f, textvariable=self._reply_ctx_var,
            font=FONT_I, bg=BG, fg=MUTED, anchor="w",
        )
        self._reply_ctx_lbl.pack(fill="x", padx=20)

        self._lbl(f, "Message:")
        self._body = tk.Text(
            f, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            highlightthickness=1, highlightcolor=ACCENT,
            highlightbackground=BORDER, height=12,
        )
        self._body.pack(fill="both", expand=True, padx=20, pady=(2, 10))

        row = tk.Frame(f, bg=BG)
        row.pack(pady=6)
        _btn(row, "  ✈  Send  ", self._send,
             fg=WHITE, bg=ACCENT).pack(side="left", padx=6)
        _btn(row, "  Clear  ", self._clear_compose,
             fg=MUTED, bg=PANEL).pack(side="left", padx=6)

    # ── Sent tab ──────────────────────────────────────────────────────────────

    def _build_sent_tab(self, f):
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=20, pady=(10, 6))
        tk.Label(top, text="📤  Sent", font=FONT_H,
                 bg=BG, fg=WHITE).pack(side="left")

        pane = tk.PanedWindow(f, orient="horizontal", bg=BG,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        lf = tk.Frame(pane, bg=PANEL, width=280,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(lf, minsize=200)

        self._sent_lb = tk.Listbox(
            lf, font=FONT_S, bg=PANEL, fg=WHITE,
            selectbackground=ACCENT, selectforeground=WHITE,
            relief="flat", borderwidth=0, activestyle="none",
        )
        self._sent_lb.pack(fill="both", expand=True, padx=4, pady=4)
        self._sent_lb.bind("<<ListboxSelect>>", self._select_sent)

        vf = tk.Frame(pane, bg=PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(vf, minsize=300)

        self._sent_view = scrolledtext.ScrolledText(
            vf, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            borderwidth=0, state="disabled", wrap="word",
        )
        self._sent_view.pack(fill="both", expand=True, padx=6, pady=6)

    # ── Generic mail tab (Inbox / Spam) with threaded list ────────────────────

    def _build_mail_tab(self, f, folder: str):
        label = "Inbox" if folder == "inbox" else "Spam"
        icon  = "📥"   if folder == "inbox" else "🚫"
        color = WHITE  if folder == "inbox" else ORANGE

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=20, pady=(10, 6))
        tk.Label(top, text=f"{icon}  {label}", font=FONT_H,
                 bg=BG, fg=color).pack(side="left")
        _btn(top, "  ↻  Refresh  ",
             lambda fd=folder: self._fetch(fd),
             fg=GREEN, bg=PANEL).pack(side="right")

        pane = tk.PanedWindow(f, orient="horizontal", bg=BG,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        lf = tk.Frame(pane, bg=PANEL, width=300,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(lf, minsize=200)

        lb = tk.Listbox(
            lf, font=FONT_S, bg=PANEL, fg=WHITE,
            selectbackground=ACCENT, selectforeground=WHITE,
            relief="flat", borderwidth=0, activestyle="none",
        )
        lb.pack(fill="both", expand=True, padx=4, pady=4)
        lb.bind("<<ListboxSelect>>",
                lambda evt, fd=folder: self._select_email(evt, fd))

        vf = tk.Frame(pane, bg=PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(vf, minsize=300)

        view = scrolledtext.ScrolledText(
            vf, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            borderwidth=0, state="disabled", wrap="word",
        )
        view.pack(fill="both", expand=True, padx=6, pady=(6, 4))

        act = tk.Frame(vf, bg=PANEL)
        act.pack(fill="x", padx=6, pady=(0, 6))

        reply_btn = _btn(act, "  ↩  Reply  ",
                         lambda fd=folder: self._reply(fd),
                         fg=WHITE, bg=ACCENT)
        reply_btn.pack(side="left", padx=(0, 6))

        delete_btn = _btn(act, "  🗑  Delete  ",
                          lambda fd=folder: self._delete(fd),
                          fg=WHITE, bg=RED)
        delete_btn.pack(side="left")

        setattr(self, f"_{folder}_lb",         lb)
        setattr(self, f"_{folder}_view",        view)
        setattr(self, f"_{folder}_reply_btn",   reply_btn)
        setattr(self, f"_{folder}_delete_btn",  delete_btn)

        reply_btn.config(state="disabled")
        delete_btn.config(state="disabled")

    # ── Cache: load on login ──────────────────────────────────────────────────

    def _load_from_cache(self):
        for folder in ("inbox", "spam"):
            cached = load_cache(self._email, folder)
            if cached:
                self._set_emails(folder, cached)
                self._populate(folder)
                self._set_status(
                    f"Showing {len(cached)} cached {folder} message(s). "
                    "Hit Refresh to fetch latest.", MUTED)

        # Sent tab: load from local Sent cache
        sent = load_sent(self._email)
        if sent:
            self._sent_emails = sent
            self._populate_sent()
            self._set_status(
                f"Loaded {len(sent)} sent message(s) from local cache.", MUTED)

    # ── Network fetch ─────────────────────────────────────────────────────────

    def _fetch(self, folder: str):
        self._set_status(f"Fetching {folder}…", YELLOW)

        def _work():
            ok, result = fetch_emails(self._email, self._password, folder)
            if ok:
                self.after(0, lambda r=result, fd=folder: self._on_fetch_ok(r, fd))
            else:
                self.after(0, lambda r=result, fd=folder: (
                    messagebox.showerror("Fetch Failed", r),
                    self._set_status(f"Fetch failed: {r}", RED),
                ))

        threading.Thread(target=_work, daemon=True).start()

    def _on_fetch_ok(self, emails: list, folder: str):
        self._set_emails(folder, emails)
        save_cache(self._email, folder, emails)
        self._populate(folder)
        count = len(emails)
        self._set_status(
            f"{count} message(s) in {folder}." if count
            else f"{folder.capitalize()} is empty.")

    # ── Email list helpers ────────────────────────────────────────────────────

    def _get_emails(self, folder: str) -> list:
        return self._inbox_emails if folder == "inbox" else self._spam_emails

    def _set_emails(self, folder: str, emails: list):
        if folder == "inbox":
            self._inbox_emails = emails
            self._inbox_threads = _thread_emails(emails)
        else:
            self._spam_emails  = emails
            self._spam_threads = _thread_emails(emails)

    def _get_threads(self, folder: str) -> list:
        return self._inbox_threads if folder == "inbox" else self._spam_threads

    # ── Populate threaded listbox ─────────────────────────────────────────────

    def _populate(self, folder: str):
        """
        Fill the listbox with a threaded view.
        We store a parallel map: listbox row index → (thread_idx, reply_idx or None)
        """
        lb      = getattr(self, f"_{folder}_lb")
        threads = self._get_threads(folder)

        lb.delete(0, tk.END)
        # row_map: list-row-index → {"thread": int, "reply": int|None}
        row_map = []

        if not threads:
            lb.insert(tk.END, "  (empty)")
            setattr(self, f"_{folder}_row_map", [])
            getattr(self, f"_{folder}_reply_btn").config(state="disabled")
            getattr(self, f"_{folder}_delete_btn").config(state="disabled")
            return

        for t_idx, thread in enumerate(threads):
            root_em = thread["email"]
            h       = _parse_headers(root_em["raw"])
            frm     = h["from"] or "(unknown)"
            subj    = h["subject"] or "(no subject)"
            label   = f" ✉ #{root_em['index']}  {frm}  —  {subj}"[:72]
            lb.insert(tk.END, label)
            lb.itemconfig(tk.END, fg=WHITE)
            row_map.append({"thread": t_idx, "reply": None})

            for r_idx, reply_em in enumerate(thread["replies"]):
                rh    = _parse_headers(reply_em["raw"])
                rfrm  = rh["from"] or "(unknown)"
                rsubj = rh["subject"] or "(no subject)"
                rlabel = f"    ↳ #{reply_em['index']}  {rfrm}  —  {rsubj}"[:72]
                lb.insert(tk.END, rlabel)
                lb.itemconfig(tk.END, fg=MUTED)
                row_map.append({"thread": t_idx, "reply": r_idx})

        setattr(self, f"_{folder}_row_map", row_map)
        getattr(self, f"_{folder}_reply_btn").config(state="disabled")
        getattr(self, f"_{folder}_delete_btn").config(state="disabled")

    # ── Populate Sent listbox ─────────────────────────────────────────────────

    def _populate_sent(self):
        self._sent_lb.delete(0, tk.END)
        if not self._sent_emails:
            self._sent_lb.insert(tk.END, "  (no sent messages)")
            return
        for em in self._sent_emails:
            h     = _parse_headers(em["raw"])
            to_   = h["to"] or "(unknown recipient)"
            subj  = h["subject"] or "(no subject)"
            label = f" ✉ #{em['index']}  To: {to_}  —  {subj}"[:72]
            self._sent_lb.insert(tk.END, label)

    # ── Email selection ───────────────────────────────────────────────────────

    def _select_email(self, _event, folder: str):
        lb      = getattr(self, f"_{folder}_lb")
        row_map = getattr(self, f"_{folder}_row_map", [])
        threads = self._get_threads(folder)
        sel     = lb.curselection()

        if not sel or not threads:
            return

        row_idx = sel[0]
        if row_idx >= len(row_map):
            return

        mapping = row_map[row_idx]
        t_idx   = mapping["thread"]
        r_idx   = mapping["reply"]   # None → root; int → reply

        self._sel_folder   = folder
        self._sel_list_idx = row_idx
        self._sel_is_reply = r_idx is not None

        thread = threads[t_idx]
        if r_idx is None:
            em = thread["email"]
        else:
            em = thread["replies"][r_idx]

        # Display the selected email in the viewer
        view = getattr(self, f"_{folder}_view")
        view.config(state="normal")
        view.delete("1.0", tk.END)

        # If showing a root with replies, show a conversation header
        if r_idx is None and thread["replies"]:
            reply_count = len(thread["replies"])
            view.insert(tk.END,
                f"── Conversation ({reply_count + 1} message"
                f"{'s' if reply_count else ''}) ──\n\n",
            )

        view.insert(tk.END, em["raw"])
        view.config(state="disabled")

        getattr(self, f"_{folder}_reply_btn").config(state="normal")
        getattr(self, f"_{folder}_delete_btn").config(state="normal")

        # Store selected email for reply/delete actions
        setattr(self, f"_{folder}_selected_email", em)

    def _select_sent(self, _event):
        sel = self._sent_lb.curselection()
        if not sel or not self._sent_emails:
            return
        idx = sel[0]
        if idx >= len(self._sent_emails):
            return
        em = self._sent_emails[idx]
        self._sent_view.config(state="normal")
        self._sent_view.delete("1.0", tk.END)
        self._sent_view.insert(tk.END, em["raw"])
        self._sent_view.config(state="disabled")

    # ── Compose helpers ───────────────────────────────────────────────────────

    def _send(self):
        to      = self._to.get().strip()
        cc      = self._cc.get().strip()
        bcc     = self._bcc.get().strip()
        subject = self._subj.get().strip() or "(no subject)"
        body    = self._body.get("1.0", tk.END).strip()
        in_reply_to = self._reply_to_msg_id

        if not to or not body:
            messagebox.showwarning("Missing Fields",
                                   "Please fill in 'To' and 'Message'.")
            return
        self._set_status("Sending…", YELLOW)

        def _work():
            ok, result = send_email(
                self._email, to, subject, body,
                cc=cc, bcc=bcc, in_reply_to=in_reply_to,
            )
            if ok:
                # result is the sent_dict on success
                sent_dict = result
                # Save to Sent cache
                append_sent(self._email, sent_dict)
                self._sent_emails = load_sent(self._email)

                def _after():
                    # Update Sent tab
                    self._populate_sent()
                    messagebox.showinfo("Sent ✓", "Email sent successfully.")
                    self._set_status(f"Sent to {to}.", GREEN)
                    self._clear_compose()

                self.after(0, _after)
            else:
                self.after(0, lambda: (
                    messagebox.showerror("Send Failed", result),
                    self._set_status(f"Failed: {result}", RED),
                ))

        threading.Thread(target=_work, daemon=True).start()

    def _clear_compose(self):
        self._to.delete(0, tk.END)
        self._cc.delete(0, tk.END)
        self._bcc.delete(0, tk.END)
        self._subj.delete(0, tk.END)
        self._body.delete("1.0", tk.END)
        self._reply_to_msg_id = ""
        self._reply_ctx_var.set("")

    # ── Reply ─────────────────────────────────────────────────────────────────

    def _reply(self, folder: str):
        em = getattr(self, f"_{folder}_selected_email", None)
        if em is None:
            messagebox.showwarning("Reply", "Please select an email to reply to.")
            return

        headers = _parse_headers(em["raw"])
        to_addr = headers["from"]
        subject = headers["subject"]
        msg_id  = headers.get("message_id") or em.get("message_id", "")

        reply_subj = (
            subject if subject.lower().startswith("re:")
            else f"Re: {subject}"
        )

        # Store the Message-ID so send_email can attach In-Reply-To
        self._reply_to_msg_id = msg_id

        self._to.delete(0, tk.END)
        self._to.insert(0, to_addr)
        self._cc.delete(0, tk.END)
        self._bcc.delete(0, tk.END)
        self._subj.delete(0, tk.END)
        self._subj.insert(0, reply_subj)
        self._body.delete("1.0", tk.END)

        # Show a subtle "Replying to …" context note
        ctx = f"↩  Replying to: {to_addr}"
        if msg_id:
            ctx += f"  (In-Reply-To: {msg_id})"
        self._reply_ctx_var.set(ctx)

        self._nb.select(0)   # switch to Compose tab
        self._to.focus()
        self._set_status(f"Replying to {to_addr}…", ACCENT)

    # ── Delete ────────────────────────────────────────────────────────────────

    def _delete(self, folder: str):
        em = getattr(self, f"_{folder}_selected_email", None)
        if em is None:
            messagebox.showwarning("Delete", "Please select an email to delete.")
            return

        msg_index = em["index"]

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete message #{msg_index} from {folder}?\n\n"
            "This will remove it from the server and your local cache."
        ):
            return

        # ── 1. Remove from local email list and rebuild threads ───────────────
        emails = self._get_emails(folder)
        emails = [e for e in emails if e["index"] != msg_index]
        for i, e in enumerate(emails, 1):
            e["index"] = i
        self._set_emails(folder, emails)
        self._populate(folder)

        # Clear the viewer
        view = getattr(self, f"_{folder}_view")
        view.config(state="normal")
        view.delete("1.0", tk.END)
        view.config(state="disabled")
        setattr(self, f"_{folder}_selected_email", None)
        self._sel_list_idx = -1

        # ── 2. Remove from local cache ────────────────────────────────────────
        delete_from_cache(self._email, folder, msg_index)

        # ── 3. Send delete command to Node 4 (async) ─────────────────────────
        self._set_status(f"Deleting message #{msg_index} from server…", YELLOW)

        def _work():
            ok, result = delete_email(
                self._email, self._password, folder, msg_index
            )
            if ok:
                self.after(0, lambda: self._set_status(
                    f"Message #{msg_index} permanently deleted.", GREEN))
            else:
                self.after(0, lambda: (
                    messagebox.showwarning(
                        "Server Delete Warning",
                        f"Email removed locally but server reported:\n{result}\n\n"
                        "It may still exist on the server — try Refresh."
                    ),
                    self._set_status(f"Server delete issue: {result}", ORANGE),
                ))

        threading.Thread(target=_work, daemon=True).start()

    # ── Logout ────────────────────────────────────────────────────────────────

    def _do_logout(self):
        if messagebox.askyesno("Logout", f"Log out of {self._email}?"):
            self._logout()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str, color=GREEN):
        self._sv.set(msg)
        self._sb.config(fg=color)


# ─────────────────────────────────────────────────────────────────────────────
# ROOT CONTROLLER
# ─────────────────────────────────────────────────────────────────────────────

class SecureMailController:
    """Manages transitions: LoginScreen ↔ MainApp."""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SecureMail")
        self.root.configure(bg=BG)
        self.root.geometry("1060x740")
        self._frame = None
        self._show_login()

    def _show_login(self):
        self._switch(LoginScreen(self.root, self._show_main))

    def _show_main(self, email, password):
        self._switch(MainApp(self.root, email, password, self._show_login))

    def _switch(self, new: tk.Frame):
        if self._frame:
            self._frame.destroy()
        self._frame = new
        new.pack(fill="both", expand=True)


if __name__ == "__main__":
    root = tk.Tk()
    SecureMailController(root)
    root.mainloop()

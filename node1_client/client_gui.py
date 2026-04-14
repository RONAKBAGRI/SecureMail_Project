"""
Node 1 – SecureMail GUI (Prashant)
====================================
Flow: LoginScreen → MainApp → (logout) → LoginScreen

New features in this version:
  • Spam tab   – fetches from the spam folder on Node 4
  • Offline cache – emails loaded from local JSON cache on login;
                    cache updated on every successful network Refresh
  • Reply      – pre-fills Compose from selected email's From/Subject
  • Delete     – removes from GUI, local cache, Node 4 storage, Node 3 storage
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
from local_cache      import save_cache, load_cache, delete_from_cache

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

FONT   = ("TkDefaultFont", 10)
FONT_B = ("TkDefaultFont", 10, "bold")
FONT_H = ("TkDefaultFont", 15, "bold")
FONT_S = ("TkDefaultFont", 9)


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
    """Extract From, To, and Subject from a raw email string."""
    headers = {"from": "", "to": "", "subject": ""}
    for line in raw.replace("\r\n", "\n").split("\n"):
        low = line.lower()
        if low.startswith("from:"):
            headers["from"] = line[5:].strip()
        elif low.startswith("to:"):
            headers["to"] = line[3:].strip()
        elif low.startswith("subject:"):
            headers["subject"] = line[8:].strip()
        elif not line.strip():
            break  # end of header block
    return headers


def _list_preview(email: dict) -> str:
    """One-line summary for the email list panel."""
    h = _parse_headers(email["raw"])
    frm  = h["from"] or "(unknown sender)"
    subj = h["subject"] or "(no subject)"
    return f" #{email['index']}  {frm}  —  {subj}"[:72]


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
            # Verify credentials against the live POP3 server
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

        # Per-folder email lists
        self._inbox_emails: list = []
        self._spam_emails:  list = []

        # Currently selected (folder, list-row index)
        self._sel_folder:   str = "inbox"
        self._sel_list_idx: int = -1

        self._build()
        self._load_from_cache()   # show cached mail immediately, before network

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

        self._nb.add(ct, text="  ✉  Compose  ")
        self._nb.add(it, text="  📥  Inbox  ")
        self._nb.add(st, text="  🚫  Spam  ")

        self._build_compose(ct)
        self._build_mail_tab(it, "inbox")
        self._build_mail_tab(st, "spam")

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
        self._lbl(f, "To:")
        self._to = _entry(f)
        self._to.pack(fill="x", padx=20, ipady=4)

        self._lbl(f, "Subject:")
        self._subj = _entry(f)
        self._subj.pack(fill="x", padx=20, ipady=4)

        self._lbl(f, "Message:")
        self._body = tk.Text(
            f, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            highlightthickness=1, highlightcolor=ACCENT,
            highlightbackground=BORDER, height=14,
        )
        self._body.pack(fill="both", expand=True, padx=20, pady=(2, 10))

        row = tk.Frame(f, bg=BG)
        row.pack(pady=6)
        _btn(row, "  ✈  Send  ", self._send,
             fg=WHITE, bg=ACCENT).pack(side="left", padx=6)
        _btn(row, "  Clear  ", self._clear_compose,
             fg=MUTED, bg=PANEL).pack(side="left", padx=6)

    # ── Generic mail tab (Inbox / Spam) ───────────────────────────────────────

    def _build_mail_tab(self, f, folder: str):
        """
        Builds an identical layout for both Inbox and Spam tabs.
        Stores widget references with folder-prefixed attribute names.
        """
        label = "Inbox" if folder == "inbox" else "Spam"
        icon  = "📥"   if folder == "inbox" else "🚫"
        color = WHITE  if folder == "inbox" else ORANGE

        # ── Top bar ────────────────────────────────────────────────────────────
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=20, pady=(10, 6))
        tk.Label(top, text=f"{icon}  {label}", font=FONT_H,
                 bg=BG, fg=color).pack(side="left")
        _btn(top, "  ↻  Refresh  ",
             lambda fd=folder: self._fetch(fd),
             fg=GREEN, bg=PANEL).pack(side="right")

        # ── Paned window: list | viewer ───────────────────────────────────────
        pane = tk.PanedWindow(f, orient="horizontal", bg=BG,
                              sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Left: email list
        lf = tk.Frame(pane, bg=PANEL, width=280,
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

        # Right: viewer + action buttons
        vf = tk.Frame(pane, bg=PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(vf, minsize=300)

        view = scrolledtext.ScrolledText(
            vf, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            borderwidth=0, state="disabled", wrap="word",
        )
        view.pack(fill="both", expand=True, padx=6, pady=(6, 4))

        # Action buttons row (Reply / Delete)
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

        # Store widget refs using folder-prefixed names
        setattr(self, f"_{folder}_lb",         lb)
        setattr(self, f"_{folder}_view",        view)
        setattr(self, f"_{folder}_reply_btn",   reply_btn)
        setattr(self, f"_{folder}_delete_btn",  delete_btn)

        # Disable action buttons until an email is selected
        reply_btn.config(state="disabled")
        delete_btn.config(state="disabled")

    # ── Cache: load on login ──────────────────────────────────────────────────

    def _load_from_cache(self):
        """Populate both tabs from local cache immediately after login."""
        for folder in ("inbox", "spam"):
            cached = load_cache(self._email, folder)
            if cached:
                self._set_emails(folder, cached)
                self._populate(folder)
                self._set_status(
                    f"Showing {len(cached)} cached {folder} message(s). "
                    "Hit Refresh to fetch latest.", MUTED)

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
        save_cache(self._email, folder, emails)   # persist to local cache
        self._populate(folder)
        count = len(emails)
        self._set_status(
            f"{count} message(s) in {folder}." if count
            else f"{folder.capitalize()} is empty.")

    # ── Populate listbox ──────────────────────────────────────────────────────

    def _get_emails(self, folder: str) -> list:
        return self._inbox_emails if folder == "inbox" else self._spam_emails

    def _set_emails(self, folder: str, emails: list):
        if folder == "inbox":
            self._inbox_emails = emails
        else:
            self._spam_emails = emails

    def _populate(self, folder: str):
        lb    = getattr(self, f"_{folder}_lb")
        emails = self._get_emails(folder)

        lb.delete(0, tk.END)
        if not emails:
            lb.insert(tk.END, f"  (empty {folder})")
            return
        for em in emails:
            lb.insert(tk.END, _list_preview(em))

        # Reset action buttons
        getattr(self, f"_{folder}_reply_btn").config(state="disabled")
        getattr(self, f"_{folder}_delete_btn").config(state="disabled")

    # ── Email selection ───────────────────────────────────────────────────────

    def _select_email(self, _event, folder: str):
        lb     = getattr(self, f"_{folder}_lb")
        emails = self._get_emails(folder)
        sel    = lb.curselection()

        if not sel or not emails:
            return

        list_idx = sel[0]
        if list_idx >= len(emails):
            return

        self._sel_folder   = folder
        self._sel_list_idx = list_idx

        view = getattr(self, f"_{folder}_view")
        view.config(state="normal")
        view.delete("1.0", tk.END)
        view.insert(tk.END, emails[list_idx]["raw"])
        view.config(state="disabled")

        # Enable action buttons now that something is selected
        getattr(self, f"_{folder}_reply_btn").config(state="normal")
        getattr(self, f"_{folder}_delete_btn").config(state="normal")

    # ── Compose helpers ───────────────────────────────────────────────────────

    def _send(self):
        to      = self._to.get().strip()
        subject = self._subj.get().strip() or "(no subject)"
        body    = self._body.get("1.0", tk.END).strip()
        if not to or not body:
            messagebox.showwarning("Missing Fields",
                                   "Please fill in 'To' and 'Message'.")
            return
        self._set_status("Sending…", YELLOW)

        def _work():
            ok, msg = send_email(self._email, to, subject, body)
            if ok:
                self.after(0, lambda: (
                    messagebox.showinfo("Sent ✓", msg),
                    self._set_status(f"Sent to {to}.", GREEN),
                    self._clear_compose(),
                ))
            else:
                self.after(0, lambda: (
                    messagebox.showerror("Send Failed", msg),
                    self._set_status(f"Failed: {msg}", RED),
                ))

        threading.Thread(target=_work, daemon=True).start()

    def _clear_compose(self):
        self._to.delete(0, tk.END)
        self._subj.delete(0, tk.END)
        self._body.delete("1.0", tk.END)

    # ── Reply ─────────────────────────────────────────────────────────────────

    def _reply(self, folder: str):
        emails   = self._get_emails(folder)
        list_idx = self._sel_list_idx

        if list_idx < 0 or list_idx >= len(emails):
            messagebox.showwarning("Reply", "Please select an email to reply to.")
            return

        raw     = emails[list_idx]["raw"]
        headers = _parse_headers(raw)
        to_addr = headers["from"]
        subject = headers["subject"]
        reply_subj = (
            subject if subject.lower().startswith("re:")
            else f"Re: {subject}"
        )

        # Pre-fill Compose tab and switch to it
        self._to.delete(0, tk.END)
        self._to.insert(0, to_addr)
        self._subj.delete(0, tk.END)
        self._subj.insert(0, reply_subj)
        self._body.delete("1.0", tk.END)

        self._nb.select(0)   # switch to Compose tab (index 0)
        self._to.focus()
        self._set_status(f"Replying to {to_addr}…", ACCENT)

    # ── Delete ────────────────────────────────────────────────────────────────

    def _delete(self, folder: str):
        emails   = self._get_emails(folder)
        list_idx = self._sel_list_idx

        if list_idx < 0 or list_idx >= len(emails):
            messagebox.showwarning("Delete", "Please select an email to delete.")
            return

        msg_index = emails[list_idx]["index"]

        if not messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete message #{msg_index} from {folder}?\n\n"
            "This will remove it from the server and your local cache."
        ):
            return

        # ── 1. Remove from GUI immediately (optimistic UI) ────────────────────
        emails.pop(list_idx)
        # Re-number remaining emails so indices stay contiguous
        for i, e in enumerate(emails, 1):
            e["index"] = i
        self._set_emails(folder, emails)
        self._populate(folder)

        # Clear the viewer
        view = getattr(self, f"_{folder}_view")
        view.config(state="normal")
        view.delete("1.0", tk.END)
        view.config(state="disabled")

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
        self.root.geometry("980x700")
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

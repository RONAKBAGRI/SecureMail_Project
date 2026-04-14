"""
Node 1 – SecureMail GUI (Prashant)
Flow: LoginScreen → MainApp → (logout) → LoginScreen
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tcp_smtp_sender import send_email
from tcp_pop3_fetcher import fetch_emails
from auth_client import register_user

# ── Palette ───────────────────────────────────────────────────────────────────
BG     = "#0d1117"
PANEL  = "#161b22"
BORDER = "#30363d"
ACCENT = "#1f6feb"
GREEN  = "#3fb950"
RED    = "#f85149"
YELLOW = "#d29922"
WHITE  = "#e6edf3"
MUTED  = "#8b949e"

FONT   = ("Courier New", 10)
FONT_B = ("Courier New", 10, "bold")
FONT_H = ("Courier New", 15, "bold")
FONT_S = ("Courier New", 9)


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
            tk.Label(pad, text=label, font=FONT_S,
                     bg=BG, fg=MUTED).pack(anchor="w")
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

        tk.Label(wrap, text="◉  SecureMail", font=("Courier New", 22, "bold"),
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
        self._emails   = []
        self._build()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=PANEL,
                       highlightthickness=1, highlightbackground=BORDER)
        hdr.pack(fill="x")
        tk.Label(hdr, text="◉  SecureMail", font=("Courier New", 13, "bold"),
                 bg=PANEL, fg=GREEN, padx=16, pady=8).pack(side="left")
        tk.Label(hdr, text=self._email, font=FONT_S,
                 bg=PANEL, fg=MUTED, padx=6).pack(side="left")
        _btn(hdr, "Logout", self._do_logout,
             fg=RED, bg=PANEL).pack(side="right", padx=12, pady=6)

        # Tabs
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                         font=FONT_B, padding=[16, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", WHITE)])

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        ct = tk.Frame(nb, bg=BG)
        it = tk.Frame(nb, bg=BG)
        nb.add(ct, text="  ✉  Compose  ")
        nb.add(it, text="  📥  Inbox  ")

        self._build_compose(ct)
        self._build_inbox(it)

        # Status bar
        self._sv = tk.StringVar(value="Ready.")
        self._sb = tk.Label(self, textvariable=self._sv, font=FONT_S,
                            bg=PANEL, fg=GREEN, anchor="w", pady=4, padx=12)
        self._sb.pack(fill="x", side="bottom")

    # ── Compose ───────────────────────────────────────────────────────────────

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
        _btn(row, "  Clear  ", self._clear,
             fg=MUTED, bg=PANEL).pack(side="left", padx=6)

    # ── Inbox ─────────────────────────────────────────────────────────────────

    def _build_inbox(self, f):
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x", padx=20, pady=(10, 6))
        tk.Label(top, text="Inbox", font=FONT_H,
                 bg=BG, fg=WHITE).pack(side="left")
        _btn(top, "  ↻  Refresh  ", self._fetch,
             fg=GREEN, bg=PANEL).pack(side="right")

        pane = tk.PanedWindow(f, orient="horizontal", bg=BG,
                               sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        lf = tk.Frame(pane, bg=PANEL, width=260,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(lf, minsize=200)
        self._lb = tk.Listbox(
            lf, font=FONT_S, bg=PANEL, fg=WHITE,
            selectbackground=ACCENT, selectforeground=WHITE,
            relief="flat", borderwidth=0, activestyle="none",
        )
        self._lb.pack(fill="both", expand=True, padx=4, pady=4)
        self._lb.bind("<<ListboxSelect>>", self._select)

        vf = tk.Frame(pane, bg=PANEL,
                      highlightthickness=1, highlightbackground=BORDER)
        pane.add(vf, minsize=300)
        self._view = scrolledtext.ScrolledText(
            vf, font=FONT, bg=PANEL, fg=WHITE,
            insertbackground=WHITE, relief="flat",
            borderwidth=0, state="disabled", wrap="word",
        )
        self._view.pack(fill="both", expand=True, padx=6, pady=6)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _status(self, msg, color=GREEN):
        self._sv.set(msg)
        self._sb.config(fg=color)

    def _send(self):
        to      = self._to.get().strip()
        subject = self._subj.get().strip() or "(no subject)"
        body    = self._body.get("1.0", tk.END).strip()
        if not to or not body:
            messagebox.showwarning("Missing Fields", "Please fill in 'To' and 'Message'.")
            return
        self._status("Sending…", YELLOW)

        def _work():
            ok, msg = send_email(self._email, to, subject, body)
            if ok:
                self.after(0, lambda: (
                    messagebox.showinfo("Sent ✓", msg),
                    self._status(f"Sent to {to}.", GREEN),
                    self._clear(),
                ))
            else:
                self.after(0, lambda: (
                    messagebox.showerror("Send Failed", msg),
                    self._status(f"Failed: {msg}", RED),
                ))

        threading.Thread(target=_work, daemon=True).start()

    def _fetch(self):
        self._status("Fetching inbox…", YELLOW)

        def _work():
            ok, result = fetch_emails(self._email, self._password)
            if ok:
                self._emails = result
                self.after(0, self._populate)
                self.after(0, lambda: self._status(
                    f"{len(result)} message(s) in inbox."))
            else:
                self.after(0, lambda: (
                    messagebox.showerror("Fetch Failed", result),
                    self._status(f"Failed: {result}", RED),
                ))

        threading.Thread(target=_work, daemon=True).start()

    def _populate(self):
        self._lb.delete(0, tk.END)
        if not self._emails:
            self._lb.insert(tk.END, "  (empty inbox)")
            return
        for em in self._emails:
            preview = em["raw"].replace("\r\n", " ").replace("\n", " ")[:55]
            self._lb.insert(tk.END, f" #{em['index']}  {preview}…")

    def _select(self, _event):
        sel = self._lb.curselection()
        if not sel or not self._emails:
            return
        idx = sel[0]
        if idx >= len(self._emails):
            return
        self._view.config(state="normal")
        self._view.delete("1.0", tk.END)
        self._view.insert(tk.END, self._emails[idx]["raw"])
        self._view.config(state="disabled")

    def _clear(self):
        self._to.delete(0, tk.END)
        self._subj.delete(0, tk.END)
        self._body.delete("1.0", tk.END)

    def _do_logout(self):
        if messagebox.askyesno("Logout", f"Log out of {self._email}?"):
            self._logout()


# ─────────────────────────────────────────────────────────────────────────────
# ROOT CONTROLLER
# ─────────────────────────────────────────────────────────────────────────────

class SecureMailController:
    """Manages transitions: LoginScreen ↔ MainApp."""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SecureMail")
        self.root.configure(bg=BG)
        self.root.geometry("940x680")
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
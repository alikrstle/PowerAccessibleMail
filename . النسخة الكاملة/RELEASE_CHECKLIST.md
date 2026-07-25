# Power Accessible Mail Release Checklist

- No `accounts.json` in the release folder.
- No `messages.sqlite3` in the release folder.
- No `.mail_store` in the release folder.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- Build is made with 64-bit Python.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Installer uses per-user install path and does not require administrator privileges.


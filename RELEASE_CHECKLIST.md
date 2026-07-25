# Power Accessible Mail Release Checklist

- No `accounts.json` in the release folder.
- No `messages.sqlite3` in the release folder.
- No `.mail_store` in the release folder.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- Build is made with 64-bit Python.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Installer uses per-user install path and does not require administrator privileges.
- Executable and installer contain consistent company, product, and version metadata.
- The limited edition bundles only the `google_gmail_api` OAuth client.
- Installer, portable ZIP, and application executable are listed in the edition SHA-256 manifest.
- Installer offers Arabic and English and keeps the destination, tasks, ready, and finished pages enabled.
- Desktop shortcut is selected by default.
- Finished page offers the localized README and application launch as separate options.

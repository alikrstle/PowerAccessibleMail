# Power Accessible Mail Release Checklist

- No `accounts.json` in the release folder.
- No `messages.sqlite3` in the release folder.
- No `.mail_store` in the release folder.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- Build is made with 64-bit Python.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Installer uses per-user install path and does not require administrator privileges.
- GitHub release tag uses the `v1.2.9` form and matches the application version.
- Full installer asset uses `PowerAccessibleMailFullSetup-<version>-win-x64-UNSIGNED.exe` until an Authenticode certificate is available.
- GitHub release is published and is neither a draft nor a pre-release.

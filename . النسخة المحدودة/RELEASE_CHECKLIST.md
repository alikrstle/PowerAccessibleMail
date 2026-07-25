# Power Accessible Mail Release Checklist

- No `accounts.json` in the release folder.
- No `messages.sqlite3` in the release folder.
- No `.mail_store` in the release folder.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- Build is made with 64-bit Python.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Installer uses per-user install path and does not require administrator privileges.
- Google Auth Platform app name is `Power Accessible Mail`.
- Gmail API is enabled in the same Google Cloud project as the limited OAuth client.
- Data Access contains `https://www.googleapis.com/auth/gmail.modify`.
- The packaged `google_gmail_api` client ID matches the limited desktop client.
- Every tester's exact Gmail address is listed under `Audience > Test users`.
- Testers are told that Google shows an unverified-app warning in Testing status and that test authorization expires after seven days.

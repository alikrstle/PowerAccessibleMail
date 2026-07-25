# OAuth Scope Justification

App name: Power Accessible Mail

## Requested scopes for the original IMAP/SMTP version

- `openid`
- `email`
- `profile`
- `https://mail.google.com/`

## Justification for `openid`, `email`, and `profile`

These scopes are used to identify the signed-in Google account and display the correct account label inside the desktop application. The app uses the user's email address as the mailbox username and to distinguish multiple accounts added by the same user.

## Justification for `https://mail.google.com/`

Power Accessible Mail is a desktop email client for blind and screen-reader users. The current version connects to Gmail through IMAP and SMTP using XOAUTH2. Gmail IMAP/SMTP OAuth requires the `https://mail.google.com/` scope so the app can authenticate to Gmail's IMAP and SMTP servers.

The scope is used only for user-facing email features:

- Listing messages in the inbox, spam/junk folder, and sent folder.
- Reading selected message content in an accessible text viewer.
- Showing message links and attachments in an accessible list.
- Marking messages as read after the user opens them.
- Sending new email messages and replies through SMTP.
- Caching messages locally in encrypted storage on the user's Windows device for faster loading.

The app does not permanently delete Gmail messages, does not access mail for advertising or analytics, and does not transfer Gmail content to developer servers.

## Why narrower scopes are not used in the current version

The current application uses IMAP and SMTP instead of the Gmail REST API. IMAP and SMTP authentication with Gmail XOAUTH2 uses the `https://mail.google.com/` OAuth scope. Narrower Gmail REST API scopes such as `gmail.readonly`, `gmail.modify`, or `gmail.send` would require replacing the mail engine with Gmail API calls. That change is planned as a future privacy improvement, but the current released desktop build requires IMAP and SMTP compatibility.

## Data handling summary

Gmail data is stored only on the user's device. Cached message data is encrypted locally using Windows DPAPI. The developer does not receive or store Gmail message content, attachments, or OAuth tokens on a server.

## Alternative limited Gmail API version

Power Accessible Mail also has a Gmail API based build that does not use IMAP or SMTP. That build uses:

- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/gmail.modify`

The `gmail.modify` scope is used to list messages, read selected messages, retrieve attachments, remove the `UNREAD` label when the user opens a message, and send messages through Gmail API. This version does not request `https://mail.google.com/` and does not request permission for immediate permanent deletion outside trash.

The Gmail API limited build uses a separate OAuth desktop client and file from the original IMAP/SMTP build. The full build reads `google` from `. النسخة الكاملة/oauth_clients.json`, while the limited build reads `google_gmail_api` from `. النسخة المحدودة/oauth_clients.json`.

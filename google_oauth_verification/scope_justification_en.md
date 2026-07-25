# OAuth Scope Justification

App name: Power Accessible Mail

## Requested scopes

- `openid`
- `email`
- `profile`
- `https://www.googleapis.com/auth/gmail.modify`

## Identity scopes

The `openid`, `email`, and `profile` scopes identify the signed-in Google account, display its label, and distinguish multiple accounts added by the same user.

## Gmail scope

Power Accessible Mail is a Windows desktop email client designed for blind and screen-reader users. It uses Gmail API directly and requests `gmail.modify` for these user-facing actions:

- List Inbox, Spam, Sent, All Mail, Starred, Unread, Read, and Trash messages.
- Read a message selected by the user and retrieve its attachments.
- Send new messages and replies.
- Mark messages read or unread.
- Add or remove the Starred label.
- Move selected messages to Gmail Trash.

The app does not request `https://mail.google.com/` and does not permanently delete messages outside Trash. It does not use Gmail data for advertising, analytics, profiling, or AI training.

## Data handling

Gmail data and OAuth tokens are stored only on the user's Windows device. Cached message data is encrypted with Windows DPAPI for the current Windows account. The developer does not receive or store Gmail content or OAuth tokens on a server.

Message text is sent to Google Translate only when the user explicitly invokes the translation command. Translation is optional and is not performed in the background.

The x64 and x86 packages have identical features and use the same OAuth desktop client and scopes.

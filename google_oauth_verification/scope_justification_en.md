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

## Why narrower Gmail scopes are insufficient

`gmail.send` would allow sending but would not let the app list or read the user's mailbox. `gmail.readonly` would allow reading but would not let the user change read state, add or remove the Starred label, or move a selected message to Trash. Combining `gmail.send` and `gmail.readonly` would still not provide those message-management actions. Power Accessible Mail therefore requests `gmail.modify` as the narrowest Gmail scope that supports the complete, user-visible email-client functionality described above.

## Data handling

Gmail data and OAuth tokens are stored only on the user's Windows device. Cached message data is encrypted with Windows DPAPI for the current Windows account. The developer does not receive or store Gmail content or OAuth tokens on a server.

Message text is sent directly from the user's device to the official Google Translate service only when the user explicitly invokes the translation command. Before the first transfer, the app displays an accessible notice explaining what will be sent and provides Allow and Cancel choices. After the user chooses Allow, that choice is saved and the notice is not shown again. Translation is optional and is not performed in the background. Attachments and OAuth tokens are not sent for translation, and no developer-controlled server receives the message text.

The x64 and x86 packages have identical features and use the same OAuth desktop client and scopes.

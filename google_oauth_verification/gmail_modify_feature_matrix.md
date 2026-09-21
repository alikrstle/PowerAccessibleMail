# Gmail Modify Feature Matrix

App: Power Accessible Mail
Requested Gmail scope: `https://www.googleapis.com/auth/gmail.modify`

This matrix records the production features that currently use Gmail API. It must remain aligned with the application code, the Google Cloud scope configuration, the consent screen, and the verification video.

| User-facing feature | Gmail API operation | Account impact | Evidence required in the new video |
| --- | --- | --- | --- |
| Refresh Inbox, Spam, Sent, All Mail, and Trash | `GET /gmail/v1/users/me/messages` with the matching Gmail label | Read-only | Show the mailbox sections loading real test messages. |
| Open and read a selected message | `GET /gmail/v1/users/me/messages/{id}?format=full` | Read-only | Open a uniquely named test message and show its sender, subject, and body. |
| Retrieve an attachment from an opened message | `GET /gmail/v1/users/me/messages/{id}/attachments/{attachmentId}` | Read-only | Open the item viewer and show a harmless test attachment. |
| Mark a message read | `POST /gmail/v1/users/me/messages/{id}/modify`, removing `UNREAD` | Changes Gmail | Perform the action in the app, refresh Gmail Web, and show the message is read. |
| Mark a message unread | `POST /gmail/v1/users/me/messages/{id}/modify`, adding `UNREAD` | Changes Gmail | Perform the action in the app, refresh Gmail Web, and show the message is unread. |
| Add a star | `POST /gmail/v1/users/me/messages/{id}/modify`, adding `STARRED` | Changes Gmail | Add the star in the app, refresh Gmail Web, and show the star. |
| Remove a star | `POST /gmail/v1/users/me/messages/{id}/modify`, removing `STARRED` | Changes Gmail | Remove the star in the app, refresh Gmail Web, and show it was removed. |
| Send a new message, including an optional attachment | `POST /gmail/v1/users/me/messages/send` | Creates a sent message | Send a uniquely titled test message, then show it in Gmail Web → Sent. |
| Reply to a message | `POST /gmail/v1/users/me/messages/send` with reply headers | Creates a reply in the thread | Reply in the app, then show the reply in the matching Gmail Web thread. |
| Move a message to Trash | `POST /gmail/v1/users/me/messages/{id}/trash` | Moves the message to Gmail Trash | Move a uniquely named test message in the app, then show it in Gmail Web → Trash. Do not permanently delete it. |

## Features that do not use `gmail.modify`

The following features are local or use a separate service and must not be presented as justification for the Gmail scope:

- Pinning a message to the top: stored only in the local encrypted cache.
- Address book entries: stored locally.
- Notification and accessibility preferences: stored locally.
- Message translation: initiated separately by the user and sent directly to Google Translate after the app's privacy notice.
- Opening links and locally saving attachments: local user actions after Gmail content has been retrieved.

## Features not present in the current production release

Do not claim or demonstrate these features until they are implemented and released:

- Gmail search.
- Archiving messages.
- Creating or applying custom Gmail labels.
- Permanently deleting messages.
- Restoring messages from Trash.

## Why narrower scopes do not provide the current workflow

- `gmail.metadata` cannot retrieve message bodies or attachments.
- `gmail.readonly` cannot change read state, change the Starred label, or move messages to Trash.
- `gmail.send` permits sending but cannot list or read the mailbox and cannot perform the message-management actions above.
- Combining `gmail.readonly` and `gmail.send` still cannot mark messages read or unread, add or remove stars, or move messages to Trash.

`gmail.modify` is therefore the narrowest Gmail scope that supports the complete set of Gmail features currently exposed by Power Accessible Mail. The application does not request `https://mail.google.com/` and does not permanently delete Gmail messages.

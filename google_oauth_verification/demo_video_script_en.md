# Google OAuth Verification Demo Video Script — Revision 2

App name: Power Accessible Mail

Project ID: `accessiblemail260527`

Requested Gmail scope: `https://www.googleapis.com/auth/gmail.modify`

This revision directly answers the Third-Party Data Safety Team finding that the previous video did not demonstrate the maximum extent of the user-facing features using `gmail.modify`.

## Recording preparation

1. Use a dedicated Gmail test account containing no personal information.
2. Prepare three uniquely titled test messages: `PAM READ TEST`, `PAM STAR TEST`, and `PAM TRASH TEST`. Prepare one harmless small attachment.
3. Keep Gmail Web open in the same source account so every write operation can be verified immediately.
4. Remove the test account from Power Accessible Mail or revoke the previous grant before recording so the complete OAuth consent flow appears again.
5. Set the Google consent-screen language to English.
6. Keep the app publishing status **In production**.
7. Do not show passwords, OAuth tokens, client secrets, personal messages, browser history, or unrelated notifications.
8. Use zoom or editing callouts so the consent text, app controls, test message subjects, and Gmail Web results remain readable.

## Required recording sequence

### Scene 1 — App identity and purpose

Show Power Accessible Mail and its accessible Windows desktop interface.

English narration/caption:

> Power Accessible Mail is a Windows desktop email client designed for blind and screen-reader users. This demonstration shows every production feature that currently uses the requested gmail.modify scope and verifies each write operation in the source Gmail account.

### Scene 2 — Complete OAuth grant flow

1. Open **Account options and management**.
2. Choose **Add account** and then **Continue with Google**.
3. Show the official Google account chooser.
4. Select the dedicated test account.
5. Show the complete English consent screen with the exact app name **Power Accessible Mail**.
6. Click **Show all services** if it appears.
7. Pause and zoom so every requested permission is fully expanded and readable.
8. Confirm that the displayed permissions match the Google Cloud configuration: `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/gmail.modify`.
9. Choose **Allow** or **Continue**.
10. Return to the app and show the successful account result dialog.

English narration/caption:

> The identity scopes identify the connected Google account. Power Accessible Mail requests gmail.modify for the complete Gmail client workflow demonstrated next. The app does not request the broader mail.google.com scope.

### Scene 3 — List mailbox messages

1. Refresh Inbox and show the test messages.
2. Briefly show the Spam, Sent, All Mail, and Trash sections or filters.

English narration/caption:

> The app uses Gmail API to list Inbox, Spam, Sent, All Mail, and Trash messages selected by the user.

### Scene 4 — Read a message and retrieve an attachment

1. Open `PAM READ TEST`.
2. Show the sender, subject, message body, and accessible message viewer.
3. Open the item viewer and show the harmless attachment and message links.
4. Open or save only the harmless test attachment if useful to make attachment retrieval explicit.

English narration/caption:

> gmail.modify includes the read access required to retrieve the full selected message and its attachments. gmail.metadata would not provide message bodies or attachment content.

### Scene 5 — Mark unread and verify in Gmail Web

1. In Power Accessible Mail, mark `PAM READ TEST` as unread.
2. Wait for the server-success status.
3. Switch to Gmail Web, refresh the source account, locate the same unique subject, and show that it is unread.

English narration/caption:

> The app adds the Gmail UNREAD label only after the user requests this action. Gmail Web now shows the same message as unread.

### Scene 6 — Mark read and verify in Gmail Web

1. Return to Power Accessible Mail and mark the same message as read.
2. Wait for server confirmation.
3. Return to Gmail Web, refresh, and show that the same message is now read.

English narration/caption:

> The app removes the UNREAD label when the user marks the message as read. This write operation requires gmail.modify and is reflected in the source Gmail account.

### Scene 7 — Add and remove a star, verifying both changes

1. In the app, add a star to `PAM STAR TEST`.
2. Refresh Gmail Web and show the star on the same message.
3. Return to the app and remove the star.
4. Refresh Gmail Web again and show that the star was removed.

English narration/caption:

> Power Accessible Mail adds or removes the Gmail STARRED label only when requested by the user. Both changes are visible in Gmail Web.

### Scene 8 — Send a new message and verify Sent

1. Compose a message with the unique subject `PAM OAUTH SEND TEST`.
2. Add a harmless attachment if desired.
3. Send the message.
4. Open Gmail Web → Sent, refresh, and show the same subject and attachment.

English narration/caption:

> The app uses Gmail API to send user-composed messages and optional attachments. The sent message is now visible in the source account's Sent folder.

### Scene 9 — Reply and verify the Gmail thread

1. Return to the app and reply to a non-sensitive test message using the subject or thread `PAM OAUTH REPLY TEST`.
2. Send the reply.
3. Open the matching thread in Gmail Web and show the newly sent reply.

English narration/caption:

> Power Accessible Mail preserves the reply headers and sends the user-authored reply through Gmail API. Gmail Web shows the reply in the matching thread.

### Scene 10 — Move to Trash and verify the source account

1. In the app, select `PAM TRASH TEST`.
2. Choose the command that moves it to Gmail Trash and confirm the accessible warning.
3. Open Gmail Web → Trash, refresh, and show the same unique subject.
4. Do not permanently delete it.

English narration/caption:

> The app moves a selected message to Gmail Trash only after explicit user confirmation. It does not permanently delete Gmail messages and does not request the broader mail.google.com scope.

### Scene 11 — Least-privilege conclusion

Return to Power Accessible Mail and show the connected test account.

English narration/caption:

> gmail.send alone cannot list or read the mailbox. gmail.readonly cannot change read state, change the Starred label, or move messages to Trash. Combining gmail.readonly and gmail.send still cannot perform those message-management operations. gmail.modify is therefore the narrowest Gmail scope that supports the complete production email-client workflow demonstrated in this video.

> Gmail data and OAuth tokens remain on the user's Windows device and are not sent to a developer-controlled server. Local cached data and saved OAuth credentials are protected for the current Windows account using Windows DPAPI.

## Editing checklist

- Add a short English title card before every scene naming the exact operation.
- Keep the unique message subject visible when switching between the app and Gmail Web.
- For every write action, show the action in Power Accessible Mail first and its result in Gmail Web second.
- Do not accelerate or cut away from the expanded consent permissions.
- Do not spend video time on translation, pinning, the local address book, update checks, or unrelated settings; they do not justify `gmail.modify`.
- Upload the final video as **Unlisted**, verify it while signed out, then reply directly to the existing OAuth Verification email thread with the new link.

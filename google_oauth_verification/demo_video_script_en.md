# Google OAuth Verification Demo Video Script

App name: Power Accessible Mail

Use a dedicated test Gmail account containing only non-sensitive sample messages. Set the Google consent-screen language to English and do not display passwords, personal mail, access tokens, or client secrets.

## Recording sequence

1. Open the public homepage at `https://soljan-alsharq.com/` and briefly show the app description and the Privacy Policy link.
2. Open Power Accessible Mail and show its name and accessible Windows desktop interface.
3. Open Account options and management, choose Add account, then choose Continue with Google.
4. Show that the system browser opens Google's official authorization page. Select the dedicated test account.
5. Show the complete English Google consent screen, including the Power Accessible Mail name and every requested permission. Do not skip this screen in the recording.
6. Choose Allow or Continue, return to Power Accessible Mail, and show that the account was added successfully.
7. Refresh Inbox and open a sample message. Show the message body, sender, subject, links, and a harmless sample attachment.
8. Mark the sample message read and unread, add and remove its star, and show that the changes appear in Gmail.
9. Compose and send a test message, then open Sent and show the message there.
10. Move a selected sample message to Gmail Trash and show it in the Trash filter. Do not permanently delete it.
11. Select a non-sensitive sample message and invoke Translate. Show the accessible privacy notice explaining that only the selected text is sent to the official Google Translate service and that attachments and sign-in tokens are not sent. Choose Allow and show the translated result. Invoke Translate again to show that the saved choice prevents the notice from appearing again.
12. Open Help, then Privacy Policy, and show the sections describing Gmail access, local DPAPI encryption, data deletion, Google Translate, and Google Limited Use.
13. End on the Power Accessible Mail interface and state that Gmail data and OAuth tokens are not sent to a developer-controlled server.

## Suggested English narration

Power Accessible Mail is a Windows desktop email client designed for blind and screen-reader users. It uses Google's official OAuth flow so users can connect Gmail without entering their Google password into the application.

The application requests openid, email, profile, and gmail.modify. The identity scopes identify the connected account. Gmail.modify is required to list and read user-selected messages, send messages and replies, change read state, add or remove the Starred label, and move selected messages to Gmail Trash. Gmail.send or gmail.readonly would not support this complete user-visible email-client workflow.

Gmail data and OAuth tokens are stored only on the user's Windows device. The local cache and tokens are protected with Windows DPAPI. The developer does not receive Gmail content or OAuth tokens on a server.

Translation is optional. When the user invokes it for the first time, Power Accessible Mail explains that the selected message text will be sent directly to the official Google Translate service and provides Allow and Cancel choices. After Allow is selected, the choice is saved and the notice is not shown again. Attachments and OAuth tokens are not sent for translation.

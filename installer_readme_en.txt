Power Accessible Mail
Version: 1.2.9

Edition: Gmail API Limited
Developer: Ali Al-Amir
Company: Soljan.AlSharq.
Company ownership: Soljan.AlSharq. is owned by developer Ali Al-Amir

About the application
Power Accessible Mail is an email application designed for comfortable use with screen readers. Its interface uses native Windows lists and fields and presents messages vertically for efficient keyboard navigation.

Adding a Gmail account
1. Open Accounts and select Add account.
2. Select browser sign-in, then select Gmail.
3. Choose the account and grant consent on Google's official page.
4. Return to the application after sign-in succeeds.

This edition uses the Gmail API and the limited gmail.modify scope. The user does not enter a Gmail password inside the application.

Main sections
- Inbox: displays messages carrying the INBOX label.
- Spam: displays Gmail Spam or a detected Junk folder.
- Sent: displays messages sent by the user.
- All Mail: displays Gmail All Mail and can reveal recent messages that do not appear in Inbox.

Message filters
Each section can display all messages, starred messages, unread messages, or read messages. The Trash option displays messages in Gmail's actual Trash label.

Main commands
- Refresh displayed content: retrieves the newest messages from the server.
- Synchronize all messages: retrieves older messages in batches and stores them locally.
- Load older messages: retrieves one older batch for the current section.
- Account options and management: adds an account, signs in again, or removes an account from the application.
- Compose email: creates and sends a new message.
- Settings: selects Arabic or English, the message viewer, in-view or separate-window translation, and light or dark appearance.

Read status
Selecting a message does not mark it as read automatically. Press Space on the selected message to switch between read and unread.

Reading messages and elements
In the HTML viewer, links and buttons appear in their original message positions as real screen-reader elements. Use Tab or your screen reader's browsing commands, then press Enter or Space to activate an element.

The element viewer is hidden by default in HTML mode. Press Ctrl+Enter to move between the message and element viewers. Press Ctrl+Space to return to the message list.

The easy viewer presents cleaned text with fewer blank lines. Its element viewer lists links, buttons, and attachments with clear names.

Message actions
Open the actions menu from its button or press Shift+F10. Depending on the message state, available actions include Reply, Star, Translate, Pin to top, Move to Gmail Trash, and Save attachments.

Keyboard shortcuts
- Ctrl+A: account options and management.
- Ctrl+N: compose a new message.
- Ctrl+R: reply to the selected message.
- Ctrl+T: translate the current message.
- F5: refresh messages.
- F1: open the application guide.
- Ctrl+Space: return to the message list.
- Ctrl+Enter: switch between the message and element viewers.
- Shift+F10: open the context and actions menu.
- Alt+F4: close the application.

Security and privacy
- Browser sign-in uses OAuth, and the application does not read browser passwords.
- The local message cache is protected with Windows DPAPI for the current Windows account.
- Distribution packages contain no user accounts or cached messages.
- The application can access Gmail only after the user grants consent on Google's official page.

Updates and removal
To check for updates, open Help and select Update application. To remove the application, open Installed apps in Windows Settings, select Power Accessible Mail, and choose Uninstall.

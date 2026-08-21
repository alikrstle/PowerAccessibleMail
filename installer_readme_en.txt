Power Accessible Mail
Version 1.3.0
Developed by Soljan.AlSharq.
Soljan.AlSharq. is owned by Ali Al-Amir

Welcome to your email

Power Accessible Mail is built to make reading writing organizing and updating email comfortable from the keyboard

Native Windows lists and fields give screen readers predictable controls while messages are arranged vertically so moving through your mail feels direct and familiar

Add your account in the way that suits you

When the application starts without an account you can continue with Google continue with Microsoft sign in manually or open the main interface without adding an account

Open Account options and management and select Add account

The sign in methods appear as a real list

Select browser sign in or manual sign in then press Enter right click the selected item or use the OK button beside Cancel

Browser sign in opens the official Google or Microsoft consent page and never asks the application to read your browser password

After you return from the browser, the app shows the sign-in result in a readable dialog with Continue and Copy buttons. If sign-in fails, you can copy the error details and send them to the developer; sign-in tokens and secrets are redacted before display or copying

Manual sign in begins with an Email service choice

Select Google or Microsoft and the application fills the matching IMAP and SMTP settings while keeping the fields available for review

Gmail manual sign in normally requires an app password

For Microsoft browser sign in is recommended because password based IMAP access may be restricted by the account policy

Your mail sections

Inbox reads the real Inbox folder

Spam reads Spam or Junk

Sent holds the messages you sent

All Mail opens Gmail All Mail when it is available and can reveal recent messages that do not carry the Inbox label

Inside each section the filter can show all messages starred messages unread messages read messages or the real Trash folder

Press F5 whenever you want the newest messages

Synchronize all messages retrieves older mail in batches and stores it locally

Load older messages adds one older batch from the current section

Read each message in the viewer you prefer

The HTML viewer keeps links and buttons in their natural positions as real page elements

Use Tab or your screen reader browsing commands to reach them then press Enter or Space to activate them

Press Ctrl+Enter to move between the message viewer and the item viewer

Press Escape to return directly to the message list

The easy viewer removes repeated blank lines and presents clean text

Its item viewer collects links buttons images and attachments under clear names

Selecting a message does not mark it as read automatically

Press Space in the normal message list to switch the focused message between read and unread

Work with several messages at once

In normal mode messages are list items without check boxes

Press Ctrl+Shift+Space to enter multiple selection mode where every message becomes a check box

Move with the arrow keys and press Space to check or uncheck a message or use the mouse

The application announces entry into or exit from this mode after 150 milliseconds

Press Control by itself to hear the selected count

Press Escape or Ctrl+Shift+Space again to leave the mode

Trying to move above the first item or below the last item announces the boundary

The context menu provides suitable bulk read star pin and Trash commands

Delete asks for confirmation and states how many messages will be moved to Trash

Write and act without leaving the keyboard

Compose email opens a complete message window

Setup registers Power Accessible Mail among the email applications available to Windows. From application Settings choose Choose PowerAccessibleMail as the default email app then confirm your choice in Windows Settings. In Windows 11 Enter might not open the associated-app picker; press Space on MAILTO to open it. Afterward selecting an email address or mailto link in a browser opens Compose with the recipient subject and body from the link filled automatically. The application never changes the Windows default without your approval

Reply Star Translate Pin to top and move to the provider Trash are available from the message context menu. The item viewer list has no context menu, and the Item actions button displays attachment and link commands directly

Use Shift+F10 or the Application key for the message context menu and use the Item actions button for attachments images and links

Translation in place or in a separate window

Ctrl+T translates the current message into the application language

In Settings choose whether translation replaces the content inside the HTML or easy viewer or opens in a separate window

Translation becomes available only while you are inside the message viewer

It requires an internet connection and sends the selected message text to the official Google Translate service only when you request it. Before the first translation, the app explains this transfer and provides Allow and Cancel choices. After you choose Allow, the choice is saved and the notice is not shown again

Make the application yours

Settings lets you choose Arabic English or French the HTML or easy message viewer translation inside the page or in a separate window and light or dark appearance

You can also control how many application actions the NVDA library announces with four levels: none some most or all. The Customize and manage action announcements button beside the level opens categories containing native Windows checkboxes. Use Tab to move between them hear their state and Space to change it then save. The default level does not announce read or unread state changes or server-save confirmations unless the user enables that category in customization. Settings also includes Choose PowerAccessibleMail as the default email app which opens the application's page in Windows Settings; press Space on MAILTO to open the app picker if Enter does not respond

Your choices are saved for the next launch

Updates without opening a browser

The application checks GitHub Releases after startup and you can check manually from Help and Check for updates

When a release is available Update now opens an internal progress window showing its version release date progress bar and percentage

The correct installer is downloaded to the Power Accessible Mail updates folder in the user profile its SHA-256 digest is verified and Setup appears in a visible window before the application closes to complete the update and restart

Detailed guide to the main window

Application notifications

The notification bar appears at the top of the window and announces important information such as a completed action a required sign in or an available update. Some notices disappear after a short time while the status bar at the bottom keeps the latest operation state

Email account selector

This control lists the accounts you added. Selecting an account changes the displayed folders and messages without mixing its data with another account. When no account exists open Account options and management to add one

Application command list

Refresh displayed content retrieves the newest messages for the current section and performs the same action as F5

Synchronize all messages continues retrieving older mail in batches and stores it locally until synchronization finishes or stops

Load older messages retrieves one batch older than the messages currently displayed in the section

Account options and management opens commands to add an account sign in again or remove the account

Compose email opens the new message window

Address book opens the email addresses you saved and lets you compose edit pin view associated messages or delete an address

Settings opens the application language message viewer translation mode and appearance choices

Mail sections

Inbox Spam Sent and All Mail are separate pages with their own displayed messages and filter. All Mail is available when the provider supports it and may reveal messages that do not carry the Inbox label

Filter choice

The filter controls what the current section displays: All Starred Unread Read or the real Trash folder. Selecting Trash requests its actual contents from the email provider

Message list

Each row contains Status Sender Subject and Date. Status announces whether the message is read or unread starred or pinned. Use the arrow keys Home End Page Up and Page Down to navigate. Selecting a message loads its content but does not change its read status automatically

Message viewer

This area displays the selected message using the HTML or simple viewer chosen in Settings. Escape returns focus to the message list and Ctrl+Enter moves to the item viewer

Item viewer

This separate list collects the message links buttons images and attachments. Every item begins with its type and number such as Link 1 Button 1 Image 1 or Attachment 1 followed by its name and address or by the file type and size. The application combines equivalent addresses after normalizing the host and common tracking parameters and chooses the best description from element text aria-label title or alt text. Links and buttons keep reading order followed by images and attachments. Hidden 1 by 1 tracking images are excluded

Item actions button

This button displays the commands directly without a submenu: Open selected attachment Save selected attachment Save all attachments at once Open image Save image Open selected link and Copy selected link. Reply Star Translate Pin and Delete remain in the message context menu

Message retrieval progress and status bar

The progress control reports message retrieval or synchronization percentage. The status bar announces the current operation and its result so you do not need to move focus to it

Mark a message as read or unread

Moving to a message or opening its content does not mark it as read. From the normal message list press Space once to switch the focused message between read and unread. The Status column changes immediately and the application then saves that state to the server

When a message is unread you can press the Application key or Shift+F10 and choose Mark as read. The context menu does not include Mark as unread; press Space in the message list whenever you want to switch the read state. In multiple selection mode Mark as read is available for the selected group

Use the Unread filter to find messages that still need attention and the Read filter to review messages you have finished

Use the item viewer step by step

While focus is inside the message viewer press Ctrl+Enter. The item viewer becomes available and focus moves to its list. Use Up and Down Arrow to choose a link button image or attachment

Press Enter or Space to open the item directly. A safe link or an image with an external address opens in the default browser and an attachment opens locally. A button with a link behaves the same way while a button or image without an address that can be opened is announced clearly

For explicit commands press Tab to reach the Item actions button then press Enter or Space. An attachment provides Open selected attachment and Save selected attachment and you can save every attachment in the message at once. A link or image with an external address provides Open selected link and Copy selected link which places its safe address on the Windows clipboard. Commands that do not apply to the selected item remain disabled to prevent accidental activation

Press Ctrl+Enter to return to the message viewer or Escape to return directly to the message list. The item list has no context menu. The Item actions button is the only place that displays these commands and presents them directly without a submenu

Manage received attachments

Opening an attachment writes a protected temporary copy with a safe name and asks Windows to open it in the default application. The temporary copies created for the current session are removed when Power Accessible Mail closes

Before opening a file that may run commands such as EXE BAT CMD or MSI the application displays a security warning with No as the default. Continue only when you trust both the sender and the file

To save one attachment focus it in the item viewer then move to the Item actions button and choose Save selected attachment before choosing its name and folder. To save every attachment choose Save all attachments at once from the same button and select one folder. To copy a link focus it then use Item actions and choose Copy selected link; the application places its safe address on the Windows clipboard. When a filename already exists the application creates a unique name instead of silently replacing the previous file

Compose a message and add outgoing attachments

The compose window starts with To followed by Add email address to the address book then Subject and the multiline Body field. Add attachment follows the Body followed by the Added attachments list then Send and Cancel in Tab order

While focus is in To press Down Arrow to open the saved addresses. Move with the arrow keys and press Enter or Space to choose one; the selected address replaces all text in the field. If you press the add-address button while the field is empty or invalid the application announces the problem and does not save it

Press Add attachment to open the file picker. You can select one file or several files in the same operation. Each selected file appears in the list with its filename and size so you can review exactly what will be sent

To remove a file added by mistake focus it in the attachment list and press Delete or press the Application key and choose Remove selected attachment. Removing it from the list never deletes the original file from your computer

When you press Send the application adds every file still shown in the list to the MIME message. This works for both Gmail API and SMTP accounts. The email provider controls message and attachment size limits and may reject a message that exceeds its permitted size

Use the address book

Open Address book from the application command list. A vertical address list appears beside Add a new email address. Browse with the arrow keys and press Enter or Space or double-click an address to open Compose with the recipient filled automatically

Press the Application key or Shift+F10 on an address to open its context menu. You can edit the email address or pin it to the top; for a pinned address the command changes to Unpin email address from the top. You can also view messages sent to it and received from it or delete it. In the associated-messages window move with the arrow keys and press Enter or Space to open the selected message in the main window

Context menus and the Application key

The keyboard Application key is sometimes named Menu or Context Menu. It opens the context menu for the control that currently has focus. Power Accessible Mail supports it in the message list message viewer Item actions button outgoing attachment list and address book. The item viewer list has no context menu; press Tab from it to reach Item actions. Shift+F10 is equivalent where a context menu is available

The message viewer context menu provides Reply Mark as read when needed Star Translate Pin and Delete. The Item actions button displays the seven attachment image and link commands directly without a submenu. To reach them press Ctrl+Enter to move to the item viewer select an item then press Tab to reach Item actions

In the message list commands adapt to the focused message and its current state. On the Item actions button they adapt to the selected item type. In multiple selection mode message commands act on the group and the application states the affected message count before deletion

Useful keyboard commands

Ctrl+A opens account options and management
Ctrl+N composes a new message
Ctrl+R replies to the focused message
Ctrl+T translates the current message
F5 refreshes messages
F1 opens the application guide
Escape returns to the message list from the message or item viewer
Ctrl+Enter switches between message and item viewers
Shift+F10 opens the context and actions menu
Alt+F4 closes the application

Your privacy stays part of the design

OAuth access begins only after your approval on the provider official page

Locally cached messages tokens and saved credentials are protected by Windows DPAPI for the current Windows account

Distribution packages do not contain user accounts or messages

Removing an account from the application also removes its locally stored application data

Power Accessible Mail
An accessible email experience developed by Soljan.AlSharq.
Soljan.AlSharq. is owned by Ali Al-Amir

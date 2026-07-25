# Privacy Policy for Power Accessible Mail

Last updated: May 30, 2026

## Overview

Power Accessible Mail is a desktop email client designed to improve access to email for blind and screen-reader users. The application lets users sign in to their Gmail account through Google's OAuth consent flow, read email messages, browse message links and attachments, reply to messages, and send new messages.

## Google User Data Accessed

When a user connects a Gmail account, Power Accessible Mail requests permission to access Gmail through OAuth. The current desktop version uses the `https://mail.google.com/` scope so it can connect to Gmail through IMAP and SMTP using XOAUTH2.

The app may access:

- The user's email address and basic profile information used to identify the signed-in account.
- Email message headers, including sender, subject, date, and read/unread state.
- Email message body content.
- Email links and attachments selected by the user.
- Sent mail and spam/junk folders when available.

## How Google User Data Is Used

Google user data is used only to provide the user-facing email features visible inside the application:

- Displaying the user's mailbox.
- Reading messages in an accessible vertical text viewer.
- Showing links and attachments contained in messages.
- Marking messages as read when the user opens them.
- Sending new messages and replies on behalf of the user.
- Caching messages locally so the application can load faster and avoid repeatedly downloading the same messages.

Power Accessible Mail does not use Google user data for advertising, analytics, profiling, AI training, or sale to third parties.

## Local Storage and Security

Power Accessible Mail is a desktop application. Email data is stored locally on the user's own Windows device. Cached messages, message bodies, message links, message attachments, and message summaries are encrypted locally using Windows DPAPI and are tied to the current Windows user account.

OAuth tokens are stored locally so the user does not need to sign in every time. Users can remove the account from the application or revoke access from their Google Account security settings.

## Data Sharing

Power Accessible Mail does not send Gmail message content, attachments, contacts, or OAuth tokens to the developer's servers.

The application may contact an update manifest URL only to check whether a new version is available. That update check does not include Gmail message content.

## Data Retention and Deletion

Email data is retained locally only as long as the user keeps the app data on their device. Users can delete locally stored data by removing the app data folder:

`%APPDATA%\PowerAccessibleMail`

Users can revoke Google access at any time from their Google Account permissions page.

## Limited Use

Power Accessible Mail's use and transfer of information received from Google APIs adheres to the Google API Services User Data Policy, including the Limited Use requirements.

## Contact

For privacy or support questions, contact:

`PUT-YOUR-SUPPORT-EMAIL-HERE`

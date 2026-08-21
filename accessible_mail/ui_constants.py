from __future__ import annotations

from .config import (
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_FRENCH,
    MESSAGE_READ_MANUAL,
    MESSAGE_READ_ON_VIEWER_ENTER,
    THEME_DARK,
    THEME_LIGHT,
    TRANSLATION_DIALOG,
    TRANSLATION_INLINE,
    VIEWER_HTML,
    VIEWER_SIMPLE,
)
from .notification_preferences import (
    NOTIFICATION_LEVEL_ALL,
    NOTIFICATION_LEVEL_MOST,
    NOTIFICATION_LEVEL_NONE,
    NOTIFICATION_LEVEL_SOME,
)


INITIAL_MESSAGE_LIMIT = 50
MAX_MEMORY_MESSAGE_CONTENTS = 20
MESSAGE_SELECTION_DELAY_MS = 140
MULTI_SELECTION_ANNOUNCEMENT_DELAY_MS = 150

FILTER_ALL = "الكل"
FILTER_STARRED = "الرسائل المميزة بنجمة"
FILTER_UNREAD = "غير مقروءة"
FILTER_READ = "مقروءة"
FILTER_TRASH = "سلة المحذوفات"
FILTER_CHOICES = [FILTER_ALL, FILTER_STARRED, FILTER_UNREAD, FILTER_READ, FILTER_TRASH]

ITEM_FILTER_ALL = "عرض كل العناصر"
ITEM_FILTER_LINKS = "عرض الروابط فقط"
ITEM_FILTER_ATTACHMENTS = "عرض المرفقات فقط"
ITEM_FILTER_IMAGES = "عرض الصور فقط"
ITEM_FILTER_CHOICES = [
    ITEM_FILTER_ALL,
    ITEM_FILTER_LINKS,
    ITEM_FILTER_ATTACHMENTS,
    ITEM_FILTER_IMAGES,
]

BULK_ACTION_MARK_READ = "mark_read"
BULK_ACTION_MARK_UNREAD = "mark_unread"
BULK_ACTION_STAR = "star"
BULK_ACTION_UNSTAR = "unstar"
BULK_ACTION_PIN = "pin"
BULK_ACTION_UNPIN = "unpin"
BULK_ACTION_DELETE = "delete"

LANGUAGE_CHOICES = {
    "العربية": LANGUAGE_ARABIC,
    "الإنجليزية": LANGUAGE_ENGLISH,
    "الفرنسية": LANGUAGE_FRENCH,
}
VIEWER_CHOICES = {
    "مستعرض HTML": VIEWER_HTML,
    "المستعرض السهل": VIEWER_SIMPLE,
}
MESSAGE_READ_MODE_CHOICES = {
    "يدوي عبر Space أو قائمة السياق": MESSAGE_READ_MANUAL,
    "تلقائي عند الدخول إلى مستعرض الرسالة": MESSAGE_READ_ON_VIEWER_ENTER,
}
THEME_CHOICES = {
    "الوضع الفاتح": THEME_LIGHT,
    "الوضع المظلم": THEME_DARK,
}
TRANSLATION_MODE_CHOICES = {
    "ترجمة داخل مستعرض الرسالة": TRANSLATION_INLINE,
    "ترجمة في نافذة مستقلة": TRANSLATION_DIALOG,
}
SPOKEN_NOTIFICATION_LEVEL_CHOICES = {
    "عدم نطق إجراءات البرنامج مطلقًا": NOTIFICATION_LEVEL_NONE,
    "نطق بعض إجراءات البرنامج": NOTIFICATION_LEVEL_SOME,
    "نطق معظم إجراءات البرنامج": NOTIFICATION_LEVEL_MOST,
    "نطق كل إجراءات البرنامج": NOTIFICATION_LEVEL_ALL,
}

MANUAL_PROVIDER_GOOGLE = "google"
MANUAL_PROVIDER_MICROSOFT = "microsoft"
MANUAL_PROVIDER_CHOICES = (
    (MANUAL_PROVIDER_GOOGLE, "Google / Gmail"),
    (MANUAL_PROVIDER_MICROSOFT, "Microsoft / Outlook"),
)
MANUAL_PROVIDER_SETTINGS = {
    MANUAL_PROVIDER_GOOGLE: {
        "imap_server": "imap.gmail.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "",
    },
    MANUAL_PROVIDER_MICROSOFT: {
        "imap_server": "outlook.office365.com",
        "imap_port": 993,
        "imap_ssl": True,
        "smtp_server": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "smtp_ssl": False,
        "smtp_starttls": True,
        "spam_mailbox": "Junk Email",
    },
}

INLINE_GENERIC_LINK_TEXTS = (
    "اضغط هنا",
    "إضغط هنا",
    "انقر هنا",
    "هنا",
    "افتح",
    "فتح",
    "click here",
    "here",
)

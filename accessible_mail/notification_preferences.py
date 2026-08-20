from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .i18n import source_text


NOTIFICATION_LEVEL_NONE = "none"
NOTIFICATION_LEVEL_SOME = "some"
NOTIFICATION_LEVEL_MOST = "most"
NOTIFICATION_LEVEL_ALL = "all"
NOTIFICATION_LEVELS: Final = {
    NOTIFICATION_LEVEL_NONE,
    NOTIFICATION_LEVEL_SOME,
    NOTIFICATION_LEVEL_MOST,
    NOTIFICATION_LEVEL_ALL,
}

EVENT_DIALOGS = "dialogs"
EVENT_CONTEXT_MENUS = "context_menus"
EVENT_GENERAL = "general"
EVENT_NEW_MAIL = "new_mail"
EVENT_ACCOUNTS = "accounts"
EVENT_OPERATION_STARTED = "operation_started"
EVENT_OPERATION_COMPLETED = "operation_completed"
EVENT_SYNC = "sync"
EVENT_MESSAGE_READ = "message_read"
EVENT_MESSAGE_STAR = "message_star"
EVENT_MESSAGE_PIN = "message_pin"
EVENT_MESSAGE_DELETE = "message_delete"
EVENT_MULTI_SELECTION = "multi_selection"
EVENT_ADDRESS_BOOK = "address_book"
EVENT_COMPOSE_ATTACHMENTS = "compose_attachments"
EVENT_SEND = "send"
EVENT_LINKS = "links"
EVENT_RECEIVED_ATTACHMENTS = "received_attachments"
EVENT_IMAGES = "images"
EVENT_TRANSLATION = "translation"
EVENT_UPDATES = "updates"
EVENT_ERRORS_SECURITY = "errors_security"
EVENT_READY = "ready"
EVENT_MESSAGE_LOADING = "message_loading"
EVENT_PROGRESS = "progress"
EVENT_FOCUS_NAVIGATION = "focus_navigation"
EVENT_ITEM_DETAILS = "item_details"


@dataclass(frozen=True, slots=True)
class SpokenNotificationEvent:
    event_id: str
    label: str


@dataclass(frozen=True, slots=True)
class SpokenNotificationGroup:
    label: str
    event_ids: tuple[str, ...]


SPOKEN_NOTIFICATION_EVENTS: Final = (
    SpokenNotificationEvent(EVENT_DIALOGS, "نوافذ التنبيه والتأكيد"),
    SpokenNotificationEvent(EVENT_CONTEXT_MENUS, "فتح قوائم السياق"),
    SpokenNotificationEvent(EVENT_GENERAL, "الإشعارات العامة والترحيب"),
    SpokenNotificationEvent(EVENT_NEW_MAIL, "وصول رسائل جديدة"),
    SpokenNotificationEvent(EVENT_ACCOUNTS, "الحسابات وتسجيل الدخول"),
    SpokenNotificationEvent(EVENT_OPERATION_STARTED, "بدء العمليات الداخلية"),
    SpokenNotificationEvent(EVENT_OPERATION_COMPLETED, "اكتمال العمليات العامة"),
    SpokenNotificationEvent(EVENT_SYNC, "تحديث البريد والمزامنة وتحميل الرسائل القديمة"),
    SpokenNotificationEvent(EVENT_MESSAGE_READ, "تغيير حالة الرسالة إلى مقروءة أو غير مقروءة"),
    SpokenNotificationEvent(EVENT_MESSAGE_STAR, "تمييز الرسائل بنجمة وإزالة النجمة"),
    SpokenNotificationEvent(EVENT_MESSAGE_PIN, "تثبيت الرسائل وإلغاء تثبيتها"),
    SpokenNotificationEvent(EVENT_MESSAGE_DELETE, "حذف الرسائل ونقلها إلى سلة المحذوفات"),
    SpokenNotificationEvent(EVENT_MULTI_SELECTION, "وضع التحديد المتعدد وعدد الرسائل وحدود القائمة"),
    SpokenNotificationEvent(EVENT_ADDRESS_BOOK, "إجراءات سجل العناوين"),
    SpokenNotificationEvent(EVENT_COMPOSE_ATTACHMENTS, "إضافة مرفقات الرسالة وإزالتها"),
    SpokenNotificationEvent(EVENT_SEND, "إرسال الرسائل ونتيجة الإرسال"),
    SpokenNotificationEvent(EVENT_LINKS, "فتح الروابط ونسخها ومنع الروابط غير الآمنة"),
    SpokenNotificationEvent(EVENT_RECEIVED_ATTACHMENTS, "فتح المرفقات المستلمة وحفظها"),
    SpokenNotificationEvent(EVENT_IMAGES, "فتح الصور وحفظها وفحصها"),
    SpokenNotificationEvent(EVENT_TRANSLATION, "ترجمة الرسائل ونتيجة الترجمة"),
    SpokenNotificationEvent(EVENT_UPDATES, "فحص تحديثات البرنامج وتنزيلها وتثبيتها"),
    SpokenNotificationEvent(EVENT_ERRORS_SECURITY, "الأخطاء والتحذيرات الأمنية"),
    SpokenNotificationEvent(EVENT_READY, "حالة جاهز"),
    SpokenNotificationEvent(EVENT_MESSAGE_LOADING, "بدء واكتمال تحميل محتوى الرسالة"),
    SpokenNotificationEvent(EVENT_PROGRESS, "النسب المئوية لتقدم العمليات"),
    SpokenNotificationEvent(EVENT_FOCUS_NAVIGATION, "أسماء مناطق الرسائل عند انتقال التركيز"),
    SpokenNotificationEvent(EVENT_ITEM_DETAILS, "اسم الرابط أو الزر عند التنقل داخل الرسالة"),
)

ALL_EVENT_IDS: Final = frozenset(event.event_id for event in SPOKEN_NOTIFICATION_EVENTS)
EVENTS_BY_ID: Final = {
    event.event_id: event for event in SPOKEN_NOTIFICATION_EVENTS
}
SPOKEN_NOTIFICATION_GROUPS: Final = (
    SpokenNotificationGroup(
        "التنبيهات العامة",
        (
            EVENT_DIALOGS,
            EVENT_CONTEXT_MENUS,
            EVENT_GENERAL,
            EVENT_ERRORS_SECURITY,
        ),
    ),
    SpokenNotificationGroup(
        "الحسابات والبريد والتحديثات",
        (
            EVENT_NEW_MAIL,
            EVENT_ACCOUNTS,
            EVENT_OPERATION_STARTED,
            EVENT_OPERATION_COMPLETED,
            EVENT_SYNC,
            EVENT_UPDATES,
            EVENT_PROGRESS,
        ),
    ),
    SpokenNotificationGroup(
        "إدارة الرسائل والتنقل",
        (
            EVENT_MESSAGE_READ,
            EVENT_MESSAGE_STAR,
            EVENT_MESSAGE_PIN,
            EVENT_MESSAGE_DELETE,
            EVENT_MULTI_SELECTION,
            EVENT_MESSAGE_LOADING,
            EVENT_READY,
            EVENT_FOCUS_NAVIGATION,
            EVENT_ITEM_DETAILS,
        ),
    ),
    SpokenNotificationGroup(
        "إنشاء الرسائل وسجل العناوين",
        (
            EVENT_ADDRESS_BOOK,
            EVENT_COMPOSE_ATTACHMENTS,
            EVENT_SEND,
        ),
    ),
    SpokenNotificationGroup(
        "محتوى الرسالة",
        (
            EVENT_LINKS,
            EVENT_RECEIVED_ATTACHMENTS,
            EVENT_IMAGES,
            EVENT_TRANSLATION,
        ),
    ),
)
_SOME_EVENT_IDS: Final = frozenset(
    {
        EVENT_DIALOGS,
        EVENT_NEW_MAIL,
        EVENT_ACCOUNTS,
        EVENT_SEND,
        EVENT_UPDATES,
        EVENT_ERRORS_SECURITY,
    }
)
_NOISY_EVENT_IDS: Final = frozenset(
    {
        EVENT_READY,
        EVENT_MESSAGE_LOADING,
        EVENT_MESSAGE_READ,
        EVENT_PROGRESS,
        EVENT_FOCUS_NAVIGATION,
    }
)

_active_event_ids: frozenset[str] = ALL_EVENT_IDS - _NOISY_EVENT_IDS


def preset_event_ids(level: str) -> set[str]:
    if level == NOTIFICATION_LEVEL_NONE:
        return set()
    if level == NOTIFICATION_LEVEL_SOME:
        return set(_SOME_EVENT_IDS)
    if level == NOTIFICATION_LEVEL_ALL:
        return set(ALL_EVENT_IDS)
    return set(ALL_EVENT_IDS - _NOISY_EVENT_IDS)


def normalize_event_ids(event_ids: object) -> list[str] | None:
    if event_ids is None:
        return None
    if not isinstance(event_ids, (list, tuple, set, frozenset)):
        return None
    selected = {str(event_id) for event_id in event_ids} & set(ALL_EVENT_IDS)
    return [event.event_id for event in SPOKEN_NOTIFICATION_EVENTS if event.event_id in selected]


def configure_spoken_notifications(
    level: str,
    selected_event_ids: object = None,
) -> None:
    global _active_event_ids
    normalized_level = level if level in NOTIFICATION_LEVELS else NOTIFICATION_LEVEL_MOST
    normalized_events = normalize_event_ids(selected_event_ids)
    _active_event_ids = frozenset(
        preset_event_ids(normalized_level)
        if normalized_events is None
        else normalized_events
    )


def event_is_enabled(event_id: str) -> bool:
    return event_id in _active_event_ids


def notification_event_for_message(message: str) -> str:
    text = source_text(str(message or "")).strip()
    if not text:
        return EVENT_GENERAL
    if "%" in text:
        return EVENT_PROGRESS
    if text == "جاهز":
        return EVENT_READY
    if text in {"جار تحميل الرسالة...", "تم تحميل الرسالة."}:
        return EVENT_MESSAGE_LOADING
    if text in {"مستعرض العناصر.", "مستعرض الرسالة.", "قائمة الرسائل."}:
        return EVENT_FOCUS_NAVIGATION

    if any(word in text for word in ("خطأ", "تعذر", "فشل", "تحذير", "غير آمن", "ضار", "رفض")):
        return EVENT_ERRORS_SECURITY
    if any(word in text for word in ("تحديث البرنامج", "التحديث داخل البرنامج", "تنزيل التحديث", "تثبيت التحديث", "فحص التحديثات")):
        return EVENT_UPDATES
    if "ترجم" in text or "الترجمة" in text:
        return EVENT_TRANSLATION
    if (
        "عنوان البريد الإلكتروني" in text
        or "البريد الإلكتروني" in text
        or "سجل العناوين" in text
        or "العنوان" in text and "البريد" in text
    ):
        return EVENT_ADDRESS_BOOK
    if "مرفق" in text and "الرسالة" in text and any(word in text for word in ("إضافة", "إزالة", "المضافة")):
        return EVENT_COMPOSE_ATTACHMENTS
    if "مرفق" in text:
        return EVENT_RECEIVED_ATTACHMENTS
    if "الصورة" in text or "صورة" in text:
        return EVENT_IMAGES
    if text.startswith(("رابط:", "زر:")):
        return EVENT_ITEM_DETAILS
    if "الرابط" in text or "رابط" in text or "الحافظة" in text:
        return EVENT_LINKS
    if "إرسال" in text or "إرسال الرسالة" in text:
        return EVENT_SEND
    if any(word in text for word in ("الحساب", "تسجيل الدخول", "OAuth", "Google", "Microsoft")):
        return EVENT_ACCOUNTS
    if "رسالة جديدة" in text or "رسائل جديدة" in text:
        return EVENT_NEW_MAIL
    if any(word in text for word in ("التحديد المتعدد", "رسالة محددة", "رسائل محددة", "بداية قائمة", "نهاية قائمة")):
        return EVENT_MULTI_SELECTION
    if "سلة المحذوفات" in text or "حذف" in text:
        return EVENT_MESSAGE_DELETE
    if "تثبيت" in text:
        return EVENT_MESSAGE_PIN
    if "نجمة" in text:
        return EVENT_MESSAGE_STAR
    if "مقروء" in text or "حالة الرسالة" in text:
        return EVENT_MESSAGE_READ
    if any(word in text for word in ("مزامنة", "تحديث الرسائل", "رسائل أقدم", "عرض")) and any(
        word in text for word in ("رسالة", "رسائل", "الرسائل")
    ):
        return EVENT_SYNC
    if text.startswith("جار "):
        return EVENT_OPERATION_STARTED
    if text.startswith(("تم ", "تمت ", "اكتمل", "اكتملت")):
        return EVENT_OPERATION_COMPLETED
    return EVENT_GENERAL

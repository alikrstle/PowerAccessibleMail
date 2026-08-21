from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import wx

from accessible_mail.accessibility import announce_to_screen_reader, message_box
from accessible_mail.notification_preferences import (
    ALL_EVENT_IDS,
    EVENT_ADDRESS_BOOK,
    EVENT_CONTEXT_MENUS,
    EVENT_FOCUS_NAVIGATION,
    EVENT_ITEM_DETAILS,
    EVENT_MESSAGE_LOADING,
    EVENT_MESSAGE_PIN,
    EVENT_MESSAGE_READ,
    EVENT_PROGRESS,
    EVENT_READY,
    EVENT_SEND,
    EVENT_SYNC,
    EVENT_TRANSLATION,
    NOTIFICATION_LEVEL_ALL,
    NOTIFICATION_LEVEL_MOST,
    NOTIFICATION_LEVEL_NONE,
    NOTIFICATION_LEVEL_SOME,
    SPOKEN_NOTIFICATION_GROUPS,
    configure_spoken_notifications,
    event_is_enabled,
    notification_event_for_message,
    preset_event_ids,
)


class NotificationPreferenceTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure_spoken_notifications(NOTIFICATION_LEVEL_MOST)

    def test_four_levels_have_increasing_useful_coverage(self) -> None:
        none = preset_event_ids(NOTIFICATION_LEVEL_NONE)
        some = preset_event_ids(NOTIFICATION_LEVEL_SOME)
        most = preset_event_ids(NOTIFICATION_LEVEL_MOST)
        all_events = preset_event_ids(NOTIFICATION_LEVEL_ALL)

        self.assertEqual(none, set())
        self.assertLess(some, most)
        self.assertLess(most, all_events)
        self.assertEqual(all_events, set(ALL_EVENT_IDS))
        self.assertIn(EVENT_CONTEXT_MENUS, most)
        self.assertNotIn(EVENT_READY, most)
        self.assertNotIn(EVENT_MESSAGE_READ, most)
        self.assertIn(EVENT_READY, all_events)
        self.assertIn(EVENT_MESSAGE_READ, all_events)

    def test_checkbox_groups_cover_every_notification_once(self) -> None:
        grouped_event_ids = [
            event_id
            for group in SPOKEN_NOTIFICATION_GROUPS
            for event_id in group.event_ids
        ]

        self.assertEqual(set(grouped_event_ids), set(ALL_EVENT_IDS))
        self.assertEqual(len(grouped_event_ids), len(set(grouped_event_ids)))

    def test_explicit_checklist_selection_overrides_the_level_preset(self) -> None:
        configure_spoken_notifications(
            NOTIFICATION_LEVEL_NONE,
            [EVENT_CONTEXT_MENUS, EVENT_SEND, "unknown"],
        )

        self.assertTrue(event_is_enabled(EVENT_CONTEXT_MENUS))
        self.assertTrue(event_is_enabled(EVENT_SEND))
        self.assertFalse(event_is_enabled(EVENT_READY))

    def test_internal_messages_are_assigned_to_customizable_categories(self) -> None:
        expected = {
            "جاهز": EVENT_READY,
            "تم تحميل الرسالة.": EVENT_MESSAGE_LOADING,
            "جار استلام الرسائل (50%).": EVENT_PROGRESS,
            "مستعرض الرسالة.": EVENT_FOCUS_NAVIGATION,
            "تم تثبيت الرسالة في الأعلى.": EVENT_MESSAGE_PIN,
            "تم تثبيت البريد الإلكتروني بالأعلى.": EVENT_ADDRESS_BOOK,
            "تم إرسال الرسالة.": EVENT_SEND,
            "تم تحديث الرسائل. الوارد 5.": EVENT_SYNC,
            "رابط: الموقع الرسمي": EVENT_ITEM_DETAILS,
            "جار ترجمة الرسالة...": EVENT_TRANSLATION,
            "تمت ترجمة الرسالة داخل المستعرض.": EVENT_TRANSLATION,
            "ألغيت ترجمة الرسالة قبل إرسال النص.": EVENT_TRANSLATION,
            "تعذر الحصول على ترجمة من Google.": EVENT_TRANSLATION,
            "اكتملت ترجمة أوصاف العناصر في الخلفية، وتعذر ترجمة بعضها.": EVENT_TRANSLATION,
        }

        for message, event_id in expected.items():
            with self.subTest(message=message):
                self.assertEqual(notification_event_for_message(message), event_id)

    @patch("accessible_mail.accessibility.interrupt_and_speak", return_value=True)
    def test_none_level_stops_nvda_library_announcements(self, speak: Mock) -> None:
        configure_spoken_notifications(NOTIFICATION_LEVEL_NONE)

        announced = announce_to_screen_reader(Mock(), "تم إرسال الرسالة.")

        self.assertFalse(announced)
        speak.assert_not_called()

    @patch("accessible_mail.accessibility._native_message_box", return_value=wx.ID_OK)
    @patch("accessible_mail.accessibility.interrupt_and_speak", return_value=True)
    def test_dialogs_follow_the_central_notification_selection(
        self,
        speak: Mock,
        native_message_box: Mock,
    ) -> None:
        configure_spoken_notifications(NOTIFICATION_LEVEL_NONE)
        message_box("رسالة صامتة", "تنبيه")
        speak.assert_not_called()

        configure_spoken_notifications(NOTIFICATION_LEVEL_ALL)
        message_box("رسالة منطوقة", "تنبيه")
        speak.assert_called_once_with("رسالة منطوقة")
        self.assertEqual(native_message_box.call_count, 2)


if __name__ == "__main__":
    unittest.main()

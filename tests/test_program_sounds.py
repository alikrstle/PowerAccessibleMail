from __future__ import annotations

import tempfile
import unittest
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from accessible_mail import config
from accessible_mail.i18n import SUPPORTED_LANGUAGES, set_language, tr
from accessible_mail.program_sounds import (
    ALL_SOUND_EVENT_IDS,
    PROGRAM_SOUNDS,
    SOUND_ADDRESS_BOOK,
    SOUND_COMPOSE,
    SOUND_SEND,
    SOUND_TASK_COMPLETE,
    SOUND_UPDATE_BACKGROUND,
    UPDATE_BACKGROUND_SOUND,
    normalize_sound_event_ids,
    play_program_sound,
    replace_program_sound,
    sound_path,
    start_update_background_music,
    stop_update_background_music,
)
from accessible_mail.interactive_learning import InteractiveLearning, LESSONS
from accessible_mail.dialogs import ProgramSoundsDialog, SettingsDialog
from accessible_mail.main_frame import MainFrame


class ProgramSoundsTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_language(config.LANGUAGE_ARABIC)

    def test_all_declared_sound_assets_exist_and_are_mp3_files(self) -> None:
        self.assertEqual(len(PROGRAM_SOUNDS), 10)
        for sound in (*PROGRAM_SOUNDS, UPDATE_BACKGROUND_SOUND):
            path = sound_path(sound.event_id)
            self.assertIsNotNone(path, sound.filename)
            assert path is not None
            self.assertEqual(path.suffix.casefold(), ".mp3")
            self.assertTrue(path.read_bytes().startswith(b"ID3"), sound.filename)

    def test_event_normalization_is_stable_and_filters_unknown_values(self) -> None:
        self.assertEqual(
            normalize_sound_event_ids(None),
            [sound.event_id for sound in PROGRAM_SOUNDS],
        )
        self.assertEqual(
            normalize_sound_event_ids([SOUND_SEND, "unknown", SOUND_COMPOSE]),
            [SOUND_COMPOSE, SOUND_SEND],
        )

    def test_sound_settings_round_trip(self) -> None:
        settings = config.ProgramSettings(
            program_sounds_enabled=False,
            program_sound_events=[SOUND_SEND],
            program_sound_files={SOUND_SEND: "C:/sounds/send.mp3"},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch("accessible_mail.config.settings_path", return_value=path):
                config.save_settings(settings)
                loaded = config.load_settings()
        self.assertFalse(loaded.program_sounds_enabled)
        self.assertEqual(loaded.program_sound_events, [SOUND_SEND])
        self.assertEqual(
            loaded.program_sound_files,
            {SOUND_SEND: "C:/sounds/send.mp3"},
        )

    def test_existing_sound_preferences_enable_new_address_book_sound_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({
                "program_sound_events": [SOUND_SEND],
                "program_sounds_enabled": True,
            }), encoding="utf-8")
            with patch("accessible_mail.config.settings_path", return_value=path):
                loaded = config.load_settings()
                self.assertEqual(loaded.program_sound_events, [SOUND_SEND, SOUND_ADDRESS_BOOK])
                config.save_settings(loaded)
                loaded.program_sound_events.remove(SOUND_ADDRESS_BOOK)
                config.save_settings(loaded)
                reloaded = config.load_settings()
        self.assertEqual(reloaded.program_sound_events, [SOUND_SEND])
        self.assertEqual(reloaded.program_sound_catalog_version, 2)

    def test_existing_profile_with_all_sounds_disabled_stays_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"program_sound_events": []}), encoding="utf-8")
            with patch("accessible_mail.config.settings_path", return_value=path):
                loaded = config.load_settings()
        self.assertEqual(loaded.program_sound_events, [])

    def test_opening_address_book_uses_configured_sound_event(self) -> None:
        frame = SimpleNamespace(
            selected_account=lambda: None,
            address_message_matches=Mock(),
            play_program_sound=Mock(return_value=True),
            open_compose_dialog=Mock(),
            open_address_message=Mock(),
        )
        with patch("accessible_mail.main_frame.AddressBookDialog") as dialog_class:
            dialog_class.return_value.ShowModal.return_value = 0
            MainFrame.on_address_book(frame)
        frame.play_program_sound.assert_called_once_with(SOUND_ADDRESS_BOOK)
        dialog_class.return_value.ShowModal.assert_called_once_with()

    def test_replacement_is_copied_to_stable_application_data(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as data_dir:
            source = Path(source_dir) / "replacement.mp3"
            source.write_bytes(b"ID3replacement")
            with patch("accessible_mail.program_sounds.data_dir", return_value=Path(data_dir)):
                destination = replace_program_sound(SOUND_SEND, source)
            self.assertEqual(destination.parent, Path(data_dir) / "custom-sounds")
            self.assertTrue(destination.name.startswith("send-"))
            self.assertEqual(destination.read_bytes(), b"ID3replacement")

    def test_custom_sound_overrides_bundled_sound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            custom = Path(directory) / "custom.mp3"
            custom.write_bytes(b"ID3custom")
            settings = SimpleNamespace(program_sound_files={SOUND_SEND: str(custom)})
            self.assertEqual(sound_path(SOUND_SEND, settings), custom.resolve())

    def test_cancelled_replacement_does_not_overwrite_previously_saved_sound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            source.write_bytes(b"ID3original")
            with patch("accessible_mail.program_sounds.data_dir", return_value=root):
                saved = replace_program_sound(SOUND_SEND, source)
                settings = SimpleNamespace(program_sound_files={SOUND_SEND: str(saved)})
                source.write_bytes(b"ID3new")
                cancelled = replace_program_sound(SOUND_SEND, source)
            self.assertNotEqual(saved, cancelled)
            self.assertEqual(saved.read_bytes(), b"ID3original")
            self.assertEqual(sound_path(SOUND_SEND, settings), saved.resolve())

    def test_fixed_background_music_is_not_customizable(self) -> None:
        self.assertNotIn(SOUND_UPDATE_BACKGROUND, ALL_SOUND_EVENT_IDS)
        self.assertNotIn(
            SOUND_UPDATE_BACKGROUND,
            normalize_sound_event_ids([SOUND_UPDATE_BACKGROUND]),
        )
        self.assertIsNotNone(sound_path(SOUND_UPDATE_BACKGROUND))

    def test_update_background_music_uses_fixed_file_at_reduced_volume(self) -> None:
        media = Mock()
        media.IsBeingDeleted.return_value = False
        media.Load.return_value = True
        media.Play.return_value = True
        app = SimpleNamespace(GetTopWindow=lambda: object())
        settings = SimpleNamespace(program_sounds_enabled=True)
        with (
            patch("accessible_mail.program_sounds.os.name", "nt"),
            patch("accessible_mail.program_sounds.sound_path", return_value=Path("background.mp3")),
            patch("accessible_mail.program_sounds.wx.GetApp", return_value=app),
            patch("accessible_mail.program_sounds.wx.media.MediaCtrl", return_value=media),
            patch("accessible_mail.program_sounds._WX_BACKGROUND_CONTROL", None),
        ):
            self.assertTrue(start_update_background_music(settings))
            media.SetVolume.assert_called_once_with(0.35)
            media.Load.assert_called_once_with("background.mp3")
            media.Play.assert_called_once()
            stop_update_background_music()

    def test_play_respects_master_switch_and_selected_events(self) -> None:
        fake_path = Path("sound.mp3")
        with (
            patch("accessible_mail.program_sounds.os.name", "nt"),
            patch("accessible_mail.program_sounds.sound_path", return_value=fake_path),
            patch("accessible_mail.program_sounds._play_mp3_with_mci", return_value=True) as player,
        ):
            disabled = SimpleNamespace(
                program_sounds_enabled=False,
                program_sound_events=[SOUND_SEND],
            )
            self.assertFalse(play_program_sound(SOUND_SEND, disabled))
            player.assert_not_called()

            selected = SimpleNamespace(
                program_sounds_enabled=True,
                program_sound_events=[SOUND_COMPOSE],
            )
            self.assertFalse(play_program_sound(SOUND_SEND, selected))
            self.assertTrue(play_program_sound(SOUND_COMPOSE, selected))
            player.assert_called_once_with(fake_path)

    def test_preview_can_play_even_when_master_switch_is_off(self) -> None:
        settings = SimpleNamespace(
            program_sounds_enabled=False,
            program_sound_events=[],
        )
        with (
            patch("accessible_mail.program_sounds.os.name", "nt"),
            patch("accessible_mail.program_sounds.sound_path", return_value=Path("sound.mp3")),
            patch("accessible_mail.program_sounds._play_mp3_with_mci", return_value=True) as player,
        ):
            self.assertTrue(play_program_sound(SOUND_SEND, settings, force=True))
            player.assert_called_once()

    def test_wx_media_fallback_runs_when_windows_mci_rejects_mp3(self) -> None:
        settings = SimpleNamespace(
            program_sounds_enabled=True,
            program_sound_events=[SOUND_SEND],
            program_sound_files={},
        )
        with (
            patch("accessible_mail.program_sounds.os.name", "nt"),
            patch("accessible_mail.program_sounds.sound_path", return_value=Path("sound.mp3")),
            patch("accessible_mail.program_sounds._play_mp3_with_mci", return_value=False),
            patch("accessible_mail.program_sounds._play_mp3_with_wx", return_value=True) as fallback,
        ):
            self.assertTrue(play_program_sound(SOUND_SEND, settings))
        fallback.assert_called_once_with(Path("sound.mp3"))

    def test_visible_sound_names_are_translated_in_every_supported_language(self) -> None:
        keys = [
            "تشغيل أصوات البرنامج",
            "تخصيص أصوات البرنامج",
            "استبدال",
            "اختر ملف MP3 لاستبدال الصوت",
            "الإعدادات والتدريب",
            *(sound.label for sound in PROGRAM_SOUNDS),
        ]
        for language in SUPPORTED_LANGUAGES:
            set_language(language)
            for key in keys:
                value = tr(key)
                self.assertTrue(value.strip(), (language, key))
                if language != config.LANGUAGE_ARABIC:
                    self.assertNotEqual(value, key, (language, key))

    def test_build_script_bundles_sound_directory(self) -> None:
        script = (config.app_dir() / "build_power_accessible_mail.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('Join-Path $PSScriptRoot "sound"', script)
        self.assertIn('";sound"', script)

    def test_each_event_is_connected_to_an_application_action(self) -> None:
        root = config.app_dir() / "accessible_mail"
        sources = "\n".join(
            (root / filename).read_text(encoding="utf-8")
            for filename in ("main_frame.py", "interactive_learning.py")
        )
        for event_id in ALL_SOUND_EVENT_IDS:
            self.assertIn(event_id.upper(), sources)

    @patch("accessible_mail.interactive_learning.announce_to_screen_reader")
    @patch("accessible_mail.interactive_learning.wx.CallLater")
    def test_reaching_guide_end_plays_completion_even_after_a_skipped_task(
        self,
        call_later,
        announce,
    ) -> None:
        parent = SimpleNamespace(play_program_sound=Mock())
        guide = SimpleNamespace(
            step=len(LESSONS),
            task_states={LESSONS[0][2]: "skipped"},
            _guide_completion_sound_played=False,
            status=Mock(),
            card_timer=None,
            completion_card=Mock(),
            Layout=Mock(),
            GetParent=lambda: parent,
            hide_completion=Mock(),
        )

        InteractiveLearning.show_completion(guide)

        parent.play_program_sound.assert_called_once_with("learning_complete")
        announce.assert_called_once()
        call_later.assert_called_once()

    @patch("accessible_mail.interactive_learning.announce_to_screen_reader")
    @patch("accessible_mail.interactive_learning.wx.CallLater")
    def test_completing_regular_guide_task_plays_task_sound(
        self,
        call_later,
        announce,
    ) -> None:
        parent = SimpleNamespace(play_program_sound=Mock())
        guide = SimpleNamespace(
            step=1,
            task_states={LESSONS[0][2]: "completed"},
            _guide_completion_sound_played=False,
            status=Mock(),
            card_timer=None,
            completion_card=Mock(),
            Layout=Mock(),
            GetParent=lambda: parent,
            hide_completion=Mock(),
        )
        InteractiveLearning.show_completion(guide)
        parent.play_program_sound.assert_called_once_with(SOUND_TASK_COMPLETE)
        announce.assert_called_once()
        call_later.assert_called_once()

    def test_sound_names_play_directly_and_each_row_has_replace_button(self) -> None:
        source = inspect.getsource(ProgramSoundsDialog.__init__)
        self.assertIn("lambda _event, event_id=sound.event_id: self.play_sound(event_id)", source)
        self.assertIn('label=tr("استبدال")', source)
        self.assertNotIn("preview_button", source)

    def test_visual_options_are_at_the_end_of_settings(self) -> None:
        source = inspect.getsource(SettingsDialog._build)
        self.assertLess(
            source.index("self.customize_sounds_button = wx.Button"),
            source.index("self.low_vision_options_button = wx.Button"),
        )
        self.assertLess(
            source.index("self.low_vision_options_button = wx.Button"),
            source.index("self.default_mail_button = wx.Button"),
        )
        self.assertLess(
            source.index("self.default_mail_button = wx.Button"),
            source.index("self.restore_defaults_button = wx.Button"),
        )
        self.assertLess(
            source.index("self.restore_defaults_button = wx.Button"),
            source.index("self.theme_box = wx.RadioBox"),
        )

    def test_installer_has_fixed_music_and_mute_checkbox_for_both_builds(self) -> None:
        script = (config.app_dir() / "installer_power_accessible_mail.iss").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('DestName: "pam-installer-background.mp3"', script)
        self.assertIn("MuteInstallerMusicCheck", script)
        self.assertIn("CreateOleObject('WMPlayer.OCX')", script)
        self.assertIn("Settings.SetMode('loop', True)", script)
        self.assertIn('TargetArchitecture "x64"', script)


if __name__ == "__main__":
    unittest.main()

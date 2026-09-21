from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from accessible_mail import error_logging


class ErrorLoggingTests(unittest.TestCase):
    @staticmethod
    def reset_logger() -> None:
        logger = logging.getLogger(error_logging.LOGGER_NAME)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        error_logging._configured = False

    def tearDown(self) -> None:
        self.reset_logger()

    def test_crash_log_is_created_under_the_application_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"APPDATA": directory}):
                path = error_logging.configure_crash_logging()
                self.assertEqual(
                    path,
                    Path(directory)
                    / "PowerAccessibleMail"
                    / "logs"
                    / "power-accessible-mail.log",
                )
                self.assertTrue(path.exists())
                self.reset_logger()

    def test_exception_values_are_not_written_to_the_log(self) -> None:
        secret = "secret-access-token-user@example.com"
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"APPDATA": directory}):
                path = error_logging.configure_crash_logging()
                try:
                    raise RuntimeError(secret)
                except RuntimeError as exc:
                    error_logging.record_unhandled_exception(
                        type(exc),
                        exc,
                        exc.__traceback__,
                        origin="test",
                    )
                for handler in logging.getLogger(error_logging.LOGGER_NAME).handlers:
                    handler.flush()
                content = path.read_text(encoding="utf-8")
                self.assertIn("Unhandled RuntimeError in test", content)
                self.assertNotIn(secret, content)
                self.assertNotIn("user@example.com", content)
                self.reset_logger()

    def test_handled_exception_values_are_not_written_to_the_log(self) -> None:
        secret = "secret-oauth-code-user@example.com"
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.dict(os.environ, {"APPDATA": directory}):
                path = error_logging.configure_crash_logging()
                try:
                    raise RuntimeError(secret)
                except RuntimeError as exc:
                    error_logging.record_handled_exception(
                        exc,
                        origin="OAuth account sign-in",
                    )
                for handler in logging.getLogger(error_logging.LOGGER_NAME).handlers:
                    handler.flush()
                content = path.read_text(encoding="utf-8")
                self.assertIn("Handled RuntimeError in OAuth account sign-in", content)
                self.assertNotIn(secret, content)
                self.assertNotIn("user@example.com", content)
                self.reset_logger()

from __future__ import annotations

import json
import unittest
import urllib.error
from unittest.mock import patch

from accessible_mail.update_checker import (
    ARCHITECTURE_X64,
    ARCHITECTURE_X86,
    GITHUB_API_VERSION,
    check_for_updates,
    version_key,
)


class FakeResponse:
    def __init__(self, payload: object = b"", final_url: str = "") -> None:
        if isinstance(payload, bytes):
            self.payload = payload
        else:
            self.payload = json.dumps(payload).encode("utf-8")
        self.final_url = final_url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, _size: int = -1) -> bytes:
        return self.payload

    def geturl(self) -> str:
        return self.final_url


class UpdateCheckerTests(unittest.TestCase):
    def github_release(self) -> dict[str, object]:
        return {
            "tag_name": "v1.2.9",
            "published_at": "2026-07-25T18:30:00Z",
            "html_url": "https://github.com/alikrstle/PowerAccessibleMail/releases/tag/v1.2.9",
            "body": "Accessibility and performance improvements.",
            "assets": [
                {
                    "name": "PowerAccessibleMailSetup-1.2.9-win-x64.exe",
                    "browser_download_url": "https://github.com/download/x64.exe",
                    "digest": f"sha256:{'a' * 64}",
                },
                {
                    "name": "PowerAccessibleMailSetup-1.2.9-win-x86-UNSIGNED.exe",
                    "browser_download_url": "https://github.com/download/x86-unsigned.exe",
                    "digest": f"sha256:{'b' * 64}",
                },
                {
                    "name": "PowerAccessibleMailSetup-1.2.9-win-x86.exe",
                    "browser_download_url": "https://github.com/download/x86.exe",
                    "digest": f"sha256:{'c' * 64}",
                },
            ],
        }

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_x64_build_selects_signed_x64_installer(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        urlopen.return_value = FakeResponse(self.github_release())

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X64)

        self.assertTrue(result.configured)
        self.assertTrue(result.available)
        self.assertEqual(result.latest_version, "1.2.9")
        self.assertEqual(result.download_url, "https://github.com/download/x64.exe")
        self.assertEqual(result.sha256, "a" * 64)
        self.assertEqual(result.release_date, "2026-07-25T18:30:00Z")
        self.assertIn("Accessibility", result.notes)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Accept"), "application/vnd.github+json")
        self.assertEqual(request.get_header("X-github-api-version"), GITHUB_API_VERSION)

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_x86_build_selects_signed_x86_installer(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        urlopen.return_value = FakeResponse(self.github_release())

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X86)

        self.assertTrue(result.available)
        self.assertEqual(result.download_url, "https://github.com/download/x86.exe")
        self.assertEqual(result.sha256, "c" * 64)

    @patch.dict(
        "os.environ",
        {"POWER_ACCESSIBLE_MAIL_GITHUB_TOKEN": "test-token"},
        clear=False,
    )
    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_optional_github_token_is_sent_as_bearer_authentication(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        urlopen.return_value = FakeResponse(self.github_release())

        check_for_updates("1.2.8", architecture=ARCHITECTURE_X64)

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_release_page_is_used_when_matching_installer_is_missing(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        release = self.github_release()
        release["assets"] = []
        urlopen.return_value = FakeResponse(release)

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X64)

        self.assertEqual(result.download_url, release["html_url"])

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_rate_limit_falls_back_to_latest_release_redirect(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        api_error = urllib.error.HTTPError(
            "https://api.github.com/releases/latest",
            403,
            "rate limited",
            {},
            None,
        )
        release_url = (
            "https://github.com/alikrstle/PowerAccessibleMail/releases/tag/v1.2.9"
        )
        signed_asset_error = urllib.error.HTTPError(
            "https://github.com/download/x64.exe",
            404,
            "not found",
            {},
            None,
        )
        urlopen.side_effect = [
            api_error,
            FakeResponse(b"", final_url=release_url),
            signed_asset_error,
            FakeResponse(b""),
        ]

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X64)

        self.assertTrue(result.available)
        self.assertEqual(result.latest_version, "1.2.9")
        self.assertEqual(
            result.download_url,
            (
                "https://github.com/alikrstle/PowerAccessibleMail/releases/"
                "download/v1.2.9/"
                "PowerAccessibleMailSetup-1.2.9-win-x64-UNSIGNED.exe"
            ),
        )

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_rate_limit_uses_release_page_when_installer_checks_fail(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        release_url = (
            "https://github.com/alikrstle/PowerAccessibleMail/releases/tag/v1.2.9"
        )
        errors = [
            urllib.error.HTTPError(
                "https://api.github.com/releases/latest",
                403,
                "rate limited",
                {},
                None,
            ),
            FakeResponse(b"", final_url=release_url),
            urllib.error.HTTPError(
                "https://github.com/download/x64.exe",
                404,
                "not found",
                {},
                None,
            ),
            urllib.error.HTTPError(
                "https://github.com/download/x64-unsigned.exe",
                404,
                "not found",
                {},
                None,
            ),
        ]
        urlopen.side_effect = errors

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X64)

        self.assertTrue(result.available)
        self.assertEqual(result.download_url, release_url)

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_missing_published_release_has_clear_result(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        urlopen.side_effect = urllib.error.HTTPError(
            "https://api.github.com/releases/latest",
            404,
            "not found",
            {},
            None,
        )

        result = check_for_updates("1.2.8")

        self.assertFalse(result.available)
        self.assertIn("لا يوجد إصدار منشور", result.message)

    @patch(
        "accessible_mail.update_checker.load_update_manifest_url",
        return_value="https://updates.example.com/latest.json",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_manifest_override_remains_supported(self, urlopen, _manifest) -> None:
        urlopen.return_value = FakeResponse(
            {
                "version": "1.3.0",
                "download_url": "https://updates.example.com/setup.exe",
                "sha256": "d" * 64,
                "release_date": "2026-08-01",
                "notes": "Release notes",
            }
        )

        result = check_for_updates("1.2.8")

        self.assertTrue(result.available)
        self.assertEqual(result.latest_version, "1.3.0")
        self.assertEqual(
            result.download_url,
            "https://updates.example.com/setup.exe",
        )
        self.assertEqual(result.sha256, "d" * 64)
        self.assertEqual(result.release_date, "2026-08-01")

    @patch(
        "accessible_mail.update_checker.load_update_manifest_url",
        return_value="https://updates.example.com/latest.json",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_manifest_can_provide_architecture_specific_downloads(
        self,
        urlopen,
        _manifest,
    ) -> None:
        urlopen.return_value = FakeResponse(
            {
                "version": "1.3.0",
                "downloads": {
                    "x64": "https://updates.example.com/x64.exe",
                    "x86": {
                        "url": "https://updates.example.com/x86.exe",
                        "sha256": f"sha256:{'e' * 64}",
                    },
                },
            }
        )

        result = check_for_updates("1.2.8", architecture=ARCHITECTURE_X86)

        self.assertEqual(result.download_url, "https://updates.example.com/x86.exe")
        self.assertEqual(result.sha256, "e" * 64)

    @patch(
        "accessible_mail.update_checker.load_update_manifest_url",
        return_value="http://updates.example.com/latest.json",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_insecure_manifest_url_is_rejected_without_network_request(
        self,
        urlopen,
        _manifest,
    ) -> None:
        result = check_for_updates("1.2.8")

        self.assertFalse(result.available)
        self.assertIn("HTTPS", result.message)
        urlopen.assert_not_called()

    @patch(
        "accessible_mail.update_checker.load_update_manifest_url",
        return_value="https://updates.example.com/latest.json",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_manifest_redirect_to_http_is_rejected(self, urlopen, _manifest) -> None:
        urlopen.return_value = FakeResponse(
            {"version": "1.3.0"},
            final_url="http://updates.example.com/latest.json",
        )

        result = check_for_updates("1.2.8")

        self.assertFalse(result.available)
        self.assertIn("غير آمن", result.message)

    def test_equivalent_versions_compare_equally(self) -> None:
        self.assertEqual(version_key("v1.2"), version_key("1.2.0"))

    @patch("accessible_mail.update_checker.load_update_manifest_url", return_value="")
    @patch(
        "accessible_mail.update_checker.load_github_repository",
        return_value="alikrstle/PowerAccessibleMail",
    )
    @patch("accessible_mail.update_checker.urllib.request.urlopen")
    def test_unrelated_tag_name_is_not_treated_as_version(
        self,
        urlopen,
        _repository,
        _manifest,
    ) -> None:
        release = self.github_release()
        release["tag_name"] = "release-from-2026"
        urlopen.return_value = FakeResponse(release)

        result = check_for_updates("1.2.8")

        self.assertFalse(result.available)
        self.assertIn("رقم إصدار صالح", result.message)


if __name__ == "__main__":
    unittest.main()

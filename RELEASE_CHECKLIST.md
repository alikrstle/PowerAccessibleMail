# Power Accessible Mail Release Checklist

## User documentation and release notes

- Identify the previous stable release tag and compare its source tree with the exact commit being released. Compare trees rather than relying on commit history when release and website branches have different ancestry.
- Verify every feature described as new against that comparison. Distinguish new features from improvements to existing features; do not present existing address-book or multiple-selection functionality as newly added.
- Write release notes for someone upgrading from the previous stable version. Explain the benefit and where to find the feature. Do not include training sample names, internal task splits, implementation history, or development-test details.
- Check the program guide against the shipping interface: exact labels, focus order, shortcut scope, search scope, translation prompts, and installer behavior. Distinguish training steps from real-mail actions.
- Review the localized guides for the same changes. An Arabic guide rewrite does not by itself update the other languages.
- For 1.6.0, retain DOCUMENTATION_REVIEW_1.6.0_AR.md and run tests.test_documentation_consistency on both architectures. Check the bundled files, not only fallback guide strings.
- Keep Controlled Folder Access coverage separate from antivirus status and encrypted locks. Review WINDOWS_PROTECTION_REVIEW_1.6.0_AR.md; protection-policy changes require separate authorization and compatibility checks.
- Review the release body shown by the updater, website information, and bundled guide together. Editing source documentation does not update already published installers or portable packages. Publish bundled changes with a new version; do not silently replace an existing stable release's binaries.

## Packaging and verification

- Run `python -m accessible_mail.release_validation <payload-directory>` before packaging. The build runs this check on the PyInstaller payload and stops on a violation.
- No user `accounts.json`, `settings.json`, `address_book.json`, `folders.db`, or `messages.sqlite3`, including backups, temporary variants and SQLite journals, anywhere in the release payload.
- No `.mail_store`, `logs`, or user `custom-sounds` directory, and no symlinks/junctions that can pull unrelated private files into a release.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- x64 build uses 64-bit Python and a PE32+ PyInstaller bootloader; x86 uses 32-bit Python and a PE32 bootloader.
- `test_all_architectures.ps1` passes against the unified source tree and locked dependencies.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Unsigned analysis installers use non-solid ZIP compression; signed installers may use solid LZMA compression.
- A trusted Authenticode signature is preferred. When no affordable certificate is available and the maintainer explicitly approves a stable unsigned release, every unsigned asset keeps the `UNSIGNED` suffix, Windows reports `NotSigned`, SHA-256 manifests are published, and the updater's version, architecture, HTTPS, and digest checks remain mandatory.
- Both architecture application folders, installers, and portable ZIP files were scanned against current Defender definitions with remediation disabled; the scan reports were retained. Any false detection was submitted as a Software developer sample and its submission ID was recorded.
- Installer uses per-user install path and does not require administrator privileges.
- Executable and installer contain consistent company, product, and version metadata.
- The bundled OAuth file contains only the unified `google_gmail_api` and `microsoft` clients.
- Installer, portable ZIP, and application executable are listed in the architecture SHA-256 manifest.
- Internal update URLs use HTTPS and the installer version, architecture, and SHA-256 all match.
- During the temporary unsigned transition, only an installer explicitly suffixed `-UNSIGNED` may bypass Authenticode and Windows must report `NotSigned`. A signed installer is always preferred; invalid or untrusted signatures are rejected.
- Internal updates are stored under the application's LocalAppData update folder and launch an interactive Setup window; silent and suppressed-message installer switches are not used.
- The build manifest records the SHA-256 and Authenticode state of every bundled EXE, DLL, and PYD.
- Installer offers Arabic, English, French, Spanish, Turkish, Hindi, Simplified Chinese, Russian, Japanese, and German, selects the Windows UI language by default, and keeps the destination, tasks, ready, and finished pages enabled.
- Every localized catalog covers the English source catalog, preserves dynamic placeholders such as `{0}` and `{1}`, and contains no translation-generator separators or placeholder tokens.
- Each localized program guide is bundled in both application architectures, the portable ZIP, and the matching installer.
- A native speaker reviews each newly generated language, and an NVDA user verifies focus order, control names, and spoken announcements before a stable release is published.
- Desktop shortcut is selected by default.
- Finished page offers the localized README and application launch as separate options.
- Testers are never instructed to disable Defender or add a permanent antivirus exclusion.

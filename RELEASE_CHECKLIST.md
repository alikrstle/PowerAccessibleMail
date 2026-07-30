# Power Accessible Mail Release Checklist

- No `accounts.json` in the release folder.
- No `messages.sqlite3` in the release folder.
- No `.mail_store` in the release folder.
- Browser OAuth file `oauth_clients.json` is included for sign-in.
- x64 build uses 64-bit Python and a PE32+ PyInstaller bootloader; x86 uses 32-bit Python and a PE32 bootloader.
- `test_all_architectures.ps1` passes against the unified source tree and locked dependencies.
- PyInstaller uses onedir mode and `--noupx` to reduce antivirus false positives.
- Installer uses per-user install path and does not require administrator privileges.
- Executable and installer contain consistent company, product, and version metadata.
- The bundled OAuth file contains only the unified `google_gmail_api` and `microsoft` clients.
- Installer, portable ZIP, and application executable are listed in the architecture SHA-256 manifest.
- Internal update URLs use HTTPS and the installer version, architecture, and SHA-256 all match.
- Installer offers Arabic and English and keeps the destination, tasks, ready, and finished pages enabled.
- Desktop shortcut is selected by default.
- Finished page offers the localized README and application launch as separate options.

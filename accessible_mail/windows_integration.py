from __future__ import annotations

import os
import sys
import ctypes
from pathlib import Path
from urllib.parse import quote

try:
    import winreg
except ImportError:  # pragma: no cover - Windows application
    winreg = None  # type: ignore[assignment]


REGISTERED_APPLICATION_NAME = "Power Accessible Mail"
MAIL_CLIENT_KEY_NAME = "PowerAccessibleMail"
MAILTO_PROG_ID = "PowerAccessibleMail.mailto"
CAPABILITIES_PATH = (
    rf"Software\Clients\Mail\{MAIL_CLIENT_KEY_NAME}\Capabilities"
)
DEFAULT_APPS_SETTINGS_URI = (
    "ms-settings:defaultapps?registeredAppUser="
    + quote(REGISTERED_APPLICATION_NAME, safe="")
)
SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000


def application_launch_command() -> tuple[str, str]:
    executable = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False):
        return f'"{executable}" "%1"', f"{executable},0"

    project_root = Path(__file__).resolve().parent.parent
    launcher = project_root / "main.py"
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.is_file():
        executable = pythonw
    icon = project_root / "assets" / "branding" / "power_accessible_mail.ico"
    return f'"{executable}" "{launcher}" "%1"', str(icon)


def default_mail_registry_entries(
    command: str,
    icon: str,
) -> tuple[tuple[str, str, object, int], ...]:
    if winreg is None:
        return ()
    client_path = rf"Software\Clients\Mail\{MAIL_CLIENT_KEY_NAME}"
    prog_id_path = rf"Software\Classes\{MAILTO_PROG_ID}"
    return (
        (client_path, "", REGISTERED_APPLICATION_NAME, winreg.REG_SZ),
        (client_path + r"\DefaultIcon", "", icon, winreg.REG_SZ),
        (client_path + r"\shell\open\command", "", command, winreg.REG_SZ),
        (CAPABILITIES_PATH, "ApplicationName", REGISTERED_APPLICATION_NAME, winreg.REG_SZ),
        (
            CAPABILITIES_PATH,
            "ApplicationDescription",
            "Accessible email client with NVDA support",
            winreg.REG_SZ,
        ),
        (CAPABILITIES_PATH, "ApplicationIcon", icon, winreg.REG_SZ),
        (CAPABILITIES_PATH, "Hidden", 0, winreg.REG_DWORD),
        (
            CAPABILITIES_PATH + r"\Startmenu",
            "Mail",
            MAIL_CLIENT_KEY_NAME,
            winreg.REG_SZ,
        ),
        (
            CAPABILITIES_PATH + r"\UrlAssociations",
            "mailto",
            MAILTO_PROG_ID,
            winreg.REG_SZ,
        ),
        (
            r"Software\RegisteredApplications",
            REGISTERED_APPLICATION_NAME,
            CAPABILITIES_PATH,
            winreg.REG_SZ,
        ),
        (prog_id_path, "", "Power Accessible Mail email link", winreg.REG_SZ),
        (prog_id_path, "FriendlyTypeName", "Power Accessible Mail email link", winreg.REG_SZ),
        (prog_id_path, "URL Protocol", "", winreg.REG_SZ),
        (prog_id_path + r"\DefaultIcon", "", icon, winreg.REG_SZ),
        (
            prog_id_path + r"\Application",
            "ApplicationName",
            REGISTERED_APPLICATION_NAME,
            winreg.REG_SZ,
        ),
        (
            prog_id_path + r"\Application",
            "ApplicationDescription",
            "Accessible email client with NVDA support",
            winreg.REG_SZ,
        ),
        (prog_id_path + r"\Application", "ApplicationIcon", icon, winreg.REG_SZ),
        (
            prog_id_path + r"\Application",
            "ApplicationCompany",
            "Soljan.AlSharq.",
            winreg.REG_SZ,
        ),
        (prog_id_path + r"\shell\open\command", "", command, winreg.REG_SZ),
        (
            r"Software\Classes\mailto\OpenWithProgids",
            MAILTO_PROG_ID,
            b"",
            winreg.REG_NONE,
        ),
    )


def register_default_mail_capabilities() -> bool:
    if os.name != "nt" or winreg is None:
        return False
    command, icon = application_launch_command()
    try:
        for subkey, value_name, value, value_type in default_mail_registry_entries(
            command,
            icon,
        ):
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                subkey,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.SetValueEx(key, value_name, 0, value_type, value)
    except OSError:
        return False
    notify_shell_association_change()
    return True


def notify_shell_association_change() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED,
            SHCNF_IDLIST,
            None,
            None,
        )
    except (AttributeError, OSError):
        return


def open_default_apps_settings() -> bool:
    try:
        os.startfile(DEFAULT_APPS_SETTINGS_URI)
    except (AttributeError, OSError):
        return False
    return True

"""Read-only distribution checks. Never inspect the user's installed profile."""
from __future__ import annotations

import argparse
from pathlib import Path


PRIVATE_DIRECTORIES = frozenset({".mail_store", "logs", "custom-sounds"})
PRIVATE_FILES = ("accounts.json", "settings.json", "address_book.json", "folders.db", "messages.sqlite3")
PRIVATE_CORRUPT_PREFIXES = tuple(Path(name).stem + ".corrupt-" for name in PRIVATE_FILES)


def private_payload_name(name: str, *, directory: bool = False) -> bool:
    name = name.casefold()
    if directory:
        return name in PRIVATE_DIRECTORIES
    name = name.lstrip(".")
    return (any(name == base or name.startswith(base + ".") or name.startswith(base + "-")
                for base in PRIVATE_FILES)
            or name.startswith(PRIVATE_CORRUPT_PREFIXES)
            or (name.startswith("accounts.") and name.endswith((".json", ".json.bak"))))


def validate_release_directory(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError("Release payload must be an ordinary directory.")
    violations = []
    pending = [root]
    while pending:
        for path in pending.pop().iterdir():
            # Do not follow reparse points into an unrelated profile or directory.
            if path.is_symlink() or path.is_junction():
                violations.append(path)
            elif path.is_dir():
                if private_payload_name(path.name, directory=True):
                    violations.append(path)
                else:
                    pending.append(path)
            elif private_payload_name(path.name):
                violations.append(path)
    return sorted(violations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        violations = validate_release_directory(args.directory)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Payload validation failed: {exc}\n")
    if violations:
        for path in violations:
            print(f"Forbidden distribution entry: {path.relative_to(args.directory)}")
        return 1
    print("Distribution contains no recognized private profile files or reparse points.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

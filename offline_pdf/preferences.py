"""Local display preferences only. Never store document paths or passwords."""

import json
import os
from pathlib import Path

DEFAULTS = {"language": "ko", "theme": "default"}


def preferences_path():
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_CONFIG_HOME")
        or Path.home() / ".config"
    )
    return base / "OfflinePDF" / "settings.json"


def load_preferences():
    try:
        path = preferences_path()
        if path.stat().st_size > 4096:
            return dict(DEFAULTS)
        value = json.loads(path.read_text(encoding="utf-8"))
        return {
            "language": value.get("language") if value.get("language") in ("ko", "en") else "ko",
            "theme": value.get("theme") if value.get("theme") in ("default", "dark") else "default",
        }
    except (OSError, ValueError, AttributeError):
        return dict(DEFAULTS)


def save_preferences(language, theme):
    if language not in ("ko", "en") or theme not in ("default", "dark"):
        raise ValueError("Invalid display preferences")
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(json.dumps({"language": language, "theme": theme}), encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

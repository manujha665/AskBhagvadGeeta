"""macOS glue: which app is in front, and typing text into it."""

from __future__ import annotations

import os
import subprocess
import time

# pbcopy/pbpaste fall back to a non-Unicode encoding without this, garbling Devanagari.
_UTF8_ENV = {**os.environ, "LANG": "en_US.UTF-8"}


def frontmost_app() -> str:
    try:
        from AppKit import NSWorkspace

        return NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
    except Exception:
        return "a text field"


def paste_text(text: str) -> None:
    """Paste via the clipboard (works in every app), then restore the old clipboard."""
    from pynput.keyboard import Controller, Key

    previous = subprocess.run(["pbpaste"], capture_output=True, env=_UTF8_ENV).stdout
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), env=_UTF8_ENV, check=True)
    keyboard = Controller()
    with keyboard.pressed(Key.cmd):
        keyboard.press("v")
        keyboard.release("v")
    time.sleep(0.4)  # let the target app read the clipboard before we restore it
    subprocess.run(["pbcopy"], input=previous, env=_UTF8_ENV)


def notify(title: str, message: str) -> None:
    script = f"display notification {_quote(message)} with title {_quote(title)}"
    subprocess.run(["osascript", "-e", script], check=False)


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

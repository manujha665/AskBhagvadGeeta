"""macOS glue: which app is in front, reading the selection, and typing text into it."""

from __future__ import annotations

import subprocess
import time


def frontmost_app() -> str:
    try:
        from AppKit import NSWorkspace

        return NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
    except Exception:
        return "a text field"


def _pasteboard():
    from AppKit import NSPasteboard

    return NSPasteboard.generalPasteboard()


def _get_clipboard(board) -> str | None:
    from AppKit import NSPasteboardTypeString

    return board.stringForType_(NSPasteboardTypeString)


def _set_clipboard(board, text: str | None) -> None:
    from AppKit import NSPasteboardTypeString

    board.clearContents()
    if text is not None:
        board.setString_forType_(text, NSPasteboardTypeString)


def _press_cmd(letter: str) -> None:
    from pynput.keyboard import Controller, Key

    keyboard = Controller()
    with keyboard.pressed(Key.cmd):
        keyboard.press(letter)
        keyboard.release(letter)


def copy_selection(timeout: float = 0.5) -> str:
    """Text selected in the front app, or '' if nothing is selected. Clipboard is restored."""
    board = _pasteboard()
    before = board.changeCount()
    previous = _get_clipboard(board)
    _press_cmd("c")
    # With nothing selected, most apps ignore ⌘C and the clipboard never changes.
    deadline = time.monotonic() + timeout
    while board.changeCount() == before and time.monotonic() < deadline:
        time.sleep(0.02)
    if board.changeCount() == before:
        return ""
    selected = _get_clipboard(board) or ""
    _set_clipboard(board, previous)
    return selected


def paste_text(text: str) -> None:
    """Paste via the clipboard (works in every app), then restore the old clipboard."""
    board = _pasteboard()
    previous = _get_clipboard(board)
    _set_clipboard(board, text)
    _press_cmd("v")
    time.sleep(0.4)  # let the target app read the clipboard before we restore it
    _set_clipboard(board, previous)


def notify(title: str, message: str) -> None:
    script = f"display notification {_quote(message)} with title {_quote(title)}"
    subprocess.run(["osascript", "-e", script], check=False)


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

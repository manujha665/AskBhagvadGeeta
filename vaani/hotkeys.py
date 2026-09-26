"""Global hotkeys and synthetic keystrokes via Quartz event taps.

Works only with raw key codes, so it never calls the keyboard-layout APIs (TIS*) that
recent macOS versions only allow on the main thread; pynput calls those from its listener
thread, which can crash or silently stall on Sonoma and later.
"""

from __future__ import annotations

import threading
from typing import Callable

# Carbon virtual key codes (Events.h), stable across macOS versions and keyboard layouts.
KEYCODES = {
    "cmd_r": 0x36, "cmd": 0x37,
    "alt_r": 0x3D, "alt": 0x3A,
    "ctrl_r": 0x3E, "ctrl": 0x3B,
    "shift_r": 0x3C, "shift": 0x38,
    "fn": 0x3F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A, "f17": 0x40,
    "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
}
LABELS = {"cmd_r": "Right ⌘", "alt_r": "Right ⌥", "ctrl_r": "Right ⌃", "shift_r": "Right ⇧"}

# Device-dependent modifier bits (IOLLEvent.h) tell left and right keys apart; the generic
# "command is down" flag can't, so holding left ⌘ would look like right ⌘ still held.
_MODIFIER_BITS = {
    0x37: 0x00000008, 0x36: 0x00000010,  # left / right command
    0x3A: 0x00000020, 0x3D: 0x00000040,  # left / right option
    0x3B: 0x00000001, 0x3E: 0x00002000,  # left / right control
    0x38: 0x00000002, 0x3C: 0x00000004,  # left / right shift
    0x3F: 0x00800000,                    # fn
}

# CGEventType values (CGEventTypes.h).
KEY_DOWN, KEY_UP, FLAGS_CHANGED = 10, 11, 12
TAP_DISABLED_BY_TIMEOUT, TAP_DISABLED_BY_USER_INPUT = 0xFFFFFFFE, 0xFFFFFFFF


def keycode_for(name: str) -> int:
    try:
        return KEYCODES[name]
    except KeyError:
        raise ValueError(f"Unknown key '{name}'. Use one of: {', '.join(KEYCODES)}") from None


def label_for(name: str) -> str:
    return LABELS.get(name, name)


def classify(event_type: int, keycode: int, flags: int) -> bool | None:
    """True for a press, False for a release, None for events that are neither."""
    if event_type == KEY_DOWN:
        return True
    if event_type == KEY_UP:
        return False
    if event_type == FLAGS_CHANGED and keycode in _MODIFIER_BITS:
        return bool(flags & _MODIFIER_BITS[keycode])
    return None


class HotkeyListener(threading.Thread):
    """Calls on_press(keycode) / on_release(keycode) for every key, from its own thread."""

    def __init__(self, on_press: Callable[[int], None], on_release: Callable[[int], None],
                 on_error: Callable[[str], None] = print):
        super().__init__(daemon=True)
        self.on_press, self.on_release, self.on_error = on_press, on_release, on_error
        self._tap = None

    def run(self) -> None:
        import Quartz as Q

        mask = (Q.CGEventMaskBit(KEY_DOWN) | Q.CGEventMaskBit(KEY_UP)
                | Q.CGEventMaskBit(FLAGS_CHANGED))
        self._tap = Q.CGEventTapCreate(
            Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
            mask, self._callback, None,
        )
        if self._tap is None:
            self.on_error(
                "Can't watch the keyboard. Grant Input Monitoring to the app running Vaani "
                "(run `python -m vaani doctor`)."
            )
            return
        source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), source, Q.kCFRunLoopDefaultMode)
        Q.CGEventTapEnable(self._tap, True)
        while True:  # same loop shape pynput uses; one-second slices keep it responsive
            Q.CFRunLoopRunInMode(Q.kCFRunLoopDefaultMode, 1, False)

    def _callback(self, _proxy, event_type, event, _refcon):
        import Quartz as Q

        if event_type in (TAP_DISABLED_BY_TIMEOUT, TAP_DISABLED_BY_USER_INPUT):
            Q.CGEventTapEnable(self._tap, True)  # macOS switches off slow taps; turn it back on
            return event
        try:
            keycode = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
            pressed = classify(event_type, keycode, Q.CGEventGetFlags(event))
            if pressed is True:
                self.on_press(keycode)
            elif pressed is False:
                self.on_release(keycode)
        except Exception as e:  # an exception here would take the whole tap down
            self.on_error(f"hotkey handler error: {e}")
        return event


_ANSI_KEYCODES = {"c": 0x08, "v": 0x09}


def press_cmd(letter: str) -> None:
    """Send ⌘+letter to the front app (needs Accessibility permission)."""
    import Quartz as Q

    code = _ANSI_KEYCODES[letter]
    for is_down in (True, False):
        event = Q.CGEventCreateKeyboardEvent(None, code, is_down)
        Q.CGEventSetFlags(event, Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap, event)


def permissions() -> dict[str, bool | None]:
    """Input Monitoring (to see hotkeys) and Accessibility (to paste); None if unknown."""
    import Quartz as Q

    listen = getattr(Q, "CGPreflightListenEventAccess", None)
    post = getattr(Q, "CGPreflightPostEventAccess", None)
    return {
        "Input Monitoring": bool(listen()) if listen else None,
        "Accessibility": bool(post()) if post else None,
    }


def request_permissions() -> None:
    """Show the macOS permission prompts for anything not yet granted."""
    import Quartz as Q

    for name in ("CGRequestListenEventAccess", "CGRequestPostEventAccess"):
        request = getattr(Q, name, None)
        if request:
            request()

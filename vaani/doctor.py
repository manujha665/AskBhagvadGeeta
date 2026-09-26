"""`python -m vaani doctor`: checks every step Vaani needs and says how to fix what's missing."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
import threading
import time

from .config import Config
from .hotkeys import KEYCODES, HotkeyListener, keycode_for, label_for, permissions, request_permissions

OK, BAD, WARN = "✅", "❌", "⚠️ "

HOST_APPS = {
    "Apple_Terminal": "Terminal",
    "iTerm.app": "iTerm",
    "vscode": "Visual Studio Code (or Cursor)",
    "WarpTerminal": "Warp",
    "ghostty": "Ghostty",
}


def host_app() -> str:
    """macOS grants permissions to the app that launched Python, not to Python itself."""
    return HOST_APPS.get(os.environ.get("TERM_PROGRAM", ""), "the terminal app you're using")


def run(cfg: Config, key_test_seconds: int = 20) -> int:
    problems = 0

    def report(ok: bool | None, label: str, fix: str = "") -> None:
        nonlocal problems
        mark = OK if ok else (WARN if ok is None else BAD)
        print(f"{mark} {label}")
        if not ok and fix:
            print("     " + fix.replace("\n", "\n     "))
        problems += ok is False

    app = host_app()
    print(f"Vaani doctor · macOS {platform.mac_ver()[0] or '?'} · {platform.machine()} · "
          f"Python {platform.python_version()} · running inside {app}\n")

    if sys.platform != "darwin":
        report(False, "This is not a Mac", "Vaani's menu-bar app only runs on macOS.")
        return 1

    # 1. Permissions (the usual culprit)
    perms = permissions()
    missing = [name for name, granted in perms.items() if granted is False]
    for name, granted in perms.items():
        why = "to see the hotkeys" if name == "Input Monitoring" else "to copy the selection and paste"
        report(granted, f"{name} permission ({why})",
               f"System Settings → Privacy & Security → {name} → turn on {app}.")
    if missing:
        request_permissions()
        print(f"\n     macOS only applies these after you QUIT {app} completely (⌘Q, not just\n"
              f"     closing the window) and open it again. Then re-run `python -m vaani doctor`.\n")

    # 2. Claude and Whisper
    report(bool(os.environ.get("ANTHROPIC_API_KEY")), "ANTHROPIC_API_KEY is set",
           "export ANTHROPIC_API_KEY=sk-ant-...  (and add that line to ~/.zshrc)")
    module = "mlx_whisper" if cfg.whisper_backend == "mlx" else "faster_whisper"
    report(importlib.util.find_spec(module) is not None, f"Whisper backend '{module}' installed",
           "pip install -r requirements.txt")
    report(shutil.which("ffmpeg") is not None, "ffmpeg installed (Whisper reads audio with it)",
           "brew install ffmpeg")

    # 3. Microphone: macOS returns pure silence when mic access is denied, so measure a level.
    try:
        import numpy as np
        import sounddevice as sd

        from .recorder import find_device

        device = find_device(cfg.mic_device)
        name = sd.query_devices(device, "input")["name"]
        print(f"\n🎤 Say something for 3 seconds (testing '{name}')...")
        audio = sd.rec(int(3 * 16000), samplerate=16000, channels=1, device=device)
        sd.wait()
        peak = float(np.abs(audio).max())
        report(peak > 0.01, f"Microphone hears you (peak level {peak:.3f})",
               f"Silence usually means mic access is off: System Settings → Privacy & Security →\n"
               f"Microphone → turn on {app}, then quit and reopen it.")
    except Exception as e:
        report(False, "Microphone opens", f"{e}\nbrew install portaudio, then pip install -r requirements.txt")

    # 4. Live hotkey test, using exactly the listener the app uses
    wanted = {keycode_for(cfg.hotkey): cfg.hotkey, keycode_for(cfg.command_hotkey): cfg.command_hotkey}
    names = {code: name for name, code in KEYCODES.items()}
    seen: set[int] = set()
    done = threading.Event()

    def on_press(code: int) -> None:
        if code in wanted:
            print(f"   ↓ {label_for(wanted[code])} pressed")
        elif code in names:
            print(f"   ↓ {names[code]} pressed (not a Vaani hotkey)")

    def on_release(code: int) -> None:
        if code in wanted:
            print(f"   ↑ {label_for(wanted[code])} released")
            seen.add(code)
            if seen == set(wanted):
                done.set()

    errors: list[str] = []
    HotkeyListener(on_press, on_release, on_error=errors.append).start()
    print(f"\n⌨️  Press and release {label_for(cfg.hotkey)}, then {label_for(cfg.command_hotkey)} "
          f"(waiting {key_test_seconds}s)...")
    done.wait(key_test_seconds)
    time.sleep(0.1)
    for label in (cfg.hotkey, cfg.command_hotkey):
        report(keycode_for(label) in seen, f"{label_for(label)} detected",
               errors[0] if errors else
               f"No key events arrived. Turn on Input Monitoring for {app}, quit it with ⌘Q, reopen.\n"
               f"If other keys showed up but not this one, pick another key in ~/.vaani/config.toml.")

    print("\n" + ("All good! Start Vaani with: python -m vaani" if problems == 0
                  else f"{problems} thing(s) to fix above."))
    return 0 if problems == 0 else 1

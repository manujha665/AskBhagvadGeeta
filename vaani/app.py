"""Menu-bar app: hold a key to dictate anywhere, plus voice notes and call recording."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import time
from pathlib import Path

import rumps
from pynput import keyboard

from . import mac
from .config import Config
from .pipeline import Pipeline
from .recorder import Recorder, find_device

IDLE, LISTENING, THINKING, NOTE, MEETING = "🎙", "🔴", "⏳", "📝", "📞"
MIN_PRESS_SECONDS = 0.3  # ignore accidental taps of the hotkey


class VaaniApp(rumps.App):
    def __init__(self, cfg: Config):
        super().__init__("Vaani", title=IDLE, quit_button="Quit Vaani")
        self.cfg = cfg
        self.pipeline = Pipeline(cfg)
        self.tmp = Path(tempfile.mkdtemp(prefix="vaani-"))
        self.status = IDLE
        self.busy = threading.Lock()  # one recording at a time
        self.dictation: Recorder | None = None
        self.note: Recorder | None = None
        self.meeting: tuple[Recorder, Recorder | None] | None = None
        self.pressed_at = 0.0

        self.note_item = rumps.MenuItem("Start voice note", callback=self.toggle_note)
        self.meeting_item = rumps.MenuItem("Start recording call", callback=self.toggle_meeting)
        self.menu = [
            rumps.MenuItem(f"Hold {cfg.hotkey} to dictate"),
            None,
            self.note_item,
            self.meeting_item,
            None,
            rumps.MenuItem("Open notes folder", callback=self.open_notes),
        ]
        self.hotkey = getattr(keyboard.Key, cfg.hotkey)
        keyboard.Listener(on_press=self.on_press, on_release=self.on_release).start()
        # rumps widgets must only be touched on the main thread, so a timer mirrors state.
        rumps.Timer(self.sync_title, 0.2).start()

    def sync_title(self, _timer) -> None:
        if self.title != self.status:
            self.title = self.status

    # ---- push-to-talk dictation -------------------------------------------------

    def on_press(self, key) -> None:
        if key != self.hotkey or self.dictation is not None:
            return
        if not self.busy.acquire(blocking=False):
            return
        self.pressed_at = time.monotonic()
        recorder = Recorder(self.tmp / "dictation.wav", find_device(self.cfg.mic_device))
        if self._start(recorder):
            self.dictation = recorder
            self.status = LISTENING

    def on_release(self, key) -> None:
        if key != self.hotkey or self.dictation is None:
            return
        recorder, self.dictation = self.dictation, None
        audio = recorder.stop()
        if time.monotonic() - self.pressed_at < MIN_PRESS_SECONDS:
            self.finish()
            return
        app_name = mac.frontmost_app()
        self.status = THINKING
        threading.Thread(target=self._dictate, args=(audio, app_name), daemon=True).start()

    def _dictate(self, audio: Path, app_name: str) -> None:
        try:
            text = self.pipeline.dictation(audio, app_name)
            if text:
                mac.paste_text(text)
        except Exception as e:  # keep the app alive; show what went wrong
            mac.notify("Vaani: dictation failed", str(e)[:200])
        finally:
            self.finish()

    # ---- voice notes and calls ---------------------------------------------------

    def toggle_note(self, item) -> None:
        if self.note is None:
            if not self.busy.acquire(blocking=False):
                return
            recorder = Recorder(self.tmp / "note.wav", find_device(self.cfg.mic_device))
            if not self._start(recorder):
                return
            self.note = recorder
            item.title, self.status = "Stop voice note", NOTE
        else:
            audio = self.note.stop()
            self.note = None
            item.title, self.status = "Start voice note", THINKING
            self._background(lambda: self.pipeline.voice_note(audio), "Note saved")

    def toggle_meeting(self, item) -> None:
        if self.meeting is None:
            if not self.busy.acquire(blocking=False):
                return
            mic = Recorder(self.tmp / "me.wav", find_device(self.cfg.mic_device))
            system_index = find_device(self.cfg.system_audio_device)
            other = Recorder(self.tmp / "them.wav", system_index) if system_index is not None else None
            if other is None:
                mac.notify("Vaani", "No call-audio device found; recording your mic only.")
            if not self._start(mic, other):
                return
            self.meeting = (mic, other)
            item.title, self.status = "Stop recording call", MEETING
        else:
            mic, other = self.meeting
            self.meeting = None
            mic_audio = mic.stop()
            other_audio = other.stop() if other else None
            item.title, self.status = "Start recording call", THINKING
            self._background(lambda: self.pipeline.meeting(mic_audio, other_audio), "Call notes saved")

    def _start(self, *recorders: Recorder | None) -> bool:
        """Start recorders; on failure (e.g. no mic permission) release the app and say why."""
        started = []
        try:
            for r in filter(None, recorders):
                r.start()
                started.append(r)
            return True
        except Exception as e:
            for r in started:
                r.stop()
            mac.notify("Vaani: can't record", str(e)[:200])
            self.finish()
            return False

    def _background(self, job, done_message: str) -> None:
        def run():
            try:
                path = job()
                if path:
                    mac.notify("Vaani", f"{done_message}: {path.name}")
                    subprocess.run(["open", str(path)], check=False)
                else:
                    mac.notify("Vaani", "No speech detected.")
            except Exception as e:
                mac.notify("Vaani: processing failed", str(e)[:200])
            finally:
                self.finish()

        threading.Thread(target=run, daemon=True).start()

    def finish(self) -> None:
        self.status = IDLE
        self.busy.release()

    def open_notes(self, _item) -> None:
        self.cfg.notes_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(self.cfg.notes_dir)], check=False)


def run(cfg: Config) -> None:
    VaaniApp(cfg).run()

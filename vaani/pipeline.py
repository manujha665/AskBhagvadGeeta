"""The three workflows, independent of any UI so the CLI and menu bar share them."""

from __future__ import annotations

from pathlib import Path

from .brain import Brain
from .config import Config
from .storage import log_dictation, save_document
from .transcriber import Transcriber, format_transcript, merge_segments


class Pipeline:
    def __init__(self, cfg: Config, transcriber: Transcriber | None = None,
                 brain: Brain | None = None):
        self.cfg = cfg
        self.transcriber = transcriber or Transcriber(cfg)
        self.brain = brain or Brain(cfg)

    def dictation(self, audio: Path, app_name: str) -> str:
        """Speech to ready-to-paste text. Empty string if nothing was said."""
        raw = " ".join(s.text for s in self.transcriber.transcribe(audio)).strip()
        if not raw:
            return ""
        text = self.brain.clean_dictation(raw, app_name) if self.cfg.cleanup_with_claude else raw
        log_dictation(self.cfg.notes_dir, text, app_name)
        return text

    def voice_note(self, audio: Path) -> Path | None:
        transcript = format_transcript(self.transcriber.transcribe(audio))
        if not transcript:
            return None
        body = self.brain.voice_note(transcript)
        return save_document(self.cfg.notes_dir, "notes", body, transcript)

    def meeting(self, mic_audio: Path, system_audio: Path | None) -> Path | None:
        tracks = [self.transcriber.transcribe(mic_audio, speaker="Me")]
        if system_audio is not None:
            tracks.append(self.transcriber.transcribe(system_audio, speaker="Them"))
        transcript = format_transcript(merge_segments(*tracks))
        if not transcript:
            return None
        body = self.brain.meeting_minutes(transcript)
        return save_document(self.cfg.notes_dir, "meetings", body, transcript)

"""Local speech-to-text with Whisper. Audio never leaves the Mac at this stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str = ""


def merge_segments(*tracks: list[Segment]) -> list[Segment]:
    """Interleave per-speaker tracks into one conversation ordered by time."""
    merged = [seg for track in tracks for seg in track]
    return sorted(merged, key=lambda s: (s.start, s.end))


def format_transcript(segments: list[Segment]) -> str:
    lines = []
    for seg in segments:
        stamp = f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}]"
        who = f" {seg.speaker}:" if seg.speaker else ""
        lines.append(f"{stamp}{who} {seg.text}")
    return "\n".join(lines)


class Transcriber:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._fw_model = None

    def _initial_prompt(self) -> str:
        # Whisper copies the style of its prompt, so a mixed-language prompt
        # nudges it to keep Hinglish as spoken instead of translating it.
        prompt = "Namaste. Aaj ki meeting mein hum Q3 results aur SIP flows discuss karenge."
        if self.cfg.vocabulary:
            prompt += " Terms: " + ", ".join(self.cfg.vocabulary) + "."
        return prompt

    def transcribe(self, audio_path: Path, speaker: str = "") -> list[Segment]:
        language = None if self.cfg.language == "auto" else self.cfg.language
        if self.cfg.whisper_backend == "mlx":
            raw = self._transcribe_mlx(audio_path, language)
        elif self.cfg.whisper_backend == "faster-whisper":
            raw = self._transcribe_faster_whisper(audio_path, language)
        else:
            raise ValueError(f"Unknown whisper_backend '{self.cfg.whisper_backend}'")
        return [
            Segment(start, end, text.strip(), speaker)
            for start, end, text in raw
            if text.strip()
        ]

    def _transcribe_mlx(self, audio_path: Path, language: str | None):
        import mlx_whisper

        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self.cfg.mlx_model,
            language=language,
            initial_prompt=self._initial_prompt(),
            condition_on_previous_text=False,  # stops runaway repetition on long calls
        )
        return [(s["start"], s["end"], s["text"]) for s in result["segments"]]

    def _transcribe_faster_whisper(self, audio_path: Path, language: str | None):
        from faster_whisper import WhisperModel

        if self._fw_model is None:
            self._fw_model = WhisperModel(self.cfg.faster_whisper_model, compute_type="int8")
        segments, _info = self._fw_model.transcribe(
            str(audio_path),
            language=language,
            initial_prompt=self._initial_prompt(),
            vad_filter=True,  # skips silence, which is where Whisper hallucinates
        )
        return [(s.start, s.end, s.text) for s in segments]

"""User settings, loaded from ~/.vaani/config.toml (every key is optional)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_PATH = Path.home() / ".vaani" / "config.toml"


@dataclass
class Config:
    # "auto" lets Whisper detect; "hi" or "en" forces a language.
    language: str = "auto"
    # How Hindi should be written in the final text: "as-spoken", "roman", or "devanagari".
    output_script: str = "as-spoken"

    # "mlx" (Apple Silicon, fastest) or "faster-whisper" (Intel Macs / fallback).
    whisper_backend: str = "mlx"
    mlx_model: str = "mlx-community/whisper-large-v3-turbo"
    faster_whisper_model: str = "large-v3-turbo"

    claude_model: str = "claude-opus-5"
    # Turn off to paste the raw Whisper transcript with no Claude call (offline mode).
    cleanup_with_claude: bool = True

    # Any pynput Key name: alt_r (Right Option), cmd_r, ctrl_r, f13 ...
    hotkey: str = "alt_r"
    # Hold to speak an instruction that edits the selected text (or writes new text).
    command_hotkey: str = "cmd_r"
    # Substring of the input device name; None = system default mic.
    mic_device: str | None = None
    # Virtual device that carries the other side of a call (see README).
    system_audio_device: str | None = "BlackHole"

    notes_dir: Path = Path.home() / "Documents" / "Vaani"
    # Names, tickers, jargon that Whisper tends to mangle.
    vocabulary: list[str] = field(default_factory=list)


def load_config(path: Path = CONFIG_PATH) -> Config:
    cfg = Config()
    if not path.exists():
        return cfg
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(Config)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown setting '{key}' in {path}")
        if key == "notes_dir":
            value = Path(value).expanduser()
        setattr(cfg, key, value)
    if cfg.hotkey == cfg.command_hotkey:
        raise ValueError("hotkey and command_hotkey must be different keys")
    return cfg

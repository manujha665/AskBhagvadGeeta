"""Streams an input device straight to a WAV file so hour-long calls don't fill RAM."""

from __future__ import annotations

import queue
import threading
from pathlib import Path


def find_device(name_part: str | None) -> int | None:
    """Index of the first input device whose name contains name_part, else None."""
    if not name_part:
        return None
    import sounddevice as sd

    for index, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and name_part.lower() in dev["name"].lower():
            return index
    return None


def list_input_devices() -> list[str]:
    import sounddevice as sd

    return [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0]


class Recorder:
    def __init__(self, path: Path, device: int | None = None):
        self.path = path
        self.device = device
        self._queue: queue.Queue = queue.Queue()
        self._stream = None
        self._writer = None
        self.seconds = 0.0

    def start(self) -> None:
        import sounddevice as sd
        import soundfile as sf

        info = sd.query_devices(self.device, "input")
        samplerate = int(info["default_samplerate"])
        channels = min(2, int(info["max_input_channels"]))
        self._file = sf.SoundFile(
            str(self.path), "w", samplerate=samplerate, channels=1, subtype="PCM_16"
        )
        self._samplerate = samplerate
        self._writer = threading.Thread(target=self._drain, daemon=True)
        self._writer.start()
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=samplerate,
            channels=channels,
            callback=lambda data, frames, t, status: self._queue.put(data.copy()),
        )
        self._stream.start()

    def _drain(self) -> None:
        while (block := self._queue.get()) is not None:
            mono = block.mean(axis=1) if block.ndim > 1 else block
            self._file.write(mono)
            self.seconds += len(mono) / self._samplerate

    def stop(self) -> Path:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        self._queue.put(None)
        if self._writer is not None:
            self._writer.join()
        self._file.close()
        return self.path

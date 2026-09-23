"""Entry point.

    python -m vaani                         menu-bar app
    python -m vaani devices                 list microphones / virtual devices
    python -m vaani file call.m4a --meeting notes from an existing recording
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vaani")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("devices", help="list audio input devices")
    f = sub.add_parser("file", help="transcribe an existing audio/video file")
    f.add_argument("path", type=Path)
    mode = f.add_mutually_exclusive_group()
    mode.add_argument("--meeting", action="store_true", help="meeting minutes")
    mode.add_argument("--raw", action="store_true", help="print the transcript only")
    args = parser.parse_args(argv)

    cfg = load_config()

    if args.command == "devices":
        from .recorder import list_input_devices

        print("\n".join(list_input_devices()))
        return 0

    if args.command == "file":
        if not args.path.exists():
            print(f"No such file: {args.path}", file=sys.stderr)
            return 1
        from .pipeline import Pipeline
        from .transcriber import format_transcript

        pipeline = Pipeline(cfg)
        if args.raw:
            print(format_transcript(pipeline.transcriber.transcribe(args.path)))
            return 0
        saved = pipeline.meeting(args.path, None) if args.meeting else pipeline.voice_note(args.path)
        print(saved or "No speech detected.")
        return 0

    from .app import run

    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())

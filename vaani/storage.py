"""Everything is saved as plain markdown: greppable, syncable, and Obsidian-friendly."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path


def slugify(text: str, limit: int = 60) -> str:
    # Drop punctuation and symbols by Unicode category; a \w regex would also strip
    # Devanagari vowel signs (matras) and mangle Hindi titles.
    slug = "".join(c for c in text.lower() if c == "-" or unicodedata.category(c)[0] not in "PS")
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug[:limit].rstrip("-") or "untitled"


def title_of(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled"


def save_document(notes_dir: Path, kind: str, body: str, transcript: str,
                  now: datetime | None = None) -> Path:
    """Write notes plus the full transcript to <notes_dir>/<kind>/<date>-<title>.md."""
    now = now or datetime.now()
    folder = notes_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%d-%H%M}-{slugify(title_of(body))}.md"
    path.write_text(
        f"{body.rstrip()}\n\n---\n\n<details><summary>Full transcript</summary>\n\n"
        f"{transcript}\n\n</details>\n",
        encoding="utf-8",
    )
    return path


def log_dictation(notes_dir: Path, text: str, app_name: str,
                  now: datetime | None = None) -> Path:
    """Append to a daily log so nothing you dictated is ever lost."""
    now = now or datetime.now()
    folder = notes_dir / "dictations"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y-%m-%d}.md"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"**{now:%H:%M}** · {app_name}\n\n{text}\n\n")
    return path

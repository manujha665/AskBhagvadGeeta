# Vaani — voice-to-text for your Mac, in Hindi, English and Hinglish

Vaani lives in the macOS menu bar and does three things:

| Mode | How | What you get |
|---|---|---|
| **Dictate anywhere** | Hold **Right Option**, speak, release | Clean text pasted into whatever app is in front (Mail, Slack, WhatsApp, Notion, Docs). Filler words are removed and self-corrections are applied ("5 baje, nahi 6 baje" → "6 baje"). Tone follows the app you're typing into. |
| **Voice notes** | Menu → *Start voice note* | A markdown note with a title, summary, key points, action items, and "ideas worth expanding" (content angles). |
| **Call notes** | Menu → *Start recording call* | Works with Zoom, Meet, Teams or WhatsApp calls. It records you and the other side separately, so the transcript says who spoke ("Me" / "Them"). Minutes include decisions, action items, **numbers mentioned**, open questions, and a draft follow-up email. |

Everything is saved as plain markdown under `~/Documents/Vaani/` (`dictations/`, `notes/`, `meetings/`), so it opens in Obsidian and syncs with iCloud.

**Privacy:** speech-to-text runs **on your Mac** (Whisper large-v3-turbo). Only the text transcript goes to Claude for cleanup and notes. Set `cleanup_with_claude = false` to keep everything fully offline and paste the raw transcript.

## Setup (about 10 minutes)

Requires macOS, Python 3.11+ and Homebrew. Apple Silicon (M1 or later) is strongly recommended.

```bash
brew install python@3.12 portaudio ffmpeg
git clone <this repo> vaani && cd vaani
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # put this in ~/.zshrc too
python -m vaani
```

A 🎙 appears in the menu bar. The first dictation downloads the Whisper model (~1.5 GB, one time only).

**Permissions** (System Settings → Privacy & Security). Grant each of these to *Terminal* (or iTerm, or whichever app runs Vaani):
- **Microphone**: to record.
- **Accessibility** and **Input Monitoring**: to detect the hotkey and paste text.

Restart Vaani after granting them.

### Capturing the other side of a call

macOS doesn't let apps record other apps' audio directly, so you route it through a free virtual device:

1. `brew install blackhole-2ch`, then restart your Mac.
2. Open **Audio MIDI Setup** → **+** → **Create Multi-Output Device**. Tick your headphones/speakers **and** BlackHole 2ch.
3. Before a call, set your Mac's sound output to that Multi-Output Device. You'll still hear everything, and Vaani hears it too.

`python -m vaani devices` lists what Vaani can see. Without BlackHole, call mode records only your mic.

### Already have a recording?

```bash
python -m vaani file zoom_call.m4a --meeting   # minutes
python -m vaani file memo.m4a                  # voice note
python -m vaani file podcast.mp3 --raw         # plain transcript
```

## Settings

Create `~/.vaani/config.toml` (every line is optional):

```toml
language = "hi"            # "auto", "hi" or "en". "hi" is most reliable for Hinglish
output_script = "roman"    # "as-spoken", "roman" (Hinglish) or "devanagari"
hotkey = "alt_r"           # alt_r = Right Option; also cmd_r, ctrl_r, f13 …
vocabulary = ["Nifty", "SIP", "Vatayan Labs", "EBITDA", "HDFC"]  # names Whisper mishears
notes_dir = "~/Documents/Vaani"
whisper_backend = "mlx"    # use "faster-whisper" on Intel Macs
cleanup_with_claude = true
```

**Tip:** short clips in "auto" mode sometimes get detected as the wrong language. If you mostly speak Hinglish, set `language = "hi"` and pick your `output_script`.

## How it works

```
hotkey / menu ─► Recorder (sounddevice → WAV on disk)
                    │
                    ▼
            Transcriber (Whisper, local)  ── mic track "Me" + BlackHole track "Them"
                    │                          merged by timestamp
                    ▼
               Brain (Claude)  ── dictation cleanup · voice note · meeting minutes
                    │
                    ▼
     paste into front app  /  ~/Documents/Vaani/*.md
```

| File | Role |
|---|---|
| `vaani/app.py` | Menu bar, hotkey, recording state |
| `vaani/recorder.py` | Streams audio to disk (safe for 2-hour calls) |
| `vaani/transcriber.py` | Whisper (mlx or faster-whisper), speaker merge |
| `vaani/brain.py` | Claude prompts |
| `vaani/pipeline.py` | The three workflows, shared by the app and CLI |
| `vaani/storage.py` | Markdown output |
| `vaani/mac.py` | Frontmost app, paste, notifications |

Run the tests with `pip install -r requirements-dev.txt && pytest`.

## Roadmap

- **Command mode**: select text, hold the hotkey, and say "make this more formal" or "translate to Hindi".
- **Live captions** during calls (streaming transcription).
- **Auto-detect calls**: start recording when Zoom or Meet opens the mic.
- **Native Swift app** using ScreenCaptureKit, so calls can be captured without BlackHole, and a signed `.app` you can share.
- **Search across all notes** ("what did Ravi say about the IPO last month?").
- **Personal dictionary** that learns from your corrections.

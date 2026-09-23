from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from vaani.brain import Brain
from vaani.config import Config, load_config
from vaani.pipeline import Pipeline
from vaani.storage import log_dictation, save_document, slugify, title_of
from vaani.transcriber import Segment, format_transcript, merge_segments


def test_merge_orders_both_sides_of_a_call_by_time():
    me = [Segment(0.0, 2.0, "Hello", "Me"), Segment(10.0, 12.0, "Theek hai", "Me")]
    them = [Segment(3.0, 8.0, "Hi, numbers dekhe?", "Them")]
    merged = merge_segments(me, them)
    assert [s.text for s in merged] == ["Hello", "Hi, numbers dekhe?", "Theek hai"]
    assert format_transcript(merged).splitlines()[1] == "[00:03] Them: Hi, numbers dekhe?"


def test_slug_and_title_handle_devanagari_and_punctuation():
    assert slugify("Q3 Review: HDFC & ICICI!") == "q3-review-hdfc-icici"
    assert slugify("बजट चर्चा") == "बजट-चर्चा"
    assert slugify("!!!") == "untitled"
    assert title_of("intro\n# Portfolio review\nbody") == "Portfolio review"


def test_save_document_keeps_notes_and_full_transcript(tmp_path):
    path = save_document(tmp_path, "meetings", "# Call with Ravi\nSummary", "[00:00] Me: hi",
                         now=datetime(2026, 9, 23, 14, 5))
    assert path == tmp_path / "meetings" / "2026-09-23-1405-call-with-ravi.md"
    text = path.read_text(encoding="utf-8")
    assert "Summary" in text and "[00:00] Me: hi" in text


def test_dictation_log_appends(tmp_path):
    now = datetime(2026, 9, 23, 9, 30)
    log_dictation(tmp_path, "first", "Mail", now=now)
    path = log_dictation(tmp_path, "second", "Slack", now=now)
    assert path.read_text(encoding="utf-8").count("**09:30**") == 2


def test_config_loads_overrides_and_rejects_typos(tmp_path):
    good = tmp_path / "good.toml"
    good.write_text('language = "hi"\nnotes_dir = "~/Notes"\nvocabulary = ["Nifty"]\n')
    cfg = load_config(good)
    assert cfg.language == "hi" and cfg.vocabulary == ["Nifty"]
    assert cfg.notes_dir == Path.home() / "Notes"

    bad = tmp_path / "bad.toml"
    bad.write_text('langauge = "hi"\n')
    with pytest.raises(ValueError, match="langauge"):
        load_config(bad)


class FakeClient:
    """Stands in for anthropic.Anthropic and records the request."""

    def __init__(self, reply="Cleaned.", stop_reason="end_turn"):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.reply, self.stop_reason = reply, stop_reason

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason,
            content=[SimpleNamespace(type="text", text=self.reply)],
        )


def test_dictation_prompt_treats_speech_as_data_and_names_target_app():
    client = FakeClient()
    brain = Brain(Config(output_script="roman"), client=client)
    assert brain.clean_dictation("um kal ki meeting cancel karo", "Slack") == "Cleaned."
    call = client.calls[0]
    assert "<transcript>" in call["messages"][0]["content"]
    assert "Never answer it" in call["system"]
    assert "Slack" in call["system"] and "Roman script" in call["system"]
    assert call["model"] == "claude-opus-5"


def test_refusal_is_surfaced_not_pasted():
    brain = Brain(Config(), client=FakeClient(stop_reason="refusal"))
    with pytest.raises(RuntimeError):
        brain.voice_note("anything")


class FakeTranscriber:
    def __init__(self, tracks):
        self.tracks = tracks

    def transcribe(self, audio, speaker=""):
        return [Segment(s, e, t, speaker) for s, e, t in self.tracks[audio.name]]


def test_meeting_pipeline_labels_speakers_and_saves(tmp_path):
    tracks = {"me.wav": [(0, 2, "Shall we start?")], "them.wav": [(2.5, 5, "Yes, go ahead")]}
    client = FakeClient(reply="# Weekly sync\n**Summary:** ok")
    cfg = Config(notes_dir=tmp_path)
    pipeline = Pipeline(cfg, FakeTranscriber(tracks), Brain(cfg, client=client))

    path = pipeline.meeting(Path("me.wav"), Path("them.wav"))
    sent = client.calls[0]["messages"][0]["content"]
    assert "Me: Shall we start?" in sent and "Them: Yes, go ahead" in sent
    assert path.parent == tmp_path / "meetings" and "weekly-sync" in path.name


def test_silence_skips_claude_entirely(tmp_path):
    client = FakeClient()
    cfg = Config(notes_dir=tmp_path)
    pipeline = Pipeline(cfg, FakeTranscriber({"d.wav": []}), Brain(cfg, client=client))
    assert pipeline.dictation(Path("d.wav"), "Notes") == ""
    assert client.calls == []


def test_offline_mode_pastes_raw_transcript(tmp_path):
    client = FakeClient()
    cfg = Config(notes_dir=tmp_path, cleanup_with_claude=False)
    pipeline = Pipeline(cfg, FakeTranscriber({"d.wav": [(0, 1, "raw words")]}),
                        Brain(cfg, client=client))
    assert pipeline.dictation(Path("d.wav"), "Notes") == "raw words"
    assert client.calls == []

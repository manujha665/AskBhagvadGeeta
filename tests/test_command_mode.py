"""Command mode: prompts, pipeline, selection capture, and hotkey handling.

macOS-only modules (AppKit, pynput, rumps) are replaced with small fakes so this runs anywhere.
"""

import sys
import types
from pathlib import Path

import pytest

from vaani.brain import Brain
from vaani.config import Config, load_config
from vaani.pipeline import Pipeline
from test_vaani import FakeClient, FakeTranscriber


# ---- prompts and pipeline ----------------------------------------------------------

def test_edit_prompt_sends_selection_as_material_not_instructions():
    client = FakeClient(reply="Dear Sir, ...")
    brain = Brain(Config(), client=client)
    brain.command("isko formal bana do", "bhai kal milte hai", "Mail")
    call = client.calls[0]
    content = call["messages"][0]["content"]
    assert "<instruction>\nisko formal bana do\n</instruction>" in content
    assert "<selected_text>\nbhai kal milte hai\n</selected_text>" in content
    assert "replaces the selection" in call["system"]
    assert "not requests to you" in call["system"]
    assert "Mail" in call["system"]


def test_write_prompt_when_nothing_is_selected():
    client = FakeClient()
    Brain(Config(), client=client).command("write a thank-you note", "  \n", "Slack")
    call = client.calls[0]
    assert "<selected_text>" not in call["messages"][0]["content"]
    assert "Nothing is selected" in call["system"]


def test_command_pipeline_logs_instruction(tmp_path):
    client = FakeClient(reply="Formal text.")
    cfg = Config(notes_dir=tmp_path)
    pipeline = Pipeline(cfg, FakeTranscriber({"c.wav": [(0, 1, "make it formal")]}),
                        Brain(cfg, client=client))
    assert pipeline.command(Path("c.wav"), "Mail", "hey") == "Formal text."
    log = next((tmp_path / "dictations").iterdir()).read_text(encoding="utf-8")
    assert "command: make it formal" in log and "Formal text." in log


def test_command_refuses_to_run_in_offline_mode(tmp_path):
    cfg = Config(notes_dir=tmp_path, cleanup_with_claude=False)
    pipeline = Pipeline(cfg, FakeTranscriber({"c.wav": [(0, 1, "shorten")]}),
                        Brain(cfg, client=FakeClient()))
    with pytest.raises(RuntimeError, match="needs Claude"):
        pipeline.command(Path("c.wav"), "Mail", "text")


def test_config_rejects_same_key_for_both_modes(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('hotkey = "cmd_r"\n')
    with pytest.raises(ValueError, match="different keys"):
        load_config(path)


# ---- selection capture against a fake clipboard ------------------------------------

class FakePasteboard:
    def __init__(self, text, app_selection):
        self.text, self.count, self.app_selection = text, 0, app_selection

    def changeCount(self):
        return self.count

    def stringForType_(self, _type):
        return self.text

    def clearContents(self):
        self.text, self.count = None, self.count + 1

    def setString_forType_(self, text, _type):
        self.text = text


@pytest.fixture
def fake_mac(monkeypatch):
    """Returns a function that installs a fake clipboard + keyboard for vaani.mac."""
    from vaani import mac

    def install(clipboard, app_selection):
        board = FakePasteboard(clipboard, app_selection)
        pressed = []

        def press(letter):
            pressed.append(letter)
            if letter == "c" and board.app_selection:  # the app copies only if text is selected
                board.clearContents()
                board.setString_forType_(board.app_selection, None)

        appkit = types.SimpleNamespace(NSPasteboardTypeString="public.utf8-plain-text")
        monkeypatch.setitem(sys.modules, "AppKit", appkit)
        monkeypatch.setattr(mac, "_pasteboard", lambda: board)
        monkeypatch.setattr(mac, "_press_cmd", press)
        monkeypatch.setattr(mac.time, "sleep", lambda _s: None)
        return board, pressed

    return install


def test_copy_selection_returns_text_and_restores_clipboard(fake_mac):
    from vaani import mac

    board, pressed = fake_mac(clipboard="my old clipboard", app_selection="राम राम, kal milte hai")
    assert mac.copy_selection() == "राम राम, kal milte hai"
    assert board.text == "my old clipboard"
    assert pressed == ["c"]


def test_copy_selection_is_empty_when_nothing_selected(fake_mac):
    from vaani import mac

    board, _ = fake_mac(clipboard="keep me", app_selection="")
    assert mac.copy_selection(timeout=0.01) == ""
    assert board.text == "keep me"


def test_paste_restores_previous_clipboard(fake_mac):
    from vaani import mac

    board, pressed = fake_mac(clipboard="keep me", app_selection="")
    mac.paste_text("new text")
    assert pressed == ["v"] and board.text == "keep me"


# ---- hotkey handling in the menu-bar app --------------------------------------------

class Key:
    alt_r, cmd_r, cmd, shift = "alt_r", "cmd_r", "cmd", "shift"


@pytest.fixture
def app(monkeypatch, tmp_path):
    rumps = types.ModuleType("rumps")
    rumps.App = type("App", (), {"__init__": lambda self, *a, **k: None})
    rumps.MenuItem = lambda *a, **k: types.SimpleNamespace(title=a[0] if a else "")
    rumps.Timer = lambda *a: types.SimpleNamespace(start=lambda: None)
    keyboard = types.ModuleType("pynput.keyboard")
    keyboard.Key = Key
    keyboard.Listener = lambda **k: types.SimpleNamespace(start=lambda: None)
    pynput = types.ModuleType("pynput")
    pynput.keyboard = keyboard
    monkeypatch.setitem(sys.modules, "rumps", rumps)
    monkeypatch.setitem(sys.modules, "pynput", pynput)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)
    monkeypatch.delitem(sys.modules, "vaani.app", raising=False)
    import vaani.app as app_module

    class FakeRecorder:
        def __init__(self, path, device=None):
            self.path = path

        def start(self):
            pass

        def stop(self):
            return self.path

    monkeypatch.setattr(app_module, "Recorder", FakeRecorder)
    monkeypatch.setattr(app_module, "find_device", lambda name: None)
    monkeypatch.setattr(app_module.mac, "frontmost_app", lambda: "Mail")
    monkeypatch.setattr(app_module.mac, "copy_selection", lambda: "hey bro")
    pasted = []
    monkeypatch.setattr(app_module.mac, "paste_text", pasted.append)
    monkeypatch.setattr(app_module.mac, "notify", lambda *a: pasted.append(("notify", a)))

    vaani_app = app_module.VaaniApp(Config(notes_dir=tmp_path))
    calls = []
    vaani_app.pipeline = types.SimpleNamespace(
        dictation=lambda audio, app: calls.append(("dictate", app)) or "dictated",
        command=lambda audio, app, sel: calls.append(("command", app, sel)) or "Dear Sir",
    )
    # Run background work inline so tests are deterministic.
    monkeypatch.setattr(app_module.threading, "Thread",
                        lambda target, args=(), daemon=None: types.SimpleNamespace(start=lambda: target(*args)))
    monkeypatch.setattr(app_module, "MIN_PRESS_SECONDS", -1)  # every hold counts
    return vaani_app, app_module, calls, pasted


def test_holding_command_key_edits_selection(app):
    vaani_app, _, calls, pasted = app
    vaani_app.on_press(Key.cmd_r)
    assert vaani_app.status == "✨"
    vaani_app.on_release(Key.cmd_r)
    assert calls == [("command", "Mail", "hey bro")]
    assert pasted == ["Dear Sir"]
    assert vaani_app.status == "🎙" and not vaani_app.busy.locked()


def test_holding_dictation_key_still_dictates(app):
    vaani_app, _, calls, pasted = app
    vaani_app.on_press(Key.alt_r)
    vaani_app.on_release(Key.alt_r)
    assert calls == [("dictate", "Mail")] and pasted == ["dictated"]


def test_keyboard_shortcut_with_hotkey_is_not_treated_as_speech(app):
    vaani_app, _, calls, pasted = app
    vaani_app.on_press(Key.cmd_r)
    vaani_app.on_press("c")          # user pressed ⌘C with the right Command key
    vaani_app.on_release(Key.cmd_r)
    assert calls == [] and pasted == []
    assert not vaani_app.busy.locked()


def test_other_keys_are_ignored_when_idle(app):
    vaani_app, _, calls, _ = app
    vaani_app.on_press(Key.cmd)   # e.g. Vaani's own synthetic ⌘C / ⌘V
    vaani_app.on_release(Key.cmd)
    assert calls == [] and not vaani_app.busy.locked()


def test_short_tap_is_ignored(app, monkeypatch):
    vaani_app, app_module, calls, _ = app
    monkeypatch.setattr(app_module, "MIN_PRESS_SECONDS", 60)
    vaani_app.on_press(Key.cmd_r)
    vaani_app.on_release(Key.cmd_r)
    assert calls == [] and not vaani_app.busy.locked()


def test_failure_is_reported_and_app_recovers(app):
    vaani_app, _, _, pasted = app

    def boom(*_):
        raise RuntimeError("API down")

    vaani_app.pipeline.command = boom
    vaani_app.on_press(Key.cmd_r)
    vaani_app.on_release(Key.cmd_r)
    assert pasted and pasted[0][0] == "notify" and "API down" in pasted[0][1][1]
    assert not vaani_app.busy.locked()
    vaani_app.on_press(Key.alt_r)  # app still usable afterwards
    assert vaani_app.busy.locked()

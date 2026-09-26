import pytest

from vaani.hotkeys import FLAGS_CHANGED, KEY_DOWN, KEY_UP, classify, keycode_for, label_for

RIGHT_CMD, LEFT_CMD, RIGHT_OPT, CAPS_LOCK = 0x36, 0x37, 0x3D, 0x39
RIGHT_CMD_BIT, LEFT_CMD_BIT, CMD_FLAG = 0x10, 0x08, 0x100000


def test_right_command_press_and_release():
    assert classify(FLAGS_CHANGED, RIGHT_CMD, CMD_FLAG | RIGHT_CMD_BIT) is True
    assert classify(FLAGS_CHANGED, RIGHT_CMD, 0) is False


def test_releasing_right_command_while_left_is_held_counts_as_release():
    # The generic command flag stays set because left ⌘ is still down.
    assert classify(FLAGS_CHANGED, RIGHT_CMD, CMD_FLAG | LEFT_CMD_BIT) is False


def test_left_command_is_its_own_key():
    assert classify(FLAGS_CHANGED, LEFT_CMD, CMD_FLAG | LEFT_CMD_BIT | RIGHT_CMD_BIT) is True


def test_ordinary_keys_and_unknown_modifiers():
    assert classify(KEY_DOWN, 0x08, 0) is True
    assert classify(KEY_UP, 0x08, 0) is False
    assert classify(FLAGS_CHANGED, CAPS_LOCK, 0x10000) is None


def test_key_names():
    assert keycode_for("cmd_r") == RIGHT_CMD and keycode_for("alt_r") == RIGHT_OPT
    assert label_for("cmd_r") == "Right ⌘"
    with pytest.raises(ValueError, match="Unknown key"):
        keycode_for("right_command")

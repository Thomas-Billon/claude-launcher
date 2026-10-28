"""
Keyboard input of the Windows console, read with msvcrt.

Keys are read as characters: a special key (arrow, Home…) comes as a prefix then
a code, both returned as one string starting with SPECIAL_KEY_PREFIX, so that a
typed letter is never mistaken for an arrow code (K, M…).
"""

import msvcrt
import time

SPECIAL_KEY_PREFIX = "\x00"
POLL_INTERVAL_SECONDS = 0.1
SPECIAL_KEY_PREFIXES = ("\x00", "\xe0")


class Key:
    UP = "\x00H"
    DOWN = "\x00P"
    LEFT = "\x00K"
    RIGHT = "\x00M"
    HOME = "\x00G"
    END = "\x00O"
    DELETE = "\x00S"
    BACKSPACE = "\x08"
    TAB = "\t"
    SPACE = " "
    ENTER = "\r"
    ESC = "\x1b"
    CTRL_C = "\x03"
    CTRL_F = "\x06"


def read_key():
    key = msvcrt.getwch()

    if key in SPECIAL_KEY_PREFIXES:
        return SPECIAL_KEY_PREFIX + msvcrt.getwch()

    return key


def read_key_unless(should_stop_waiting):
    """Returns the next key, or None as soon as should_stop_waiting() is true before a key is pressed."""
    while not msvcrt.kbhit():
        if should_stop_waiting():
            return None

        time.sleep(POLL_INTERVAL_SECONDS)

    return read_key()


def is_typed_character(key):
    """Returns whether the key is a printable character, which a text input inserts."""
    return len(key) == 1 and key.isprintable()

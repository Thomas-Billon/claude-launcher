"""
Keyboard input of the Windows console, read with msvcrt.

Keys are read as characters: a special key (arrow, Home…) comes as a prefix then
a code, both returned as one string starting with SPECIAL_KEY_PREFIX, so that a
typed letter is never mistaken for an arrow code (K, M…).
"""

import msvcrt

SPECIAL_KEY_PREFIX = "\x00"
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
    ENTER = "\r"
    ESC = "\x1b"
    CTRL_C = "\x03"


def read_key():
    key = msvcrt.getwch()

    if key in SPECIAL_KEY_PREFIXES:
        return SPECIAL_KEY_PREFIX + msvcrt.getwch()

    return key


def is_typed_character(key):
    """Returns whether the key is a printable character, which a text input inserts."""
    return len(key) == 1 and key.isprintable()

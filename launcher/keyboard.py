"""
Keyboard input of the Windows console, read with msvcrt.

Menus read bytes (read_menu_key), where an arrow comes as a prefix then a letter
code. Text inputs read characters (read_text_key) instead, so that a typed letter
is never mistaken for an arrow code (K, M…).
"""

import msvcrt

ARROW_PREFIX = b"\xe0"
SPECIAL_KEY_PREFIXES = ("\x00", "\xe0")


class MenuKey:
    UP = b"H"
    DOWN = b"P"
    LEFT = b"K"
    RIGHT = b"M"
    ENTER = b"\r"
    ESC = b"\x1b"
    CTRL_C = b"\x03"


class TextKey:
    # INFO: Special keys come as a prefix then a code, both returned as one string by read_text_key
    LEFT = "\x00K"
    RIGHT = "\x00M"
    HOME = "\x00G"
    END = "\x00O"
    DELETE = "\x00S"
    BACKSPACE = "\x08"
    ENTER = "\r"
    ESC = "\x1b"
    CTRL_C = "\x03"


def read_menu_key():
    first_byte = msvcrt.getch()

    if first_byte == ARROW_PREFIX:
        return msvcrt.getch()

    return first_byte


def read_text_key():
    key = msvcrt.getwch()

    if key in SPECIAL_KEY_PREFIXES:
        return SPECIAL_KEY_PREFIXES[0] + msvcrt.getwch()

    return key

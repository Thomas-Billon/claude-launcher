"""
Interactive folder picker that launches Claude Code in the selected project directory.

Lists subfolders of a target directory, lets you navigate with arrow keys
(Up/Down to highlight, Left/Right to move to the parent/child folder), and
launches `claude` in the chosen folder. Remembers the last launch time per
folder (stored in claude_launcher_history.json next to this script, keyed by
absolute path) to sort most-recently-used folders first.

The default directory to scan is read from claude_launcher.config.json next to
this script (see claude_launcher.config.example.json), falling back to the
user's home directory.
"""

import argparse
import json
import msvcrt
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = SCRIPT_DIR / "claude_launcher_history.json"
CONFIG_FILE = SCRIPT_DIR / "claude_launcher.config.json"

KEY_UP = b"H"
KEY_DOWN = b"P"
KEY_LEFT = b"K"
KEY_RIGHT = b"M"
KEY_ENTER = b"\r"
KEY_ESC = b"\x1b"
KEY_CTRL_C = b"\x03"
ARROW_PREFIX = b"\xe0"


def load_target_dir():
    if not CONFIG_FILE.exists():
        return str(Path.home())

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as config_file:
            return json.load(config_file).get("target_dir", str(Path.home()))
    except (json.JSONDecodeError, OSError):
        return str(Path.home())


def load_history():
    if not HISTORY_FILE.exists():
        return {}

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as history_file:
            return json.load(history_file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_history(history):
    with HISTORY_FILE.open("w", encoding="utf-8") as history_file:
        json.dump(history, history_file, indent=2)


def get_subfolder_names(current_dir):
    if not current_dir.is_dir():
        return []

    return [entry.name for entry in current_dir.iterdir() if entry.is_dir()]


def sort_folders_by_history(folder_names, history, current_dir):
    def history_key(name):
        return str(current_dir / name)

    launched = sorted(
        (name for name in folder_names if history_key(name) in history),
        key=lambda name: history[history_key(name)],
        reverse=True,
    )
    never_launched = sorted(name for name in folder_names if history_key(name) not in history)

    return launched + never_launched


def render_menu(current_dir, folder_names, selected_index):
    os.system("cls")

    print(f"Select a folder to launch Claude Code in ({current_dir}):\n")

    if not folder_names:
        print("No subfolders here.")
    else:
        for index, name in enumerate(folder_names):
            prefix = ">" if index == selected_index else " "
            print(f"{prefix} {name}")

    print("\nUp/Down: Highlight   Left/Right: Navigate   Enter: Select   Esc/Ctrl+C: Quit")


def read_key():
    first_byte = msvcrt.getch()

    if first_byte == ARROW_PREFIX:
        return msvcrt.getch()

    return first_byte


def prompt_for_folder(initial_dir, history):
    current_dir = initial_dir
    selected_index = 0
    folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)

    render_menu(current_dir, folder_names, selected_index)

    while True:
        key = read_key()

        if key == KEY_UP and folder_names:
            selected_index = (selected_index - 1) % len(folder_names)
            render_menu(current_dir, folder_names, selected_index)
        elif key == KEY_DOWN and folder_names:
            selected_index = (selected_index + 1) % len(folder_names)
            render_menu(current_dir, folder_names, selected_index)
        elif key == KEY_LEFT:
            parent_dir = current_dir.parent

            if parent_dir != current_dir:
                current_dir = parent_dir
                selected_index = 0
                folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)

            render_menu(current_dir, folder_names, selected_index)
        elif key == KEY_RIGHT and folder_names:
            current_dir = current_dir / folder_names[selected_index]
            selected_index = 0
            folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)
            render_menu(current_dir, folder_names, selected_index)
        elif key == KEY_ENTER and folder_names:
            return current_dir / folder_names[selected_index]
        elif key in (KEY_ESC, KEY_CTRL_C):
            return None


def parse_arguments():
    target_dir = load_target_dir()

    parser = argparse.ArgumentParser(description="Pick a project folder and launch Claude Code in it.")
    parser.add_argument(
        "-d",
        "--directory",
        default=target_dir,
        help=f"Directory to scan for project folders (default: {target_dir})",
    )

    return parser.parse_args()


def main():
    arguments = parse_arguments()
    initial_dir = Path(arguments.directory).resolve()

    if not initial_dir.is_dir():
        print(f'No folders found in "{initial_dir}".')

        return

    history = load_history()
    selected_path = prompt_for_folder(initial_dir, history)

    if selected_path is None:
        print("Cancelled.")

        return

    history[str(selected_path)] = datetime.now(timezone.utc).isoformat()
    save_history(history)

    os.chdir(selected_path)
    os.system("cls")
    subprocess.run("claude", shell=True)


if __name__ == "__main__":
    main()

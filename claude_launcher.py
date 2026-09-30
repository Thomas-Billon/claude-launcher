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

On startup, the claude-skills repo (found through the junction of one of its
installed skills) is fetched; when behind its upstream, it is fast-forward
pulled and its install.ps1 is run so skills and the global CLAUDE.md are up
to date before Claude Code starts.
"""

import argparse
import json
import msvcrt
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = SCRIPT_DIR / "claude_launcher_history.json"
CONFIG_FILE = SCRIPT_DIR / "claude_launcher.config.json"

# INFO: The claude-skills repo path varies per machine, so it is deduced from the target of a junction its install.ps1 creates
SKILLS_JUNCTION = Path.home() / ".claude" / "skills" / "create-personal-skill"
GIT_TIMEOUT_SECONDS = 10
INSTALL_WARNINGS_MARKER = "__INSTALL_WARNINGS__"

KEY_UP = b"H"
KEY_DOWN = b"P"
KEY_LEFT = b"K"
KEY_RIGHT = b"M"
KEY_ENTER = b"\r"
KEY_ESC = b"\x1b"
KEY_CTRL_C = b"\x03"
ARROW_PREFIX = b"\xe0"

RESET = "\033[0m"
CYAN = "\033[96m"
DARK_CYAN = "\033[36m"
DARK_GRAY = "\033[90m"
GREEN = "\033[92m"
WHITE = "\033[97m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLACK_ON_GREEN = "\033[30;102m"

CURSOR_HOME = "\033[H"
CLEAR_LINE_END = "\033[K"
CLEAR_SCREEN_END = "\033[J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Enter: Select   Esc/Ctrl+C: Quit"
MIN_LIST_ROWS = 3


def colorize(text, color):
    return f"{color}{text}{RESET}"


def truncate(text, max_length):
    if len(text) <= max_length:
        return text

    return text[: max_length - 1] + "…"


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


def find_skills_repo():
    if not SKILLS_JUNCTION.exists():
        return None

    repo = SKILLS_JUNCTION.resolve().parent

    return repo if (repo / ".git").exists() else None


def run_command(command, cwd, timeout=None):
    # INFO: GIT_TERMINAL_PROMPT=0 makes git fail instead of hanging on a credential prompt
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def build_install_command(install_script):
    # INFO: Warnings are read from the warning stream rather than the output text, which PowerShell localizes
    escaped_path = str(install_script).replace("'", "''")
    script = (
        f"$warnings = & '{escaped_path}' 3>&1 | Where-Object {{ $_ -is [System.Management.Automation.WarningRecord] }}; "
        "if ($LASTEXITCODE) { exit $LASTEXITCODE }; "
        f"if ($warnings) {{ Write-Output '{INSTALL_WARNINGS_MARKER}' }}"
    )

    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


def update_skills_repo():
    repo = find_skills_repo()

    if repo is None:
        return "claude-skills repo not found", DARK_GRAY

    print(colorize("Checking claude-skills updates…", DARK_GRAY))

    try:
        if run_command(["git", "fetch", "--quiet"], repo, GIT_TIMEOUT_SECONDS).returncode != 0:
            return "update failed (fetch error)", YELLOW

        behind = run_command(["git", "rev-list", "--count", "HEAD..@{u}"], repo)

        if behind.returncode != 0:
            return "update failed (no upstream branch)", YELLOW

        commit_count = int(behind.stdout.strip())

        if commit_count == 0:
            return "up to date", DARK_GRAY

        if run_command(["git", "pull", "--ff-only", "--quiet"], repo, GIT_TIMEOUT_SECONDS).returncode != 0:
            return "update failed (pull refused)", YELLOW

        install = run_command(build_install_command(repo / "install.ps1"), repo)
    except subprocess.TimeoutExpired:
        return "update failed (git timed out)", YELLOW
    except OSError:
        return "update failed (git not found)", YELLOW

    commits = f"{commit_count} new commit{'s' if commit_count > 1 else ''}"

    if install.returncode != 0:
        return f"pulled {commits} but install.ps1 failed", YELLOW

    if INSTALL_WARNINGS_MARKER in install.stdout:
        return f"updated ({commits}), install.ps1 reported warnings", YELLOW

    return f"updated ({commits})", GREEN


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


def get_scroll_offset(scroll_offset, selected_index, visible_rows, item_count):
    if selected_index < scroll_offset:
        scroll_offset = selected_index
    elif selected_index >= scroll_offset + visible_rows:
        scroll_offset = selected_index - visible_rows + 1

    return max(0, min(scroll_offset, item_count - visible_rows))


def render_menu(current_dir, folder_names, selected_index, scroll_offset, skills_status):
    skills_text, skills_color = skills_status
    width, height = shutil.get_terminal_size()
    # INFO: The last column is left empty so the console never wraps a line, which would break the row count
    max_length = width - 1

    lines = [
        "",
        colorize(truncate("  Claude Code Launcher", max_length), CYAN),
        colorize(truncate(f"  {'=' * 40}", max_length), DARK_CYAN),
        colorize(truncate(f"  Directory : {current_dir}", max_length), DARK_GRAY),
        colorize(truncate(f"  Skills    : {skills_text}", max_length), skills_color),
        "",
    ]
    footer = ["", colorize(truncate(HELP_TEXT, max_length), DARK_GRAY)]
    available_rows = max(height - len(lines) - len(footer), MIN_LIST_ROWS)

    if not folder_names:
        lines.append(colorize(truncate("  No subfolders here.", max_length), RED))
    else:
        is_scrollable = len(folder_names) > available_rows
        # INFO: When scrolling, two rows are reserved for the "more" indicators above and below the list
        visible_rows = available_rows - 2 if is_scrollable else len(folder_names)
        scroll_offset = get_scroll_offset(scroll_offset, selected_index, visible_rows, len(folder_names))
        hidden_below = len(folder_names) - scroll_offset - visible_rows

        if is_scrollable:
            lines.append(colorize(f"  ↑ {scroll_offset} more", DARK_GRAY) if scroll_offset > 0 else "")

        for index in range(scroll_offset, scroll_offset + visible_rows):
            name = truncate(folder_names[index], max_length - 4)

            if index == selected_index:
                lines.append(colorize("  > ", GREEN) + colorize(name, BLACK_ON_GREEN))
            else:
                lines.append(colorize(f"    {name}", WHITE))

        if is_scrollable:
            lines.append(colorize(f"  ↓ {hidden_below} more", DARK_GRAY) if hidden_below > 0 else "")

    lines.extend(footer)

    # INFO: The frame overwrites the previous one in place instead of clearing the screen first, which avoids flicker
    sys.stdout.write(CURSOR_HOME + "\n".join(line + CLEAR_LINE_END for line in lines) + CLEAR_SCREEN_END)
    sys.stdout.flush()

    return scroll_offset


def read_key():
    first_byte = msvcrt.getch()

    if first_byte == ARROW_PREFIX:
        return msvcrt.getch()

    return first_byte


def prompt_for_folder(initial_dir, history, skills_status):
    current_dir = initial_dir
    selected_index = 0
    scroll_offset = 0
    folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)

    os.system("cls")
    sys.stdout.write(HIDE_CURSOR)

    try:
        while True:
            scroll_offset = render_menu(current_dir, folder_names, selected_index, scroll_offset, skills_status)
            key = read_key()

            if key == KEY_UP and folder_names:
                selected_index = (selected_index - 1) % len(folder_names)
            elif key == KEY_DOWN and folder_names:
                selected_index = (selected_index + 1) % len(folder_names)
            elif key == KEY_LEFT:
                parent_dir = current_dir.parent

                if parent_dir != current_dir:
                    current_dir = parent_dir
                    selected_index = 0
                    scroll_offset = 0
                    folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)
            elif key == KEY_RIGHT and folder_names:
                current_dir = current_dir / folder_names[selected_index]
                selected_index = 0
                scroll_offset = 0
                folder_names = sort_folders_by_history(get_subfolder_names(current_dir), history, current_dir)
            elif key == KEY_ENTER and folder_names:
                return current_dir / folder_names[selected_index]
            elif key in (KEY_ESC, KEY_CTRL_C):
                return None
    finally:
        sys.stdout.write(SHOW_CURSOR)
        sys.stdout.flush()


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
    # INFO: Empty system call enables ANSI escape code processing in the Windows console
    os.system("")

    arguments = parse_arguments()
    initial_dir = Path(arguments.directory).resolve()

    if not initial_dir.is_dir():
        print(colorize(f'No folders found in "{initial_dir}".', RED))

        return 1

    skills_status = update_skills_repo()
    history = load_history()
    selected_path = prompt_for_folder(initial_dir, history, skills_status)

    if selected_path is None:
        os.system("cls")
        print(colorize("Cancelled.", YELLOW))

        return 0

    history[str(selected_path)] = datetime.now(timezone.utc).isoformat()
    save_history(history)

    os.chdir(selected_path)
    os.system("cls")
    print()
    print(colorize("  Opening Claude Code in:", CYAN))
    print(colorize(f"  {selected_path}", GREEN))
    print()

    return subprocess.run("claude", shell=True).returncode


if __name__ == "__main__":
    sys.exit(main())

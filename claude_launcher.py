"""
Interactive launcher that starts Claude Code with a chosen account in a chosen project directory.

On startup, the claude-skills repo (found through the junction of one of its
installed skills) is fetched; when behind its upstream, it is fast-forward
pulled and its install.ps1 is run so skills and the global CLAUDE.md are up
to date before Claude Code starts.

The Claude account is then picked (see accounts.py): Up/Down to highlight,
Enter to use it (logging in when needed), Right to open its options (use or
delete), Left to close them. A last entry adds a new account.

Finally, subfolders of a target directory are listed (Up/Down to highlight,
Left/Right to move to the parent/child folder) and `claude` is launched in
the chosen folder. The last launch time per folder is remembered per account
(see accounts.py): the most recently opened folders are listed on top, and
subfolders are sorted most-recently-used first.

The folder list starts from the -d argument, else from the default folder of
the account (see accounts.py), else from the user's home directory.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import accounts
from terminal_ui import (
    COLUMN_SEPARATOR,
    CYAN,
    DARK_GRAY,
    GREEN,
    KEY_CTRL_C,
    KEY_ENTER,
    KEY_ESC,
    KEY_LEFT,
    KEY_RIGHT,
    MIN_LIST_ROWS,
    RED,
    SEPARATOR,
    YELLOW,
    ListSelection,
    build_footer,
    build_header,
    clear_screen,
    colorize,
    draw,
    get_screen_size,
    hide_cursor,
    join_columns,
    read_key,
    show_cursor,
    truncate,
)

# INFO: The claude-skills repo path varies per machine, so it is deduced from the target of a junction its install.ps1 creates
SKILLS_JUNCTION = Path.home() / ".claude" / "skills" / "create-personal-skill"
GIT_TIMEOUT_SECONDS = 10
INSTALL_WARNINGS_MARKER = "__INSTALL_WARNINGS__"

FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Enter: Select   Esc: Back   Ctrl+C: Quit"
DEFAULT_FOLDER_HELP_TEXT = "  Up/Down: Highlight   Left/Right: Navigate   Enter: Set as default   Esc: Back   Ctrl+C: Quit"
ACCOUNT_HELP_TEXT = "  Up/Down: Highlight   Right: Options   Enter: Select   Esc/Ctrl+C: Quit"
OPTIONS_HELP_TEXT = "  Up/Down: Highlight   Left/Esc: Back   Enter: Confirm   Ctrl+C: Quit"
HISTORY_HELP_TEXT = "  Up/Down: Highlight   Left/Esc: Back   Enter: Remove from history   Ctrl+C: Quit"

ADD_ACCOUNT_LABEL = "+ Add account"
USE_ACCOUNT = "Use account"
SET_DEFAULT_FOLDER = "Set default folder"
REMOVE_FROM_HISTORY = "Remove from history"
CLEAR_HISTORY = "Clear history"
DELETE_ACCOUNT = "Delete account"
CANCEL = "Cancel"
CONFIRM_CLEAR = "Confirm clear"
CONFIRM_DELETE = "Confirm delete"
ACCOUNT_OPTIONS = [USE_ACCOUNT, SET_DEFAULT_FOLDER, REMOVE_FROM_HISTORY, CLEAR_HISTORY, DELETE_ACCOUNT]
# INFO: Cancel comes first so that a double Enter never clears the history or deletes an account
CLEAR_OPTIONS = [CANCEL, CONFIRM_CLEAR]
DELETE_OPTIONS = [CANCEL, CONFIRM_DELETE]

RECENT_FOLDER_COUNT = 5

# INFO: Menu outcomes besides a selection: Esc goes back one step, Ctrl+C quits from anywhere
BACK = object()
QUIT = object()


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

    try:
        if run_command(["git", "fetch", "--quiet"], repo, GIT_TIMEOUT_SECONDS).returncode != 0:
            return "update failed (fetch error)", YELLOW

        behind = run_command(["git", "rev-list", "--count", "HEAD..@{u}"], repo)

        if behind.returncode != 0:
            return "update failed (no upstream branch)", YELLOW

        commit_count = int(behind.stdout.strip())

        if commit_count == 0:
            return "up to date", GREEN

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


def render_screen(details, render_body=None, help_text=None, message=None):
    max_length, height = get_screen_size()
    header = build_header(max_length, details)
    body = []
    footer = []

    if render_body is not None:
        footer = build_footer(max_length, help_text, message)
        available_rows = max(height - len(header) - len(footer), MIN_LIST_ROWS)
        body = render_body(available_rows, max_length)

    draw(header + body + footer)


def get_skills_detail(skills_status):
    skills_text, skills_color = skills_status

    return "Skills", skills_text, skills_color


def get_account_detail(account):
    return "Account", account.label, GREEN


def run_interactive_login(account):
    show_cursor()
    clear_screen()
    print()
    print(colorize("  Logging in… (complete the login in your browser)", CYAN))
    print()

    accounts.login(account)

    hide_cursor()
    clear_screen()

    return accounts.fetch_status(account)


def account_label(item):
    return ADD_ACCOUNT_LABEL if item is None else item.label


def render_account_menu(selection, options, skills_status, message, help_text):
    def render_body(available_rows, max_length):
        if options is None:
            return selection.render(available_rows, max_length)

        longest_label = max(len(account_label(item)) for item in selection.items)
        left_width = min(longest_label + 4, max_length // 2)
        right_width = max_length - left_width - len(COLUMN_SEPARATOR)

        return join_columns(
            selection.render(available_rows, left_width, has_cursor=False),
            options.render(available_rows, right_width),
            left_width,
        )

    render_screen([get_skills_detail(skills_status)], render_body, help_text, message)


def build_account_selection(account_list, selected_id):
    # INFO: None stands for the "Add account" entry, always last
    items = account_list + [None]
    selected_index = next(
        (index for index, account in enumerate(account_list) if account.account_id == selected_id),
        0,
    )

    return ListSelection(items, account_label, selected_index)


def add_account(account_list):
    account = run_interactive_login(accounts.create_account())

    if not account.logged_in:
        accounts.delete_account(account)

        return None, ("Login cancelled, no account added.", YELLOW)

    if any(existing.email == account.email for existing in account_list):
        # INFO: No logout here, it is not worth risking the session of the account already in the list
        accounts.delete_account(account, logout=False)

        return None, ("This account is already in the list.", YELLOW)

    return account, ("Account added.", GREEN)


def use_account(account):
    if account.logged_in:
        return account, None

    # INFO: The local files can lag behind Claude Code, which has the final say before asking for a new login
    account = accounts.fetch_status(account)

    if account.logged_in:
        return account, None

    account = run_interactive_login(account)

    if not account.logged_in:
        return None, ("Login cancelled.", YELLOW)

    return account, None


def get_start_dir(account):
    default_dir = accounts.load_default_dir(account)

    return default_dir if default_dir is not None and default_dir.is_dir() else Path.home()


def choose_default_dir(account, skills_status):
    selected_path = prompt_for_folder(
        get_start_dir(account),
        skills_status,
        account,
        DEFAULT_FOLDER_HELP_TEXT,
        ("Choose the default folder of this account.", CYAN),
    )

    if selected_path in (BACK, QUIT):
        return selected_path, None

    accounts.save_default_dir(account, selected_path)

    return None, (f"Default folder set to {selected_path}", GREEN)


def build_account_options(selected_option=None):
    return ListSelection(ACCOUNT_OPTIONS, selected_index=ACCOUNT_OPTIONS.index(selected_option) if selected_option else 0)


def build_history_selection(account, selected_index=0):
    history = accounts.load_history(account)
    folders = [Path(folder) for folder in sorted(history, key=history.get, reverse=True)]
    entries = [FolderEntry(folder, format_folder_label(folder)) for folder in folders]

    return ListSelection(entries, lambda entry: entry.label, min(selected_index, len(entries) - 1))


def prompt_for_account(skills_status, selected_id=None):
    render_screen([get_skills_detail(skills_status), ("Account", "loading…", DARK_GRAY)])

    account_list = accounts.load_accounts()
    selection = build_account_selection(account_list, selected_id)
    options = None
    is_history_open = False
    message = None

    while True:
        if options is None:
            help_text = ACCOUNT_HELP_TEXT
        else:
            help_text = HISTORY_HELP_TEXT if is_history_open else OPTIONS_HELP_TEXT

        render_account_menu(selection, options, skills_status, message, help_text)
        key = read_key()
        message = None

        if key == KEY_CTRL_C:
            return QUIT

        if options is None:
            if selection.handle_key(key):
                continue

            if key == KEY_ESC:
                return QUIT
            elif key == KEY_RIGHT and selection.selected is not None:
                options = build_account_options()
            elif key == KEY_ENTER and selection.selected is None:
                added_account, message = add_account(account_list)
                selected_id = added_account.account_id if added_account else None
                account_list = accounts.load_accounts()
                selection = build_account_selection(account_list, selected_id)
            elif key == KEY_ENTER:
                account, message = use_account(selection.selected)

                if account is not None:
                    return account

            continue

        if options.handle_key(key):
            continue

        if is_history_open:
            if key in (KEY_LEFT, KEY_ESC):
                is_history_open = False
                options = build_account_options(REMOVE_FROM_HISTORY)
            elif key == KEY_ENTER:
                removed_folder = options.selected.path
                accounts.remove_from_history(selection.selected, removed_folder)
                message = (f"Removed {removed_folder} from history.", GREEN)
                options = build_history_selection(selection.selected, options.selected_index)

                if options.selected is None:
                    is_history_open = False
                    options = build_account_options(REMOVE_FROM_HISTORY)

            continue

        if key in (KEY_LEFT, KEY_ESC):
            options = None
        elif key == KEY_ENTER and options.selected == USE_ACCOUNT:
            account, message = use_account(selection.selected)
            options = None

            if account is not None:
                return account
        elif key == KEY_ENTER and options.selected == SET_DEFAULT_FOLDER:
            outcome, message = choose_default_dir(selection.selected, skills_status)
            options = None

            if outcome is QUIT:
                return QUIT
        elif key == KEY_ENTER and options.selected in (REMOVE_FROM_HISTORY, CLEAR_HISTORY):
            if not accounts.load_history(selection.selected):
                message = ("The history of this account is empty.", YELLOW)
            elif options.selected == REMOVE_FROM_HISTORY:
                is_history_open = True
                options = build_history_selection(selection.selected)
            else:
                options = ListSelection(CLEAR_OPTIONS)
        elif key == KEY_ENTER and options.selected == CONFIRM_CLEAR:
            accounts.clear_history(selection.selected)
            message = ("History cleared.", GREEN)
            options = build_account_options(CLEAR_HISTORY)
        elif key == KEY_ENTER and options.selected == DELETE_ACCOUNT:
            options = ListSelection(DELETE_OPTIONS)
        elif key == KEY_ENTER and options.selected == CANCEL:
            options = build_account_options(CLEAR_HISTORY if options.items is CLEAR_OPTIONS else DELETE_ACCOUNT)
        elif key == KEY_ENTER and options.selected == CONFIRM_DELETE:
            options = None

            try:
                accounts.delete_account(selection.selected)
                message = ("Account deleted.", GREEN)
            except OSError:
                message = ("Could not fully delete the account, is Claude Code still running with it?", RED)

            account_list = accounts.load_accounts()
            selection = build_account_selection(account_list, None)


@dataclass(frozen=True)
class FolderEntry:
    path: Path
    label: str


def format_folder_label(folder):
    # INFO: The name comes first so that truncating a long label only cuts the parent path
    return f"{folder.name}  ({folder.parent})"


def get_recent_folders(history):
    launched = sorted(history, key=history.get, reverse=True)

    return [Path(folder) for folder in launched if Path(folder).is_dir()][:RECENT_FOLDER_COUNT]


def build_folder_entries(directory, history, show_recent):
    subfolders = [
        FolderEntry(directory / name, name)
        for name in sort_folders_by_history(get_subfolder_names(directory), history, directory)
    ]

    if not show_recent:
        return subfolders

    recent = [FolderEntry(folder, format_folder_label(folder)) for folder in get_recent_folders(history)]

    return recent + [SEPARATOR] + subfolders if recent else subfolders


def render_folder_menu(current_dir, selection, has_subfolders, skills_status, account, help_text, message):
    def render_body(available_rows, max_length):
        if has_subfolders:
            return selection.render(available_rows, max_length)

        no_subfolders = colorize(truncate("  No subfolders here.", max_length), RED)

        return selection.render(max(available_rows - 1, MIN_LIST_ROWS), max_length) + [no_subfolders]

    details = [get_skills_detail(skills_status), get_account_detail(account), ("Directory", current_dir, DARK_GRAY)]
    render_screen(details, render_body, help_text, message)


def prompt_for_folder(initial_dir, skills_status, account, help_text=FOLDER_HELP_TEXT, message=None, show_recent=False):
    history = accounts.load_history(account)

    def build_folder_selection(directory):
        return ListSelection(build_folder_entries(directory, history, show_recent), lambda entry: entry.label)

    current_dir = initial_dir
    selection = build_folder_selection(current_dir)

    while True:
        has_subfolders = any(entry is not SEPARATOR and entry.path.parent == current_dir for entry in selection.items)
        render_folder_menu(current_dir, selection, has_subfolders, skills_status, account, help_text, message)
        key = read_key()

        if selection.handle_key(key):
            continue

        if key == KEY_LEFT and current_dir.parent != current_dir:
            current_dir = current_dir.parent
            selection = build_folder_selection(current_dir)
        elif key == KEY_RIGHT and selection.selected is not None:
            current_dir = selection.selected.path
            selection = build_folder_selection(current_dir)
        elif key == KEY_ENTER and selection.selected is not None:
            return selection.selected.path
        elif key == KEY_ESC:
            return BACK
        elif key == KEY_CTRL_C:
            return QUIT


def parse_arguments():
    parser = argparse.ArgumentParser(description="Pick a Claude account and a project folder, then launch Claude Code.")
    parser.add_argument(
        "-d",
        "--directory",
        help="Directory to scan for project folders (default: the account default folder, then the home directory)",
    )

    return parser.parse_args()


def cancel():
    clear_screen()
    print(colorize("Cancelled.", YELLOW))

    return 0


def pick_launch_target(argument_dir):
    """Runs the launcher steps, each one adding its line to the header, and returns the chosen account and folder."""
    render_screen([("Skills", "checking updates…", DARK_GRAY)])
    skills_status = update_skills_repo()
    account = None

    while True:
        # INFO: Coming back from the folder list keeps the account that was just chosen highlighted
        account = prompt_for_account(skills_status, account.account_id if account else None)

        if account is QUIT:
            return None, None

        start_dir = argument_dir or get_start_dir(account)
        selected_path = prompt_for_folder(start_dir, skills_status, account, show_recent=True)

        if selected_path is QUIT:
            return None, None

        if selected_path is not BACK:
            break

    accounts.record_launch(account, selected_path)

    details = [get_skills_detail(skills_status), get_account_detail(account), ("Directory", selected_path, GREEN)]
    render_screen(details)

    return account, selected_path


def main():
    # INFO: Empty system call enables ANSI escape code processing in the Windows console
    os.system("")

    arguments = parse_arguments()
    argument_dir = Path(arguments.directory).resolve() if arguments.directory else None

    if argument_dir is not None and not argument_dir.is_dir():
        print(colorize(f'No folders found in "{argument_dir}".', RED))

        return 1

    if accounts.find_claude_executable() is None:
        print(colorize("Claude Code CLI (claude) not found in PATH.", RED))

        return 1

    clear_screen()
    hide_cursor()

    try:
        account, selected_path = pick_launch_target(argument_dir)
    finally:
        show_cursor()

    if account is None:
        return cancel()

    failed_links = accounts.prepare_account_dir(account.config_dir)

    if failed_links:
        print(colorize(f"  Warning: could not link shared {', '.join(failed_links)} from ~/.claude", YELLOW))

    print(colorize("  Opening Claude Code…", CYAN))
    print()

    os.chdir(selected_path)

    return subprocess.run(accounts.build_launch_command(), env=accounts.build_environment(account)).returncode


if __name__ == "__main__":
    sys.exit(main())

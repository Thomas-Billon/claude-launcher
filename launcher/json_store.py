"""
JSON files the launcher keeps in the user's home directory, read and written whole.
"""

import json
import os
import tempfile


def load_json(path):
    """Returns the content of the file, or an empty dict when it is missing or invalid."""
    try:
        with path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    # INFO: Written aside then swapped in, so that a launcher running in parallel never reads a half-written file,
    # which it would load as empty and save back, losing everything it held
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as temp_file:
        json.dump(data, temp_file, indent=2)

    os.replace(temp_file.name, path)

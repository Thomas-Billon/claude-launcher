"""
Directory junctions, which link a folder to another one without admin rights.
"""

import subprocess


def create_junction(link, target):
    """Returns whether the junction was created."""
    # INFO: Junctions need no admin rights, unlike directory symlinks
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)

    return result.returncode == 0

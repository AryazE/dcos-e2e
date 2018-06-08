"""
Utilities for the CLI.
"""

import json
import subprocess
from pathlib import Path


def is_enterprise(build_artifact: Path, workspace_dir: Path) -> bool:
    """
    Return whether the build artifact is an Enterprise artifact.
    """
    get_version_args = [
        'bash',
        # We put the path in quotes in case it has spaces in it.
        '"{path}"'.format(path=str(build_artifact)),
        '--version',
    ]
    result = subprocess.check_output(
        args=get_version_args,
        cwd=str(workspace_dir),
        stderr=subprocess.PIPE,
        shell=True,
    )

    result = result.decode()
    result = ' '.join(
        [
            line for line in result.splitlines()
            if not line.startswith('Extracting image')
            and not line.startswith('Loaded image') and '.tar' not in line
        ],
    )

    version_info = json.loads(result)
    variant = version_info['variant']
    return bool(variant == 'ee')

"""Workspace-path helpers shared by runtime nodes and command-line tools."""

from __future__ import annotations

import os
from pathlib import Path


WORKSPACE_ENV = 'RASPBOT_WS'
_WORKSPACE_MARKERS = ('${RASPBOT_WS}', '$RASPBOT_WS')


def workspace_root() -> Path:
    """Return the configured workspace root, defaulting to ``~/ros2_ws``."""
    return Path(os.environ.get(WORKSPACE_ENV, '~/ros2_ws')).expanduser()


def workspace_path(*parts: str) -> Path:
    """Build a path relative to the configured workspace root."""
    return workspace_root().joinpath(*parts)


def resolve_workspace_path(value: str) -> Path:
    """Expand ``~``, environment variables, and the ``$RASPBOT_WS`` marker."""
    raw = str(value)
    for marker in _WORKSPACE_MARKERS:
        if raw == marker:
            raw = str(workspace_root())
        elif raw.startswith(marker + '/'):
            raw = str(workspace_root() / raw[len(marker) + 1:])
    return Path(os.path.expanduser(os.path.expandvars(raw)))

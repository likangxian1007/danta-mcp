"""
run_server.py — launcher for the DanTa MCP server.

Why this exists: the parent process may export PYTHONPATH / VIRTUAL_ENV pointing
at a *different* interpreter's site-packages. Python honours PYTHONPATH ahead of
the venv, which can shadow this venv's `mcp` package with an older one that has
no `mcp.server.fastmcp`. We scrub those before importing anything.

Copyright (C) 2026  danta-mcp contributors

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See <https://www.gnu.org/licenses/gpl-3.0.html>.
"""
import os
import sys

# Drop inherited paths that don't belong to this venv.
_here = os.path.dirname(os.path.abspath(__file__))
_venv = os.path.join(_here, ".venv")

for var in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT"):
    os.environ.pop(var, None)

sys.path = [
    p for p in sys.path
    if p and (
        os.path.abspath(p).startswith(os.path.abspath(_venv))
        or os.path.abspath(p) == os.path.abspath(_here)
        or "hermes-agent" not in os.path.abspath(p).replace("\\", "/")
    )
]
if _here not in sys.path:
    sys.path.insert(0, _here)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

from server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run()

"""PlatformIO pre-build step: compile the web app into the firmware (embed_web.py)."""

import subprocess
import sys
from pathlib import Path

Import("env")  # noqa: F821  (SCons provides Import and env)

project = Path(env["PROJECT_DIR"])  # noqa: F821
header = project / "build" / "gen" / "web_assets.h"
subprocess.run(
    [sys.executable, str(project / "tools" / "embed_web.py"), str(project / "web"), str(header)],
    check=True,
)
env.Append(CPPPATH=[str(header.parent)])  # noqa: F821

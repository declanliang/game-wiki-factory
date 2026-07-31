"""Load server Factory env safely and exec gamewiki.py.

The operator-facing `/usr/local/bin/gamewiki` wrapper must not `source`
factory.env in a shell.  Values in that file are secrets and configuration, not
executable script.  This runner uses the same conservative dotenv parser as the
Factory itself, then replaces the process with the real CLI.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path("/srv/game-wiki-factory/app")
VENV_PYTHON = Path("/srv/game-wiki-factory/venv/bin/python")
ENV_PATH = Path(
    os.environ.get(
        "GAMEWIKI_FACTORY_ENV",
        "/srv/game-wiki-factory/secrets/factory.env",
    )
)


def main(argv: list[str]) -> int:
    if not ENV_PATH.is_file():
        print(f"factory environment file does not exist: {ENV_PATH}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(ROOT))
    from orchestrate_wiki import parse_dotenv

    env = os.environ.copy()
    env.update(parse_dotenv(ENV_PATH))
    os.chdir(ROOT)
    os.execve(str(VENV_PYTHON), [str(VENV_PYTHON), "gamewiki.py", *argv], env)
    raise AssertionError("os.execve returned unexpectedly")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

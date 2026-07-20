"""Friendly command-line entry point for the Game Wiki factory."""

import sys

from orchestrate_wiki import main


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        from publisher import publish
        raise SystemExit(publish(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in {"run-many", "status", "logs", "resume"}:
        from factory_cli import dispatch
        raise SystemExit(dispatch(sys.argv[1], sys.argv[2:]))
    raise SystemExit(main())

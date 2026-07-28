"""Friendly command-line entry point for the Game Wiki factory."""

import sys

from orchestrate_wiki import main


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "jobs":
        from job_system import jobs_cli
        raise SystemExit(jobs_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        from job_system import worker_cli
        raise SystemExit(worker_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "control-server":
        from job_control import control_cli
        raise SystemExit(control_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "notifier":
        from job_notifier import notifier_cli
        raise SystemExit(notifier_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "supervisor":
        from job_supervisor import supervisor_cli
        raise SystemExit(supervisor_cli(sys.argv[2:]))
    if len(sys.argv) > 2 and sys.argv[1] == "--config":
        from factory_cli import dispatch
        raise SystemExit(dispatch("run-config", sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        from publisher import publish
        raise SystemExit(publish(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "release-locale":
        from locale_publication import release_locale
        raise SystemExit(release_locale(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in {"run-config", "run-many", "status", "logs", "resume"}:
        from factory_cli import dispatch
        raise SystemExit(dispatch(sys.argv[1], sys.argv[2:]))
    raise SystemExit(main())

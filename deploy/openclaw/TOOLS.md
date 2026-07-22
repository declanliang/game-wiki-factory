# Tools

The authoritative interface is the `gamewiki.py jobs` CLI documented in `AGENTS.md`. The loopback API at `127.0.0.1:8787` is reserved for local integrations and requires `GAMEWIKI_CONTROL_TOKEN`; do not retrieve that token yourself. System health can be read with `systemctl status gamewiki-worker gamewiki-control` and `df -h /`.

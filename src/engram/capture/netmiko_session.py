"""Netmiko-based device session: connect, run commands, capture raw output.

Credentials come from env (DEVICE_SSH_USERNAME / DEVICE_SSH_PASSWORD) — never
hardcoded. For the Containerlab FRR demo, devices run an SSH server and `vtysh`;
`device_type="linux"` with a `vtysh -c "<cmd>"` wrapper works well, or use the
appropriate netmiko driver for real gear (cisco_ios, arista_eos, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engram.config import get_settings


@dataclass
class CommandResult:
    device: str
    command: str
    raw_output: str


class DeviceSession:
    def __init__(self, host: str, device_type: str = "linux", hostname: str | None = None):
        self.host = host
        self.device_type = device_type
        self.hostname = hostname or host
        self._conn: Any = None

    def __enter__(self) -> DeviceSession:
        from netmiko import ConnectHandler

        s = get_settings()
        if not s.device_ssh_username:
            raise RuntimeError(
                "DEVICE_SSH_USERNAME/PASSWORD not set in .env.local — required for live capture."
            )
        self._conn = ConnectHandler(
            device_type=self.device_type,
            host=self.host,
            username=s.device_ssh_username,
            password=s.device_ssh_password,
            fast_cli=False,
        )
        return self

    def __exit__(self, *exc) -> None:
        if self._conn is not None:
            self._conn.disconnect()
            self._conn = None

    def run(self, command: str) -> CommandResult:
        if self._conn is None:
            raise RuntimeError("session not open")
        out = self._conn.send_command(command, read_timeout=30)
        return CommandResult(device=self.hostname, command=command, raw_output=out)

    def run_many(self, commands: list[str]) -> list[CommandResult]:
        return [self.run(c) for c in commands]

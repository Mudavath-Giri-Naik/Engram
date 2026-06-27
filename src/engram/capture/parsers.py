"""Turn raw `show` output into structured data.

Strategy (best-effort, never fatal):
  1. ntc-templates (TextFSM) via `parse_output` when a template exists for the
     platform+command. This is the open-source workhorse.
  2. Optional Genie/pyATS parser if installed (heavy; behind a try/except).
  3. Fall back to returning None (the raw_output is always retained regardless).

Parsing enriches an InvestigationStep but is NEVER required — Engram works on
raw text too, and the embedding/signature paths use the raw output directly.
"""

from __future__ import annotations

from typing import Any


def parse_with_ntc(platform: str, command: str, raw: str) -> list[dict[str, Any]] | None:
    """Parse with ntc-templates TextFSM. Returns list-of-dicts or None."""
    try:
        from ntc_templates.parse import parse_output

        parsed = parse_output(platform=platform, command=command, data=raw)
        return parsed or None
    except Exception:
        return None


def parse_with_genie(platform: str, command: str, raw: str) -> dict | None:
    """Parse with Genie if pyATS is installed. Returns dict or None."""
    try:
        from genie.conf.base import Device  # type: ignore
        from genie.libs.parser.utils import get_parser  # type: ignore

        dev = Device(name="tmp", os=platform)
        dev.custom.setdefault("abstraction", {"order": ["os"]})
        parser_cls = get_parser(command, dev)[0]
        return parser_cls(device=dev).cli(output=raw)
    except Exception:
        return None


# Map common netmiko device_types to ntc-templates platform names.
_PLATFORM_MAP = {
    "cisco_ios": "cisco_ios",
    "cisco_xe": "cisco_ios",
    "cisco_nxos": "cisco_nxos",
    "cisco_xr": "cisco_xr",
    "arista_eos": "arista_eos",
    "juniper_junos": "juniper_junos",
    "linux": "linux",
    # FRR/vtysh output closely resembles Cisco IOS for many show commands.
    "frr": "cisco_ios",
}


def parse(device_type: str, command: str, raw: str) -> dict | None:
    """Best-effort structured parse. Returns {'parser':..., 'data':...} or None."""
    platform = _PLATFORM_MAP.get(device_type, device_type)

    ntc = parse_with_ntc(platform, command, raw)
    if ntc is not None:
        return {"parser": "ntc-templates", "platform": platform, "data": ntc}

    genie = parse_with_genie(platform, command, raw)
    if genie is not None:
        return {"parser": "genie", "platform": platform, "data": genie}

    return None

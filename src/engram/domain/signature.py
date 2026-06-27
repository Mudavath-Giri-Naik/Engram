"""Symptom-signature normalization.

A *signature* is a stable, machine-comparable label for a class of fault
(e.g. ``BGP_NEIGHBOR_DOWN``, ``MTU_MISMATCH``). Two incidents with the same
signature are the "same kind" of fault even if their English descriptions and
raw device output differ. This is what lets retrieval filter precisely where
embeddings-alone would conflate distinct faults that merely *read* similarly.

`derive_signature` is intentionally rule-based and inspectable: it scans the
symptom description plus captured command output for well-known patterns. It is
NOT an LLM call — signatures must be deterministic and cheap.
"""

from __future__ import annotations

import re

from engram.domain.enums import Protocol

# Ordered rules: (signature, compiled regex over normalized text).
# Order matters — more specific patterns first.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("MTU_MISMATCH", re.compile(r"\bmtu\b.*(mismatch|differ|wrong|1500|9000|9216)|mismatched mtu")),
    ("BGP_NEIGHBOR_DOWN", re.compile(r"\bbgp\b.*(neighbor|peer).*(down|idle|active|not establish|flap)")),
    ("BGP_ASPATH_ISSUE", re.compile(r"\bbgp\b.*(as[-_ ]?path|as path|prepend|aspath)")),
    ("OSPF_ADJ_DOWN", re.compile(r"\bospf\b.*(adjacenc|neighbor).*(down|stuck|exstart|init|2-?way)")),
    ("OSPF_COST_BLACKHOLE", re.compile(r"\bospf\b.*(cost|metric).*(blackhol|wrong|misconfig|loop)|blackhole")),
    ("ACL_BLOCK", re.compile(r"\bacl\b.*(block|deny|drop)|access[-_ ]?list.*deny")),
    ("STP_LOOP", re.compile(r"\bstp\b.*(loop|tcn|topology change)|spanning[-_ ]?tree.*loop")),
    ("VLAN_MISMATCH", re.compile(r"\bvlan\b.*(mismatch|missing|prune|native)")),
    ("ARP_INCOMPLETE", re.compile(r"\barp\b.*(incomplete|fail|miss)")),
    ("DNS_RESOLUTION_FAIL", re.compile(r"\bdns\b.*(fail|nxdomain|timeout|resolv)")),
    ("DHCP_NO_LEASE", re.compile(r"\bdhcp\b.*(no lease|discover|no offer|exhaust)")),
    ("NAT_TRANSLATION_FAIL", re.compile(r"\bnat\b.*(fail|no translation|exhaust)")),
]

# Fallback by protocol when no specific pattern matches.
_PROTOCOL_FALLBACK: dict[Protocol, str] = {
    Protocol.BGP: "BGP_ISSUE",
    Protocol.OSPF: "OSPF_ISSUE",
    Protocol.MTU: "MTU_MISMATCH",
    Protocol.ACL: "ACL_BLOCK",
    Protocol.STP: "STP_ISSUE",
    Protocol.VLAN: "VLAN_MISMATCH",
    Protocol.ARP: "ARP_INCOMPLETE",
    Protocol.DNS: "DNS_RESOLUTION_FAIL",
    Protocol.DHCP: "DHCP_NO_LEASE",
    Protocol.NAT: "NAT_TRANSLATION_FAIL",
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def derive_signature(
    description: str,
    *,
    protocols: list[Protocol] | None = None,
    extra_text: str = "",
) -> str:
    """Return a normalized signature string for a symptom.

    `extra_text` lets callers fold in captured command output so that signatures
    can be derived from real device evidence, not just the human description.
    """
    blob = normalize(f"{description} {extra_text}")
    for sig, pattern in _RULES:
        if pattern.search(blob):
            return sig
    for proto in protocols or []:
        if proto in _PROTOCOL_FALLBACK:
            return _PROTOCOL_FALLBACK[proto]
    return "UNCLASSIFIED"

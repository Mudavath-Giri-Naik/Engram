"""Controlled vocabularies for incident classification.

These enums are part of the IP: by forcing every incident into a structured
taxonomy (layer, protocol, scope, severity, outcome) we make *filter-then-rank*
retrieval possible. Free-text alone cannot be filtered reliably; these can.
"""

from __future__ import annotations

from enum import Enum


class Layer(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L7 = "L7"
    UNKNOWN = "UNKNOWN"


class Protocol(str, Enum):
    OSPF = "OSPF"
    BGP = "BGP"
    EIGRP = "EIGRP"
    STP = "STP"
    VLAN = "VLAN"
    ARP = "ARP"
    DNS = "DNS"
    DHCP = "DHCP"
    MTU = "MTU"
    ACL = "ACL"
    NAT = "NAT"
    QOS = "QOS"
    OTHER = "OTHER"


class Scope(str, Enum):
    DEVICE = "DEVICE"
    LINK = "LINK"
    SITE = "SITE"
    NETWORK_WIDE = "NETWORK_WIDE"


class Severity(str, Enum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"

    @property
    def rank(self) -> int:
        """Lower rank = more severe. Used for severity-proximity scoring."""
        return {"SEV1": 1, "SEV2": 2, "SEV3": 3, "SEV4": 4}[self.value]


class Outcome(str, Enum):
    RESOLVED = "RESOLVED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

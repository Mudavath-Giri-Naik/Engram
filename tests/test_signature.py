"""Signature normalization on REAL captured device outputs (fixtures)."""

from __future__ import annotations

from engram.domain.enums import Protocol
from engram.domain.signature import derive_signature
from tests.conftest import fixture_text


def test_bgp_neighbor_down_signature():
    raw = fixture_text("bgp_neighbor_down_show_ip_bgp_summary.txt") + fixture_text(
        "bgp_neighbor_detail.txt"
    )
    sig = derive_signature(
        "BGP neighbor 10.0.13.1 to R1 stuck Active", protocols=[Protocol.BGP], extra_text=raw
    )
    assert sig == "BGP_NEIGHBOR_DOWN"


def test_mtu_mismatch_signature():
    raw = fixture_text("mtu_mismatch_show_interface.txt")
    sig = derive_signature(
        "OSPF adjacency stuck, mtu mismatch suspected",
        protocols=[Protocol.OSPF, Protocol.MTU],
        extra_text=raw,
    )
    assert sig == "MTU_MISMATCH"


def test_ospf_adjacency_signature():
    raw = fixture_text("ospf_neighbor.txt")
    sig = derive_signature("OSPF neighbor stuck in ExStart", protocols=[Protocol.OSPF], extra_text=raw)
    assert sig == "OSPF_ADJ_DOWN"


def test_acl_block_signature():
    raw = fixture_text("acl_block_show_access_list.txt")
    sig = derive_signature("database flow dropped by access-list deny", protocols=[Protocol.ACL], extra_text=raw)
    assert sig == "ACL_BLOCK"


def test_aspath_variant_signature():
    sig = derive_signature("bgp as-path prepend causing route filtering", protocols=[Protocol.BGP])
    assert sig == "BGP_ASPATH_ISSUE"


def test_protocol_fallback_then_unclassified():
    assert derive_signature("totally unknown thing", protocols=[Protocol.BGP]) == "BGP_ISSUE"
    assert derive_signature("totally unknown thing", protocols=[]) == "UNCLASSIFIED"

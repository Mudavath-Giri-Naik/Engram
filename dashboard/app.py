"""Engram dashboard (Streamlit) — talks to the API only, never the DB directly.

Pages:
  - Incidents : filterable table + detail view (investigation timeline, RCA, fix, outcome)
  - New Fault : describe a fault -> /v1/query -> top-3 matches (with match
                explanations, staleness + FAILED-fix warnings) + LLM comparative analysis
  - Stats     : counts per protocol/outcome, MTTR, FAILED fixes remembered

Run with:  engram dashboard   (or:  streamlit run dashboard/app.py)
Set ENGRAM_API_URL / ENGRAM_API_KEY in the environment, or use the sidebar.
"""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Engram", page_icon="🧠", layout="wide")

# --- connection settings (sidebar) ------------------------------------------
st.sidebar.title("🧠 Engram")
st.sidebar.caption("Network-specific incident memory")
api_url = st.sidebar.text_input("API URL", os.environ.get("ENGRAM_API_URL", "http://localhost:8000"))
api_key = st.sidebar.text_input(
    "API Key", os.environ.get("ENGRAM_API_KEY", ""), type="password"
)
page = st.sidebar.radio("Page", ["New Fault", "Incidents", "Stats"])

HEADERS = {"X-API-Key": api_key}


def api_get(path: str, params: dict | None = None):
    r = httpx.get(f"{api_url}{path}", headers=HEADERS, params=params or {}, timeout=60)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict, params: dict | None = None):
    r = httpx.post(f"{api_url}{path}", headers=HEADERS, json=body, params=params or {}, timeout=120)
    r.raise_for_status()
    return r.json()


def _health_badge() -> None:
    try:
        h = httpx.get(f"{api_url}/health", timeout=10).json()
        ok = h.get("status") == "ok"
        st.sidebar.success("API healthy") if ok else st.sidebar.warning(f"API degraded: {h.get('checks')}")
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"API unreachable: {e}")


_health_badge()


# ============================================================ NEW FAULT page
if page == "New Fault":
    st.header("New Fault — comparative reasoning over this network's memory")
    with st.form("fault"):
        desc = st.text_area("Describe the fault", height=120,
                            placeholder="e.g. BGP session to upstream flapping on R3, AS-path looks different")
        c1, c2, c3 = st.columns(3)
        layer = c1.selectbox("Affected layer", ["", "L1", "L2", "L3", "L4", "L7", "UNKNOWN"])
        scope = c2.selectbox("Scope", ["", "DEVICE", "LINK", "SITE", "NETWORK_WIDE"])
        severity = c3.selectbox("Severity", ["", "SEV1", "SEV2", "SEV3", "SEV4"])
        protocols = st.multiselect(
            "Protocols",
            ["OSPF", "BGP", "EIGRP", "STP", "VLAN", "ARP", "DNS", "DHCP", "MTU", "ACL", "NAT", "QOS", "OTHER"],
        )
        devices = st.text_input("Devices (comma-separated)", "")
        topo = st.text_input("Current topology hash (optional)", "")
        reason_enabled = st.checkbox("Run LLM comparative reasoning", value=True)
        submitted = st.form_submit_button("Search memory")

    if submitted and desc.strip():
        body = {
            "network_id": "from-auth",
            "description": desc,
            "affected_layer": layer or None,
            "scope": scope or None,
            "severity": severity or None,
            "protocols": protocols,
            "devices": [d.strip() for d in devices.split(",") if d.strip()],
            "current_topology_hash": topo or None,
        }
        try:
            data = api_post("/v1/query", body, params={"reason_enabled": str(reason_enabled).lower()})
        except Exception as e:  # noqa: BLE001
            st.error(f"Query failed: {e}")
            st.stop()

        st.subheader("Top retrieved incidents (this network)")
        if not data["retrieved"]:
            st.info(data.get("reasoning_error") or "No prior incidents in memory yet.")
        for i, r in enumerate(data["retrieved"], 1):
            inc = r["incident"]
            with st.container(border=True):
                top = st.columns([3, 1, 1, 1])
                top[0].markdown(f"**#{i} · {inc.get('title') or inc['symptom']['description'][:60]}**")
                top[1].metric("final", f"{r['final_score']:.3f}")
                top[2].metric("vector", f"{r['vector_score']:.3f}")
                top[3].metric("structured", f"{r['structured_score']:.3f}")
                st.caption("🔎 " + r["match_explanation"])
                if r.get("outcome_flag"):
                    st.error("⚠️ " + r["outcome_flag"])
                stale = r.get("staleness", {})
                if stale.get("stale"):
                    st.warning(f"🕑 Stale: {', '.join(stale.get('reasons', []))} (age {stale.get('age_days')}d)")
                with st.expander("Root cause / fix / signature"):
                    st.write(f"**Signature:** `{inc['symptom']['signature']}`")
                    st.write(f"**Root cause:** {inc['resolution']['root_cause']}")
                    st.write(f"**Fix:** {inc['resolution']['fix_description']}")
                    st.write(f"**Outcome:** {inc['outcome']['status']}")

        reasoning = data.get("reasoning")
        st.subheader("LLM comparative analysis")
        if reasoning is None:
            st.info(data.get("reasoning_error") or "Reasoning not run.")
        else:
            cc = st.columns([1, 3])
            cc[0].metric("Confidence", reasoning["confidence"])
            cc[1].success("Recommended hypothesis: " + reasoning["recommended_hypothesis"])
            st.markdown("**Recommended fix (adapt + verify before applying):**")
            st.write(reasoning["recommended_fix"])
            if reasoning.get("adapted_from"):
                st.caption("Adapted from incident(s): " + ", ".join(reasoning["adapted_from"]))
            for w in reasoning.get("warnings", []):
                st.warning("⚠️ " + w)
            for comp in reasoning.get("comparisons", []):
                st.markdown(f"- **{comp['similarity_pct']}%** like `{comp['incident_id'][:8]}` — {comp['rationale']}")
                for d in comp.get("key_differences", []):
                    st.caption(f"    • difference: {d}")
            st.info("Decision support only — a human must approve. requires_human_approval = "
                    f"{reasoning.get('requires_human_approval')}")


# ============================================================ INCIDENTS page
elif page == "Incidents":
    st.header("Incidents")
    c1, c2, c3 = st.columns(3)
    f_proto = c1.selectbox("Protocol", ["", "OSPF", "BGP", "MTU", "ACL", "STP", "VLAN", "DNS", "DHCP", "NAT"])
    f_layer = c2.selectbox("Layer", ["", "L1", "L2", "L3", "L4", "L7"])
    f_outcome = c3.selectbox("Outcome", ["", "RESOLVED", "PARTIAL", "FAILED", "UNKNOWN"])
    params = {k: v for k, v in {"protocol": f_proto, "layer": f_layer, "outcome": f_outcome}.items() if v}
    try:
        incidents = api_get("/v1/incidents", params)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load incidents: {e}")
        st.stop()

    if not incidents:
        st.info("No incidents yet. Capture some with `engram capture`.")
    else:
        rows = [{
            "id": inc["id"][:8],
            "title": inc.get("title"),
            "signature": inc["symptom"]["signature"],
            "protocols": ",".join(inc["symptom"]["protocols"]),
            "layer": inc["symptom"]["affected_layer"],
            "severity": inc["symptom"]["severity"],
            "outcome": inc["outcome"]["status"],
            "occurred_at": inc["occurred_at"][:19],
        } for inc in incidents]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        labels = {f"{inc.get('title') or inc['id'][:8]} ({inc['id'][:8]})": inc for inc in incidents}
        sel = st.selectbox("Inspect incident", list(labels))
        inc = labels[sel]
        st.subheader(inc.get("title") or inc["id"])
        meta = st.columns(4)
        meta[0].metric("Signature", inc["symptom"]["signature"])
        meta[1].metric("Severity", inc["symptom"]["severity"])
        meta[2].metric("Outcome", inc["outcome"]["status"])
        meta[3].metric("MTTR (s)", inc["outcome"].get("mttr_seconds") or "—")
        st.write("**Symptom:** " + inc["symptom"]["description"])
        st.markdown("**Investigation timeline**")
        for step in inc["investigation"]:
            with st.expander(f"{step['device']} · `{step['command']}`"):
                st.code(step["raw_output"] or "(no output)")
        st.markdown("**Root cause:** " + (inc["resolution"]["root_cause"] or "—"))
        st.markdown("**Fix:** " + (inc["resolution"]["fix_description"] or "—"))


# ============================================================ STATS page
elif page == "Stats":
    st.header("Stats")
    try:
        s = api_get("/v1/stats")
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to load stats: {e}")
        st.stop()
    k = st.columns(3)
    k[0].metric("Total incidents", s.get("total", 0))
    k[1].metric("FAILED fixes remembered", s.get("failed_fixes_remembered", 0))
    k[2].metric("Avg MTTR (s)", s.get("avg_mttr_seconds") or "—")
    if s.get("by_protocol"):
        st.subheader("By protocol")
        st.bar_chart(pd.Series(s["by_protocol"]))
    if s.get("by_outcome"):
        st.subheader("By outcome")
        st.bar_chart(pd.Series(s["by_outcome"]))

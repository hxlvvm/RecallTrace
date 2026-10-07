"""RecallTrace demo: match a fictional clinic inventory against an openFDA device-recall snapshot."""
import html
import pathlib
import re
import sys

import pandas as pd
import streamlit as st

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from recalltrace.pipeline import MISMATCH, MISSING, NEED_MODEL, NONE_FOUND, REVIEW, Engine  # noqa: E402

DOT = {REVIEW: ":red[●]", MISSING: ":orange[●]", NEED_MODEL: ":orange[●]", MISMATCH: ":green[●]", NONE_FOUND: ":gray[●]"}
SHORT = {REVIEW: "Review required", MISSING: "Information missing", NEED_MODEL: "Model number needed",
         MISMATCH: "Outside recall scope", NONE_FOUND: "No candidate found"}
VERDICT_DOT = {"affected": ":red[●]", "unresolved": ":orange[●]", "not_affected": ":green[●]"}
COLUMNS = ["asset_tag", "department", "manufacturer", "device", "model", "ref", "udi_di", "serial", "lot", "software"]
PHI = re.compile(r"\b(patient|mrn|dob|date of birth|ssn)\b|\b\d{1,2}/\d{1,2}/(19|20)\d{2}\b", re.I)
ORDER = {REVIEW: 0, MISSING: 1, NEED_MODEL: 2, MISMATCH: 3, NONE_FOUND: 4}

st.set_page_config(page_title="RecallTrace", page_icon=":material/search:", layout="wide")


@st.cache_resource(show_spinner="Loading the recall snapshot...")
def engine():
    return Engine(ROOT)


def clean(rows):
    return [r for r in rows if not PHI.search(" ".join(map(str, r.values())))]


def show_finding(f, row, expanded=False):
    label = f'{DOT[f.status]} **{row.get("asset_tag") or "Device"}** · {row.get("manufacturer", "")} {row.get("device", "")} — {SHORT[f.status]}'
    with st.expander(label, expanded=expanded):
        left, right = st.columns([1, 1])
        with left:
            st.markdown(f"**{f.status}**")
            if f.record:
                st.markdown(f"**Recall {f.record}** · {html.escape(f.firm)}  \n{html.escape(f.product)}")
            st.markdown(f"**Same product?** {html.escape(f.identity)}")
            st.markdown(f"**This unit in scope?** {html.escape(f.scope)}")
            if f.link and f.record:
                st.markdown(f"[Open the FDA recall notice]({f.link})")
            if f.others:
                st.markdown("**Other recalls of this product**")
                for o in f.others[:6]:
                    st.markdown(f"{VERDICT_DOT.get(o['verdict'], ':gray[●]')} [{o['record']}]({o['link']}) · {html.escape(o['reason'])}")
                if len(f.others) > 6:
                    st.caption(f"and {len(f.others) - 6} more")
        with right:
            st.markdown("**Source text**")
            for s in f.snippets or ["<i>No identifier from this row appears in the recall text.</i>"]:
                st.markdown(f"<div style='font-size:0.85em;line-height:1.45;margin-bottom:0.7em'>{s}</div>",
                            unsafe_allow_html=True)


def device_checker():
    q = st.query_params
    st.markdown("Enter what is on the device label. Change one character of the serial and watch the verdict change.")
    c = st.columns(6)
    row = {"manufacturer": c[0].text_input("Manufacturer", q.get("manufacturer", "Masimo")),
           "device": c[1].text_input("Device", q.get("device", "Rad-G pulse oximeter")),
           "model": c[2].text_input("Model", q.get("model", "")),
           "ref": c[3].text_input("REF / catalogue no.", q.get("ref", "9847")),
           "serial": c[4].text_input("Serial", q.get("serial", "6000062125")),
           "lot": c[5].text_input("Lot", q.get("lot", ""))}
    if not clean([row]):
        st.error("That looks like patient information. Use equipment data only.")
        return
    show_finding(engine().review_row(0, row), row, expanded=True)


def inventory_scan():
    inventory = pd.read_csv(ROOT / "data/demo/clinic_inventory.csv", dtype=str).fillna("")
    st.caption("A fictional outpatient clinic. Edit any cell (a serial, a model number) and the queue updates.")
    edited = st.data_editor(inventory, num_rows="dynamic", use_container_width=True, hide_index=True, height=250)
    rows = edited.reindex(columns=COLUMNS).fillna("").astype(str).to_dict("records")
    kept = clean(rows)
    if len(kept) < len(rows):
        st.error("Some rows look like they contain patient information and were skipped.")
    kept = [r for r in kept if any(r.get(k) for k in COLUMNS[2:])]
    findings = engine().review(kept)
    cols = st.columns(len(SHORT))
    for col, s in zip(cols, SHORT):
        col.metric(f"{DOT[s]} {SHORT[s]}", sum(f.status == s for f in findings))
    opened = st.query_params.get("open", "")
    for f in sorted(findings, key=lambda f: (ORDER[f.status], f.row)):
        show_finding(f, kept[f.row], expanded=kept[f.row].get("asset_tag") == opened)


st.title("RecallTrace")
st.markdown("Match medical equipment against **FDA device recalls**, and see the recall text behind every call.")
st.info("Inventory and devices here are **fictional**. Recalls come from an openFDA snapshot: infusion pumps, ventilators, "
        "AEDs, patient monitors and pulse oximeters, 1,794 recall records retrieved 7 Oct 2026. This is an engineering "
        "prototype and a review aid, not a safety system. A missing match never means a device is safe.",
        icon=":material/info:")

if st.query_params.get("view") == "device":
    device_checker()
else:
    tab_scan, tab_one = st.tabs(["Scan a clinic inventory", "Check one device"])
    with tab_scan:
        inventory_scan()
    with tab_one:
        device_checker()

with st.expander("How it works, how it was tested, and what it cannot do"):
    st.markdown("""
- **Offline extraction.** An open-weight LLM (gpt-oss-20b) read each recall's scope text once and proposed structure:
  identifiers, serial and lot lists or ranges, prefixes, software conditions and per-model scopes. Python kept only
  values that literally appear in the recall text. The app makes no LLM calls.
- **Matching.** Exact model, catalogue and UDI-DI lookups first, then manufacturer and device-name similarity.
- **Three-valued scope check:** affected, outside scope, or not enough information. Missing serial or lot numbers stay
  unresolved instead of being guessed.
- **Blind test** (70 hand-written cases, written after the system was frozen): 64 correct, 2 wrong definitive
  answers, 1 answer where it should have abstained, 3 abstentions. A regex-only version got 61 right and made
  5 wrong definitive answers.
- **Limits:** five device categories; a snapshot, not live data; rows without a model number cannot be confirmed.
""")
st.caption("Code and evaluation: https://github.com/hxlvvm/RecallTrace · Data: openFDA (CC0) · Fictional inventory")

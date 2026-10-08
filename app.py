"""
MAHPO Project Office Dashboard
===============================
Streamlit dashboard reading from a Google Sheet.
Run:  streamlit run app.py
"""

from datetime import datetime, timedelta, timezone

import streamlit as st
import pandas as pd
from data_loader import load_sheet
from freshness import track_first_seen

# ── Config ──
SHEET_ID = "1YklJC8YnjUvAXY9PImRLqWouqKiPIj4laeSFH1l6qJk"

STATUS_COLORS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
INK_SECONDARY = "#52514e"


def activity_update_date(acts: pd.DataFrame) -> pd.Series:
    """Proxy for 'last updated' per activity row: its completed date, or else its date."""
    cols = [c for c in ("completed_date", "date") if c in acts.columns]
    if not cols:
        return pd.Series(pd.NaT, index=acts.index)
    return acts[cols].max(axis=1, skipna=True)


# ── Page config ──
st.set_page_config(
    page_title="MAHPO Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ──
st.markdown(
    """
    <style>
    /* KPI cards */
    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #e1e0d9;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="stMetric"] label {
        color: #52514e;
        font-size: 0.85rem;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem;
        font-weight: 600;
    }
    /* Project cards */
    div[class*="st-key-project_card_"] {
        background: #f1f1ef;
    }
    /* Sidebar heading */
    section[data-testid="stSidebar"] h1 {
        font-size: 1.1rem;
        color: #52514e;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Load data ──
try:
    projects, activity = load_sheet(SHEET_ID)
except Exception as e:
    st.error(f"Failed to load Google Sheet: {e}")
    st.info("Make sure the sheet is shared with the service account email.")
    st.stop()

if projects.empty:
    st.warning("No project data found in the sheet.")
    st.stop()


# ═══════════════════════════════════════════
#  SIDEBAR FILTERS
# ═══════════════════════════════════════════
st.sidebar.title("Filters")

# Status
all_statuses = sorted(projects["status"].unique().tolist()) if "status" in projects.columns else []
sel_status = st.sidebar.multiselect("Status", all_statuses, default=all_statuses)

# Priority
all_priorities = sorted(projects["priority"].unique().tolist()) if "priority" in projects.columns else []
sel_priority = st.sidebar.multiselect("Priority", all_priorities, default=all_priorities)

# Category
all_categories = sorted(projects["category"].unique().tolist()) if "category" in projects.columns else []
sel_category = st.sidebar.multiselect("Category", all_categories, default=all_categories)

# Assigned person
if "assigned_person" in projects.columns:
    all_persons = sorted([p for p in projects["assigned_person"].unique() if p])
    sel_person = st.sidebar.multiselect("Assigned Person", all_persons, default=all_persons)
else:
    sel_person = []

# State
if "state" in projects.columns:
    all_states = sorted([s for s in projects["state"].unique() if s])
    sel_state = st.sidebar.multiselect("State", all_states, default=all_states)
else:
    sel_state = []

# Apply filters
filt = projects.copy()
if "status" in filt.columns and sel_status:
    filt = filt[filt["status"].isin(sel_status)]
if "priority" in filt.columns and sel_priority:
    filt = filt[filt["priority"].isin(sel_priority)]
if "category" in filt.columns and sel_category:
    filt = filt[filt["category"].isin(sel_category)]
if "assigned_person" in filt.columns and sel_person:
    filt = filt[filt["assigned_person"].isin(sel_person)]
if "state" in filt.columns and sel_state:
    filt = filt[filt["state"].isin(sel_state)]

# Filter activity to only matching project IDs
if "project_id" in filt.columns and "project_id" in activity.columns:
    filt_act = activity[activity["project_id"].isin(filt["project_id"])].copy()
else:
    filt_act = activity.copy()

filt_act["_update_date"] = activity_update_date(filt_act)

# ── Refresh button ──
st.sidebar.divider()
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()


# ═══════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════
st.title("Project Office — Muhammed Abdul Hakkim Azhari")
st.caption(f"Live from Google Sheet  ·  {len(filt)} project(s) shown")


# ═══════════════════════════════════════════
#  PROJECT TABLE
# ═══════════════════════════════════════════
st.subheader("Projects")

proj_first_seen, act_first_seen = track_first_seen(projects, activity)
fresh_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

new_project_ids = {pid for pid, ts in proj_first_seen.items() if ts >= fresh_cutoff}

updated_project_ids = set()
if "project_id" in activity.columns and "activity_id" in activity.columns:
    recent_activity_ids = {aid for aid, ts in act_first_seen.items() if ts >= fresh_cutoff}
    updated_project_ids = set(
        activity.loc[activity["activity_id"].isin(recent_activity_ids), "project_id"]
    )

if "project_id" in filt_act.columns:
    activity_counts = filt_act.groupby("project_id").size()
    latest_update_per_project = filt_act.groupby("project_id")["_update_date"].max()
else:
    activity_counts = pd.Series(dtype=int)
    latest_update_per_project = pd.Series(dtype="datetime64[ns]")

table_df = filt.copy()
if "project_id" in table_df.columns:
    table_df["activities"] = table_df["project_id"].map(activity_counts).fillna(0).astype(int)
    table_df["_last_update"] = table_df["project_id"].map(latest_update_per_project)
else:
    table_df["activities"] = 0
    table_df["_last_update"] = pd.NaT

# Most recently updated projects first; projects with no activity yet sink to the bottom.
table_df = table_df.sort_values("_last_update", ascending=False, na_position="last").reset_index(drop=True)


def _toggle_project(project_id: str) -> None:
    current = st.session_state.get("selected_project_id")
    st.session_state["selected_project_id"] = None if current == project_id else project_id


ACTIVITIES_PAGE_SIZE = 5


def _activities_page(df: pd.DataFrame, project_id: str, state_key: str) -> tuple[pd.DataFrame, int, int]:
    """Return (page_slice, current_page, total_pages) for one project's activities, 1-indexed."""
    pages = st.session_state.setdefault(state_key, {})
    total_pages = max(1, -(-len(df) // ACTIVITIES_PAGE_SIZE))
    current = min(max(pages.get(project_id, 1), 1), total_pages)
    pages[project_id] = current
    start = (current - 1) * ACTIVITIES_PAGE_SIZE
    return df.iloc[start : start + ACTIVITIES_PAGE_SIZE], current, total_pages


def _set_activities_page(state_key: str, project_id: str, page: int) -> None:
    st.session_state.setdefault(state_key, {})[project_id] = page


def _render_page_controls(
    project_id: str, state_key: str, current: int, total_pages: int, key_prefix: str
) -> None:
    if total_pages <= 1:
        return
    prev_col, label_col, next_col = st.columns([1, 2, 1])
    with prev_col:
        st.button(
            "Previous",
            icon=":material/chevron_left:",
            key=f"{key_prefix}_prev_{project_id}",
            width="stretch",
            disabled=current <= 1,
            on_click=_set_activities_page,
            args=(state_key, project_id, current - 1),
        )
    with label_col:
        st.markdown(f"Page {current} of {total_pages}", text_alignment="center")
    with next_col:
        st.button(
            "Next",
            icon=":material/chevron_right:",
            key=f"{key_prefix}_next_{project_id}",
            width="stretch",
            disabled=current >= total_pages,
            on_click=_set_activities_page,
            args=(state_key, project_id, current + 1),
        )


# Card list instead of st.dataframe: st.columns stacks vertically below ~640px,
# so each project reflows into a single wrapped column on mobile instead of truncating.
sel_project_id = st.session_state.get("selected_project_id")

if "project_id" in table_df.columns:
    for _, row in table_df.iterrows():
        project_id = row["project_id"]
        is_selected = project_id == sel_project_id
        with st.container(border=True, key=f"project_card_{project_id}"):
            name_col, view_col, state_col, person_col, count_col = st.columns([4, 1, 1.3, 1.6, 1])

            with name_col:
                st.markdown(f"**{str(row.get('project_name', '')).strip()}**")
                if project_id in new_project_ids:
                    st.badge("New", icon=":material/fiber_new:", color="green")
                elif project_id in updated_project_ids:
                    st.badge("Updated", icon=":material/update:", color="orange")

            with view_col:
                st.button(
                    "Hide" if is_selected else "View",
                    icon=":material/visibility_off:" if is_selected else ":material/visibility:",
                    key=f"view_project_{project_id}",
                    width="stretch",
                    on_click=_toggle_project,
                    args=(project_id,),
                )

            with state_col:
                st.caption("State")
                st.markdown(row.get("state", "") or "—")

            with person_col:
                st.caption("Assigned person")
                st.markdown(row.get("assigned_person", "") or "—")

            with count_col:
                st.caption("Activities")
                st.markdown(str(row.get("activities", 0)))

            # Show this project's activities inline, right under its own card.
            if is_selected:
                st.divider()
                st.markdown("**Activities**")

                if "project_id" in filt_act.columns:
                    proj_acts = filt_act[filt_act["project_id"] == project_id].sort_values(
                        "_update_date", ascending=False, na_position="last"
                    )
                else:
                    proj_acts = pd.DataFrame()

                if not proj_acts.empty:
                    page_df, current_page, total_pages = _activities_page(
                        proj_acts, project_id, "activities_page_by_project"
                    )
                    for _, act in page_df.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**{str(act.get('title', '')).strip()}**")
                            related_person = act.get("related_person", "")
                            if related_person:
                                st.caption(f"Related person: {related_person}")
                            notes = act.get("notes", "")
                            if notes:
                                st.write(notes)
                    _render_page_controls(
                        project_id, "activities_page_by_project", current_page, total_pages, "card"
                    )
                else:
                    st.info("No activities recorded for this project.")

st.caption(
    "New · created in the last 24h   ·   Updated · new activity added in the last 24h  "
    "·  sorted by most recently updated   ·   tap \"View\" to see a project's activities, \"Hide\" to collapse"
)

st.divider()


# ═══════════════════════════════════════════
#  KPI ROW
# ═══════════════════════════════════════════
k1, k2, k3, k4, k5 = st.columns(5)

k1.metric("Total Projects", len(filt))

if "status" in filt.columns:
    k2.metric("In Progress", int((filt["status"] == "In Progress").sum()))
    k3.metric("Completed", int((filt["status"] == "Completed").sum()))
else:
    k2.metric("In Progress", "–")
    k3.metric("Completed", "–")

if not filt_act.empty and "status" in filt_act.columns:
    tasks_done = int((filt_act["status"] == "Done").sum())
    tasks_total = len(filt_act)
    k4.metric("Activities Done", f"{tasks_done}/{tasks_total}")
else:
    k4.metric("Activities Done", "–")

if not filt_act.empty and "status" in filt_act.columns:
    delayed = int((filt_act["status"] == "Delayed").sum())
    k5.metric("Delayed Activities", delayed, delta=None)
else:
    k5.metric("Delayed Activities", "–")

st.divider()


# ═══════════════════════════════════════════
#  PROJECT DETAIL DRILLDOWN
# ═══════════════════════════════════════════
st.subheader("Project Detail")

if "project_name" in filt.columns:
    project_names = filt["project_name"].tolist()
    if project_names:
        selected_name = st.selectbox("Select a project", project_names, index=0)
        sel_proj = filt[filt["project_name"] == selected_name].iloc[0]

        # Info cards
        ic1, ic2, ic3, ic4 = st.columns(4)
        ic1.metric("Status", sel_proj.get("status", "–"))
        ic2.metric("Priority", sel_proj.get("priority", "–"))
        ic3.metric("Category", sel_proj.get("category", "–"))
        ic4.metric("State", sel_proj.get("state", "–"))

        # Description & remarks
        desc = sel_proj.get("description", "")
        remarks = sel_proj.get("remarks", "")
        if desc:
            st.markdown(f"**Description:** {desc}")
        if remarks:
            st.markdown(f"**Remarks:** {remarks}")

        # Related activities
        proj_id = sel_proj.get("project_id", "")
        if proj_id and "project_id" in filt_act.columns:
            proj_acts = filt_act[filt_act["project_id"] == proj_id].sort_values(
                "_update_date", ascending=False, na_position="last"
            )
            if not proj_acts.empty:
                st.markdown("#### Activities")

                page_df, current_page, total_pages = _activities_page(
                    proj_acts, proj_id, "detail_activities_page_by_project"
                )
                for _, act in page_df.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{str(act.get('title', '')).strip()}**")

                        meta_bits = [
                            str(v) for v in (act.get("type", ""), act.get("status", ""))
                            if v
                        ]
                        if act.get("related_person", ""):
                            meta_bits.append(f"with {act['related_person']}")
                        if meta_bits:
                            st.caption("  ·  ".join(meta_bits))

                        date_bits = []
                        if pd.notna(act.get("date")):
                            date_bits.append(f"Date: {act['date']:%d %b %Y}")
                        if pd.notna(act.get("completed_date")):
                            date_bits.append(f"Completed: {act['completed_date']:%d %b %Y}")
                        if date_bits:
                            st.caption("  ·  ".join(date_bits))

                        if act.get("notes", ""):
                            st.write(act["notes"])
                _render_page_controls(
                    proj_id, "detail_activities_page_by_project", current_page, total_pages, "detail"
                )
            else:
                st.info("No activities recorded for this project.")


# ── Footer ──
st.divider()
st.caption("MAHPO Project Office Dashboard  ·  Data refreshes every 5 minutes")

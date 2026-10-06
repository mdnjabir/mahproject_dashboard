"""
MAHPO Project Office Dashboard
===============================
Streamlit dashboard reading from a Google Sheet.
Run:  streamlit run app.py
"""

from datetime import datetime, timedelta, timezone

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import load_sheet
from freshness import track_first_seen

# ── Config ──
SHEET_ID = "1YklJC8YnjUvAXY9PImRLqWouqKiPIj4laeSFH1l6qJk"

# ── Palette (validated dataviz defaults) ──
PAL = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "magenta": "#e87ba4",
    "green": "#008300",
    "violet": "#4a3aa7",
    "red": "#e34948",
}
STATUS_COLORS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"

ACTIVITY_STATUS_COLOR = {
    "Done": PAL["aqua"],
    "Pending": PAL["yellow"],
    "In Progress": PAL["blue"],
    "Delayed": PAL["orange"],
    "N/A": INK_MUTED,
}

# ── Plotly layout defaults ──
LAYOUT_DEFAULTS = dict(
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=INK_PRIMARY, size=13),
    margin=dict(l=16, r=16, t=40, b=16),
    xaxis=dict(gridcolor=GRIDLINE, gridwidth=1, zerolinecolor=GRIDLINE),
    yaxis=dict(gridcolor=GRIDLINE, gridwidth=1, zerolinecolor=GRIDLINE),
    hoverlabel=dict(
        bgcolor="white",
        font_size=13,
        font_family="system-ui, -apple-system, 'Segoe UI', sans-serif",
    ),
)


def apply_layout(fig, **overrides):
    """Apply the standard layout to a Plotly figure."""
    opts = {**LAYOUT_DEFAULTS, **overrides}
    fig.update_layout(**opts)
    return fig


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
    initial_sidebar_state="expanded",
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
table_df = table_df.sort_values("_last_update", ascending=False, na_position="last")


def _freshness_label(row: pd.Series) -> str:
    if row["project_id"] in new_project_ids:
        return "New"
    if row["project_id"] in updated_project_ids:
        return "Updated"
    return ""


if "project_id" in table_df.columns:
    table_df["freshness"] = table_df.apply(_freshness_label, axis=1)
else:
    table_df["freshness"] = ""

table_df = table_df.reset_index(drop=True)
table_cols = [
    c for c in ["project_name", "state", "assigned_person", "activities", "freshness"]
    if c in table_df.columns
]

FRESHNESS_STYLE = {
    "New": "background-color: #d9f7e3; color: #0ca30c; font-weight: 600; border-radius: 4px;",
    "Updated": "background-color: #fff3d6; color: #b36b00; font-weight: 600; border-radius: 4px;",
}


def _style_freshness(val: str) -> str:
    return FRESHNESS_STYLE.get(val, "")


table_df["view"] = ":material/visibility: View"
table_cols_with_action = table_cols + ["view"]

styled_table = table_df[table_cols_with_action].style.map(_style_freshness, subset=["freshness"])


def _handle_view_click():
    click = st.session_state.get("projects_view_action")
    if click is not None and click.row is not None:
        st.session_state["selected_project_id"] = table_df.iloc[click.row]["project_id"]


st.dataframe(
    styled_table,
    width="stretch",
    hide_index=True,
    column_config={
        "project_name": st.column_config.TextColumn("Project", width="large"),
        "state": st.column_config.TextColumn("State"),
        "assigned_person": st.column_config.TextColumn("Assigned person"),
        "activities": st.column_config.NumberColumn("Activities", width="small"),
        "freshness": st.column_config.TextColumn("Status", width="small"),
        "view": st.column_config.ButtonColumn(
            "Activities", width="small", on_click=_handle_view_click, key="projects_view_action"
        ),
    },
)
st.caption(
    "New · created in the last 24h   ·   Updated · new activity added in the last 24h  "
    "·  sorted by most recently updated   ·   click \"View\" to see a project's activities"
)

sel_project_id = st.session_state.get("selected_project_id")
if sel_project_id is not None and "project_id" in table_df.columns and (
    table_df["project_id"] == sel_project_id
).any():
    sel_project_name = table_df.loc[table_df["project_id"] == sel_project_id, "project_name"].iloc[0]

    st.markdown(f"**Activities — {sel_project_name}**")

    if "project_id" in filt_act.columns:
        proj_acts = filt_act[filt_act["project_id"] == sel_project_id].sort_values(
            "_update_date", ascending=False, na_position="last"
        )
    else:
        proj_acts = pd.DataFrame()

    act_cols = [c for c in ["title", "related_person", "notes"] if c in proj_acts.columns]
    if not proj_acts.empty and act_cols:
        st.dataframe(
            proj_acts[act_cols].reset_index(drop=True),
            width="stretch",
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Activity", width="medium"),
                "related_person": st.column_config.TextColumn("Related person"),
                "notes": st.column_config.TextColumn("Remarks", width="large"),
            },
        )
    else:
        st.info("No activities recorded for this project.")

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

                act_display = [
                    c
                    for c in ["activity_id", "type", "title", "related_person",
                              "status", "date", "completed_date", "notes"]
                    if c in proj_acts.columns
                ]
                st.dataframe(
                    proj_acts[act_display].reset_index(drop=True),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "date": st.column_config.DateColumn("Date", format="DD MMM YYYY"),
                        "completed_date": st.column_config.DateColumn("Completed", format="DD MMM YYYY"),
                    },
                )

                # Activity status summary
                if "status" in proj_acts.columns:
                    act_status = proj_acts["status"].value_counts().reset_index()
                    act_status.columns = ["Status", "Count"]
                    act_colors = [ACTIVITY_STATUS_COLOR.get(s, INK_MUTED) for s in act_status["Status"]]

                    fig_act = go.Figure(
                        go.Bar(
                            x=act_status["Status"],
                            y=act_status["Count"],
                            marker=dict(color=act_colors, cornerradius=4),
                            text=act_status["Count"],
                            textposition="auto",
                            textfont=dict(size=12),
                            hovertemplate="<b>%{x}</b>: %{y}<extra></extra>",
                        )
                    )
                    apply_layout(fig_act, height=250, showlegend=False,
                                 xaxis=dict(gridcolor=GRIDLINE),
                                 yaxis=dict(title="Count", gridcolor=GRIDLINE))
                    st.plotly_chart(fig_act, width="stretch")
            else:
                st.info("No activities recorded for this project.")


# ── Footer ──
st.divider()
st.caption("MAHPO Project Office Dashboard  ·  Data refreshes every 5 minutes")

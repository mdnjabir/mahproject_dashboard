"""
data_loader.py — Google Sheets connector for MAHPO Dashboard.

Reads from a Google Sheet with two tabs (projects, activity),
parses dates, and returns clean DataFrames. Cached for 5 minutes
to avoid API rate limits.
"""

import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from pathlib import Path
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ---------- auth ----------

def _get_client() -> gspread.Client:
    """Authenticate with Google.

    Prefers Streamlit secrets (for Streamlit Cloud, where credentials.json
    can't be committed to the repo); falls back to a local credentials.json
    next to this script for local development.
    """
    try:
        has_secret = "gcp_service_account" in st.secrets
    except Exception:
        has_secret = False

    if has_secret:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), scopes=SCOPES
        )
        return gspread.authorize(creds)

    creds_path = Path(__file__).parent / "credentials.json"
    if not creds_path.exists():
        st.error(
            "No Google credentials found. Locally, place your service-account "
            "credentials.json next to this script. On Streamlit Cloud, add a "
            "[gcp_service_account] table to the app's Secrets instead (see README)."
        )
        st.stop()
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


# ---------- date helpers ----------

def _parse_date(val: str) -> pd.Timestamp | None:
    """Try several date formats and return a Timestamp or None."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None

    # DD/MM/YYYY or DD-MM-YYYY
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return pd.Timestamp(datetime.strptime(val, fmt))
        except ValueError:
            continue

    # Text dates like "September 30" (assume current year)
    current_year = datetime.now().year
    for fmt in ("%B %d", "%b %d", "%B %d, %Y", "%b %d, %Y"):
        try:
            dt = datetime.strptime(val, fmt)
            if dt.year == 1900:  # no year in format
                dt = dt.replace(year=current_year)
            return pd.Timestamp(dt)
        except ValueError:
            continue

    # Last resort: let pandas try
    try:
        return pd.Timestamp(val)
    except Exception:
        return None


# ---------- loaders ----------

@st.cache_data(ttl=300)
def load_sheet(sheet_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load both tabs from the Google Sheet.

    Returns (projects_df, activity_df).
    """
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)

    # ── Projects tab ──
    try:
        ws_proj = spreadsheet.worksheet("projects")
    except gspread.exceptions.WorksheetNotFound:
        ws_proj = spreadsheet.sheet1  # fallback to first sheet

    proj_records = ws_proj.get_all_records()
    projects = pd.DataFrame(proj_records)

    if not projects.empty:
        # Normalise column names
        projects.columns = [c.strip().lower().replace(" ", "_") for c in projects.columns]

        # Parse dates
        for col in ("start_date", "target_end_date", "actual_end_date"):
            if col in projects.columns:
                projects[col] = projects[col].astype(str).apply(_parse_date)

        # System timestamps stamped by the sheet's Apps Script (UTC ISO strings)
        for col in ("created_at", "updated_at"):
            if col in projects.columns:
                projects[col] = pd.to_datetime(projects[col], utc=True, errors="coerce")

        # Numeric columns
        for col in ("budget_allocated", "budget_spent", "progress_pct"):
            if col in projects.columns:
                projects[col] = pd.to_numeric(projects[col], errors="coerce")

        # Fill blanks in key filter columns
        for col in ("status", "priority", "category", "assigned_person", "state"):
            if col in projects.columns:
                projects[col] = projects[col].fillna("").astype(str).str.strip()

    # ── Activity tab ──
    try:
        ws_act = spreadsheet.worksheet("activity")
    except gspread.exceptions.WorksheetNotFound:
        ws_act = spreadsheet.get_worksheet(1)

    act_records = ws_act.get_all_records()
    activity = pd.DataFrame(act_records)

    if not activity.empty:
        activity.columns = [c.strip().lower().replace(" ", "_") for c in activity.columns]

        for col in ("completed_date", "date", "due_date"):
            if col in activity.columns:
                activity[col] = activity[col].astype(str).apply(_parse_date)

        for col in ("created_at", "updated_at"):
            if col in activity.columns:
                activity[col] = pd.to_datetime(activity[col], utc=True, errors="coerce")

        for col in ("status", "type"):
            if col in activity.columns:
                activity[col] = activity[col].fillna("").astype(str).str.strip()

    return projects, activity
